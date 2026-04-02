"""OCR routes — submit image, poll status, get results."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Dict, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image
import cv2
import numpy as np

from api.deps import get_pipeline
from api.schemas import (
    BatchCorrectionItem,
    BatchPrepareItem,
    BatchPrepareResponse,
    BatchStatusResponse,
    BatchSubmitRequest,
    BatchSubmitResponse,
    BatchTaskItem,
    ColumnData,
    OCROptions,
    OCRStatusResponse,
    OCRSubmitResponse,
    Point,
    TaskStatus,
)
from api.ws import broadcast_batch_progress, broadcast_progress
from core.image_utils import pil_to_bgr
from core.perspective import Corners, detect_corners, warp_perspective
from services.ocr_pipeline import OCRPipeline, OCRResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ocr", tags=["ocr"])

# In-memory task store.  Production → Redis.
_tasks: Dict[str, dict] = {}
# batch_id → { task_ids: [...], filenames: {task_id: filename} }
_batches: Dict[str, dict] = {}


def _task_entry(status: TaskStatus = TaskStatus.pending) -> dict:
    return {
        "status": status,
        "progress": 0.0,
        "result": None,
        "error": None,
    }


@router.post("/upload", response_model=OCRSubmitResponse)
async def upload(
    file: UploadFile = File(...),
    auto_rotate: bool = Form(True),
    remove_print: bool = Form(True),
    auto_split: bool = Form(True),
    task_id: str | None = Form(None),
    pipeline: OCRPipeline = Depends(get_pipeline),
) -> OCRSubmitResponse:
    """Upload an image and start OCR processing.

    If *task_id* is provided (from a previous ``/corner/correct`` call),
    the already-warped image is used instead of the uploaded file.
    """
    from api.routes.corner import _pending_images

    if task_id and task_id in _pending_images:
        img_bgr = _pending_images.pop(task_id)
    else:
        contents = await file.read()
        arr = np.frombuffer(contents, dtype=np.uint8)
        img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img_bgr is None:
            raise HTTPException(400, "Invalid image")
        task_id = uuid.uuid4().hex[:12]

    _tasks[task_id] = _task_entry(TaskStatus.processing)

    loop = asyncio.get_running_loop()

    # Run OCR in a background thread so we don't block the event loop
    loop.run_in_executor(
        None,
        _run_ocr,
        task_id,
        img_bgr,
        pipeline,
        OCROptions(
            auto_rotate=auto_rotate,
            remove_print=remove_print,
            auto_split=auto_split,
        ),
        loop,
    )

    return OCRSubmitResponse(task_id=task_id, status=TaskStatus.processing)


def _run_ocr(
    task_id: str,
    img_bgr: np.ndarray,
    pipeline: OCRPipeline,
    opts: OCROptions,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Blocking OCR execution — called from executor."""

    def _on_progress(stage: str, progress: float) -> None:
        _tasks[task_id]["progress"] = progress
        asyncio.run_coroutine_threadsafe(
            broadcast_progress(task_id, stage, progress),
            loop,
        )

    try:
        pil_img = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
        result = pipeline.run(
            pil_img,
            auto_rotate=opts.auto_rotate,
            remove_print=opts.remove_print,
            auto_split=opts.auto_split,
            on_progress=_on_progress,
        )
        _tasks[task_id]["status"] = TaskStatus.completed
        _tasks[task_id]["progress"] = 1.0
        _tasks[task_id]["result"] = result
        asyncio.run_coroutine_threadsafe(
            broadcast_progress(task_id, "完成", 1.0, status="completed"),
            loop,
        )
    except Exception as e:
        logger.exception("OCR failed for task %s", task_id)
        _tasks[task_id]["status"] = TaskStatus.failed
        _tasks[task_id]["error"] = str(e)
        asyncio.run_coroutine_threadsafe(
            broadcast_progress(task_id, "失敗", 0.0, status="failed"),
            loop,
        )


def _build_task_response(task_id: str) -> OCRStatusResponse:
    """Build an OCRStatusResponse for a single task."""
    entry = _tasks.get(task_id)
    if entry is None:
        return OCRStatusResponse(task_id=task_id, status=TaskStatus.pending, progress=0.0)

    result: OCRResult | None = entry.get("result")
    return OCRStatusResponse(
        task_id=task_id,
        status=entry["status"],
        progress=entry["progress"],
        title=result.title if result else None,
        text=result.text if result else None,
        columns=[
            ColumnData(
                col_index=c.col_index,
                text=c.text,
                spacing_indexes=c.spacing_indexes,
                num_rows=c.num_rows,
            )
            for c in (result.columns if result else [])
        ],
        rotation_angle=result.rotation_angle if result else None,
        elapsed_seconds=result.elapsed_seconds if result else None,
        error=entry.get("error"),
    )


# ---------------------------------------------------------------------------
# Batch endpoints (must be registered before /{task_id} to avoid capture)
# ---------------------------------------------------------------------------

_MIN_CORNER_AREA_RATIO = 0.35


def _detect_corners_for_image(img_bgr: np.ndarray) -> tuple[Corners, float]:
    """Detect corners; fall back to full-image corners if detection fails."""
    h, w = img_bgr.shape[:2]
    full = Corners(tl=(0, 0), tr=(w, 0), br=(w, h), bl=(0, h))

    corners = detect_corners(img_bgr)
    if corners is None:
        return full, 0.0

    img_area = float(h * w)
    pts = corners.as_array().astype(np.float32)
    area = float(abs(cv2.contourArea(pts)))
    ratio = area / img_area if img_area > 0 else 0.0
    if ratio < _MIN_CORNER_AREA_RATIO:
        return full, 0.0

    return corners, 1.0


@router.post("/batch/prepare", response_model=BatchPrepareResponse)
async def batch_prepare(
    files: List[UploadFile] = File(...),
) -> BatchPrepareResponse:
    """Upload images, detect corners for each, and store originals for later submission.

    Returns detected corners (auto) — the client may override any of them via
    ``POST /corner/correct`` before calling ``POST /ocr/batch/submit``.
    """
    from api.routes.corner import _pending_images

    if not files:
        raise HTTPException(400, "No files provided")
    if len(files) > 50:
        raise HTTPException(400, "Maximum 50 files per batch")

    items: List[BatchPrepareItem] = []
    for f in files:
        contents = await f.read()
        arr = np.frombuffer(contents, dtype=np.uint8)
        img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img_bgr is None:
            logger.warning("Skipping invalid image in batch/prepare: %s", f.filename)
            continue

        corners, confidence = _detect_corners_for_image(img_bgr)
        task_id = uuid.uuid4().hex[:12]
        # Store original so /corner/correct (manual override) or batch/submit can warp it
        _pending_images[task_id] = img_bgr

        pts = corners.to_list()
        items.append(
            BatchPrepareItem(
                task_id=task_id,
                filename=f.filename or "unknown",
                corners=[Point(x=p[0], y=p[1]) for p in pts],
                confidence=confidence,
            )
        )

    if not items:
        raise HTTPException(400, "No valid images found in uploaded files")

    return BatchPrepareResponse(items=items)


@router.post("/batch/submit", response_model=BatchSubmitResponse)
async def batch_submit(
    req: BatchSubmitRequest,
    pipeline: OCRPipeline = Depends(get_pipeline),
) -> BatchSubmitResponse:
    """Warp each image using the provided (auto or user-adjusted) corners and start OCR.

    Each ``task_id`` in *corrections* must have been previously prepared via
    ``POST /ocr/batch/prepare`` (or have its corners overridden via
    ``POST /corner/correct``).
    """
    from api.routes.corner import _pending_images

    if not req.corrections:
        raise HTTPException(400, "No corrections provided")

    opts = OCROptions(
        auto_rotate=req.auto_rotate,
        remove_print=req.remove_print,
        auto_split=req.auto_split,
    )
    batch_id = uuid.uuid4().hex[:12]
    task_items: List[BatchTaskItem] = []
    loop = asyncio.get_running_loop()

    for corr in req.corrections:
        # If the image was already warped by /corner/correct, use it as-is.
        # If it's still the original (not manually overridden), apply auto warp now.
        img_bgr = _pending_images.pop(corr.task_id, None)
        if img_bgr is None:
            logger.warning("task_id %s not found in pending images — skipping", corr.task_id)
            continue

        pts = [(p.x, p.y) for p in corr.corners]
        corners = Corners(tl=pts[0], tr=pts[1], br=pts[2], bl=pts[3])
        warped = warp_perspective(img_bgr, corners)

        _tasks[corr.task_id] = _task_entry(TaskStatus.processing)

        loop.run_in_executor(
            None,
            _run_batch_ocr,
            corr.task_id,
            batch_id,
            warped,
            pipeline,
            opts,
            loop,
        )

        task_items.append(
            BatchTaskItem(
                task_id=corr.task_id,
                filename="",  # filename not needed post-submission
                status=TaskStatus.processing,
            )
        )

    if not task_items:
        raise HTTPException(400, "No valid tasks to submit")

    _batches[batch_id] = {
        "task_ids": [t.task_id for t in task_items],
        "filenames": {},
    }

    return BatchSubmitResponse(batch_id=batch_id, tasks=task_items)


def _run_batch_ocr(
    task_id: str,
    batch_id: str,
    img_bgr: np.ndarray,
    pipeline: OCRPipeline,
    opts: OCROptions,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Blocking OCR for a batch item — broadcasts per-task AND batch progress."""

    def _on_progress(stage: str, progress: float) -> None:
        _tasks[task_id]["progress"] = progress
        asyncio.run_coroutine_threadsafe(
            broadcast_progress(task_id, stage, progress),
            loop,
        )
        asyncio.run_coroutine_threadsafe(
            _broadcast_batch_status(batch_id),
            loop,
        )

    try:
        pil_img = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
        result = pipeline.run(
            pil_img,
            auto_rotate=opts.auto_rotate,
            remove_print=opts.remove_print,
            auto_split=opts.auto_split,
            on_progress=_on_progress,
        )
        _tasks[task_id]["status"] = TaskStatus.completed
        _tasks[task_id]["progress"] = 1.0
        _tasks[task_id]["result"] = result
        asyncio.run_coroutine_threadsafe(
            broadcast_progress(task_id, "完成", 1.0, status="completed"),
            loop,
        )
    except Exception as e:
        logger.exception("OCR failed for task %s (batch %s)", task_id, batch_id)
        _tasks[task_id]["status"] = TaskStatus.failed
        _tasks[task_id]["error"] = str(e)
        asyncio.run_coroutine_threadsafe(
            broadcast_progress(task_id, "失敗", 0.0, status="failed"),
            loop,
        )

    asyncio.run_coroutine_threadsafe(
        _broadcast_batch_status(batch_id),
        loop,
    )


async def _broadcast_batch_status(batch_id: str) -> None:
    """Compute and broadcast aggregated batch progress."""
    batch = _batches.get(batch_id)
    if not batch:
        return
    task_ids = batch["task_ids"]
    total = len(task_ids)
    completed = sum(1 for tid in task_ids if _tasks.get(tid, {}).get("status") == TaskStatus.completed)
    failed = sum(1 for tid in task_ids if _tasks.get(tid, {}).get("status") == TaskStatus.failed)
    progress_sum = sum(_tasks.get(tid, {}).get("progress", 0.0) for tid in task_ids)
    avg_progress = progress_sum / total if total > 0 else 0.0

    done = completed + failed
    if done == total:
        status = "completed"
    else:
        status = "processing"

    await broadcast_batch_progress(
        batch_id,
        progress=avg_progress,
        completed=completed,
        failed=failed,
        total=total,
        status=status,
    )


@router.get("/batch/{batch_id}", response_model=BatchStatusResponse)
def batch_status(batch_id: str) -> BatchStatusResponse:
    """Poll batch status and retrieve all task results."""
    batch = _batches.get(batch_id)
    if batch is None:
        raise HTTPException(404, "Batch not found")

    task_ids = batch["task_ids"]
    total = len(task_ids)
    tasks = [_build_task_response(tid) for tid in task_ids]
    completed = sum(1 for t in tasks if t.status == TaskStatus.completed)
    failed = sum(1 for t in tasks if t.status == TaskStatus.failed)
    processing = sum(1 for t in tasks if t.status in (TaskStatus.pending, TaskStatus.processing))
    progress_sum = sum(t.progress for t in tasks)
    avg_progress = progress_sum / total if total > 0 else 0.0

    return BatchStatusResponse(
        batch_id=batch_id,
        total=total,
        completed=completed,
        failed=failed,
        processing=processing,
        progress=round(avg_progress, 4),
        tasks=tasks,
    )


# ---------------------------------------------------------------------------
# Single task status (after batch routes to avoid /{task_id} capturing "batch")
# ---------------------------------------------------------------------------


@router.get("/{task_id}", response_model=OCRStatusResponse)
def status(task_id: str) -> OCRStatusResponse:
    """Poll task status and retrieve completed results."""
    entry = _tasks.get(task_id)
    if entry is None:
        raise HTTPException(404, "Task not found")
    return _build_task_response(task_id)
