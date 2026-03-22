"""OCR routes — submit image, poll status, get results."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Dict

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image
import cv2
import numpy as np

from api.deps import get_pipeline
from api.schemas import OCROptions, OCRStatusResponse, OCRSubmitResponse, TaskStatus, ColumnData
from api.ws import broadcast_progress
from core.image_utils import pil_to_bgr
from services.ocr_pipeline import OCRPipeline, OCRResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ocr", tags=["ocr"])

# In-memory task store.  Production → Redis.
_tasks: Dict[str, dict] = {}


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


@router.get("/{task_id}", response_model=OCRStatusResponse)
def status(task_id: str) -> OCRStatusResponse:
    """Poll task status and retrieve completed results."""
    entry = _tasks.get(task_id)
    if entry is None:
        raise HTTPException(404, "Task not found")

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
