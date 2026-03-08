"""
CRAFT text detector — clean wrapper around EasyOCR's CRAFT model.

Extracted from v2 ``craft_detector.py``:
- Removed ``os.environ['CUDA_VISIBLE_DEVICES']`` global side-effect.
- Detection results are returned as a ``DetectionResult`` dataclass instead
  of being stashed on mutable instance attributes.
- Device selection is injected at construction time; no hardcoded ``cuda:7``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Tuple

import cv2
import numpy as np
import torch

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DetectionResult:
    """Immutable result of a single CRAFT detection pass.

    Carries everything downstream modules need so we never re-run inference.
    """

    boxes: list
    polys: list
    score_text: np.ndarray
    score_link: np.ndarray
    ratio_h: float
    ratio_w: float


# ---------------------------------------------------------------------------
# Heatmap helpers (pure functions — no detector instance needed)
# ---------------------------------------------------------------------------

def resize_heatmap(
    score_text: np.ndarray,
    ratio_w: float,
    ratio_h: float,
    target_shape: Tuple[int, int],
) -> np.ndarray:
    """Rescale a CRAFT score map back to the original image size.

    Args:
        score_text: Raw CRAFT text-score heatmap.
        ratio_w: Width scaling ratio returned by CRAFT preprocessing.
        ratio_h: Height scaling ratio returned by CRAFT preprocessing.
        target_shape: ``(height, width)`` of the original image.

    Returns:
        Heatmap with shape ``target_shape``.
    """
    heatmap = cv2.resize(
        score_text,
        None,
        None,
        fx=ratio_w * 2,
        fy=ratio_h * 2,
        interpolation=cv2.INTER_LINEAR,
    )
    h, w = target_shape
    return heatmap[:h, :w]


# ---------------------------------------------------------------------------
# Detector class
# ---------------------------------------------------------------------------

class CRAFTDetector:
    """Thin wrapper around EasyOCR's CRAFT network.

    Usage::

        detector = CRAFTDetector(device="cuda:0")
        result: DetectionResult = detector.detect(image_bgr)
        heatmap = resize_heatmap(
            result.score_text, result.ratio_w, result.ratio_h, image_bgr.shape[:2]
        )
    """

    def __init__(
        self,
        languages: List[str] | None = None,
        gpu: bool = True,
        device: str = "cuda:7",
    ) -> None:
        if languages is None:
            languages = ["ch_tra"]

        self.device = device if gpu and torch.cuda.is_available() else "cpu"

        # EasyOCR handles its own model download / caching.
        import easyocr

        # Pass device string (e.g. "cuda:7") instead of bool so that
        # EasyOCR uses the *specific* GPU rather than the default "cuda".
        # When ``gpu`` is not a bool, easyocr.Reader stores it directly
        # as ``self.device`` (see easyocr.py line ~80).
        self.reader = easyocr.Reader(languages, gpu=self.device)

        # EasyOCR's get_detector wraps the CRAFT network in
        # ``torch.nn.DataParallel`` **without** ``device_ids``,
        # which silently replicates the model onto every visible GPU.
        # We unwrap it and keep only a single-device copy.
        if self.device != "cpu" and hasattr(self.reader, "detector"):
            det = self.reader.detector
            if isinstance(det, torch.nn.DataParallel):
                det = det.module
            det = det.to(self.device)
            self.reader.detector = det

        logger.info("CRAFTDetector initialised on %s", self.device)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def detect(
        self,
        image: np.ndarray,
        *,
        canvas_size: int = 2560,
        mag_ratio: float = 1.0,
        text_threshold: float = 0.7,
        link_threshold: float = 0.4,
        low_text: float = 0.4,
    ) -> DetectionResult:
        """Run CRAFT detection and return an immutable ``DetectionResult``."""
        from easyocr.detection import (
            adjustResultCoordinates,
            getDetBoxes,
            normalizeMeanVariance,
            resize_aspect_ratio,
        )

        net = self.reader.detector

        # ---------- preprocessing ----------
        img_resized, target_ratio, _ = resize_aspect_ratio(
            image, canvas_size, interpolation=cv2.INTER_LINEAR, mag_ratio=mag_ratio
        )
        ratio_h = ratio_w = 1 / target_ratio

        x = np.transpose(normalizeMeanVariance(img_resized), (2, 0, 1))
        x = torch.from_numpy(np.array([x])).to(self.device)

        # ---------- inference ----------
        with torch.no_grad():
            y, _ = net(x)

        out = y[0]
        score_text = out[:, :, 0].cpu().data.numpy()
        score_link = out[:, :, 1].cpu().data.numpy()

        # ---------- postprocessing ----------
        boxes, polys, _ = getDetBoxes(
            score_text, score_link, text_threshold, link_threshold, low_text, False, False
        )
        boxes = adjustResultCoordinates(boxes, ratio_w, ratio_h)
        polys = adjustResultCoordinates(polys, ratio_w, ratio_h)

        for k in range(len(polys)):
            if polys[k] is None:
                polys[k] = boxes[k]

        return DetectionResult(
            boxes=list(boxes),
            polys=list(polys),
            score_text=score_text,
            score_link=score_link,
            ratio_h=ratio_h,
            ratio_w=ratio_w,
        )
