"""Corner detection and perspective correction routes."""

from __future__ import annotations

import uuid
import logging

import cv2
import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile

from api.schemas import (
    CornerCorrectRequest,
    CornerCorrectResponse,
    CornerDetectResponse,
    Point,
)
from core.perspective import Corners, detect_corners, warp_perspective

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/corner", tags=["corner"])

# In-memory store for pending corner corrections (task_id → BGR image)
# In production, replace with Redis or a proper cache.
_pending_images: dict[str, np.ndarray] = {}


def _full_image_corners(img_bgr: np.ndarray) -> Corners:
    h, w = img_bgr.shape[:2]
    return Corners(tl=(0, 0), tr=(w, 0), br=(w, h), bl=(0, h))


def _corner_area_ratio(corners: Corners, img_bgr: np.ndarray) -> float:
    img_h, img_w = img_bgr.shape[:2]
    img_area = float(img_h * img_w)
    if img_area <= 0:
        return 0.0
    pts = corners.as_array().astype(np.float32)
    area = float(abs(cv2.contourArea(pts)))
    return area / img_area


@router.post("/detect", response_model=CornerDetectResponse)
async def detect(file: UploadFile = File(...)) -> CornerDetectResponse:
    """Upload an image and auto-detect paper corners."""
    contents = await file.read()
    arr = np.frombuffer(contents, dtype=np.uint8)
    img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise HTTPException(400, "Invalid image")

    min_corner_area_ratio = 0.35
    corners = detect_corners(img_bgr)
    confidence = 1.0
    if corners is None:
        corners = _full_image_corners(img_bgr)
        confidence = 0.0
    else:
        area_ratio = _corner_area_ratio(corners, img_bgr)
        if area_ratio < min_corner_area_ratio:
            logger.warning(
                "Detected corner area too small (ratio=%.3f < %.3f), fallback to full image",
                area_ratio,
                min_corner_area_ratio,
            )
            corners = _full_image_corners(img_bgr)
            confidence = 0.0

    task_id = uuid.uuid4().hex[:12]
    _pending_images[task_id] = img_bgr

    pts = corners.to_list()
    return CornerDetectResponse(
        task_id=task_id,
        corners=[Point(x=p[0], y=p[1]) for p in pts],
        confidence=confidence,
    )


@router.post("/correct", response_model=CornerCorrectResponse)
async def correct(req: CornerCorrectRequest) -> CornerCorrectResponse:
    """Apply user-adjusted corners and warp the image."""
    img_bgr = _pending_images.pop(req.task_id, None)
    if img_bgr is None:
        raise HTTPException(404, "Task not found or already consumed")

    pts = [(p.x, p.y) for p in req.corners]
    corners = Corners(
        tl=pts[0],
        tr=pts[1],
        br=pts[2],
        bl=pts[3],
    )

    warped = warp_perspective(img_bgr, corners)
    # Store the warped image back so the OCR route can use it
    _pending_images[req.task_id] = warped

    return CornerCorrectResponse(corrected=True)
