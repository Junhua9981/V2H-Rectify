"""
Perspective correction — detect document corners and warp to rectangle.

This is a **new** module (not in v2).  It lets users:

1. Upload a photo of a manuscript page taken at an angle.
2. Auto-detect the four corners of the page via edge / contour analysis.
3. Optionally adjust the corners interactively (handled by the frontend).
4. Apply a perspective warp to produce a flat, axis-aligned image.

The algorithm pipeline:
    a. Gaussian blur → Canny edge detection.
    b. Find contours → approximate to quadrilateral.
    c. Order corners (TL, TR, BR, BL).
    d. ``cv2.getPerspectiveTransform`` + ``cv2.warpPerspective``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Corners:
    """Four document corners in order: top-left, top-right, bottom-right, bottom-left."""

    tl: Tuple[float, float]
    tr: Tuple[float, float]
    br: Tuple[float, float]
    bl: Tuple[float, float]

    def as_array(self) -> np.ndarray:
        """Return a ``(4, 2)`` float32 array suitable for ``getPerspectiveTransform``."""
        return np.array([self.tl, self.tr, self.br, self.bl], dtype=np.float32)

    def to_list(self) -> List[List[float]]:
        return [list(self.tl), list(self.tr), list(self.br), list(self.bl)]

    @classmethod
    def from_list(cls, pts: List[List[float]]) -> "Corners":
        return cls(tl=tuple(pts[0]), tr=tuple(pts[1]), br=tuple(pts[2]), bl=tuple(pts[3]))


# ---------------------------------------------------------------------------
# Corner detection
# ---------------------------------------------------------------------------

def _order_points(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as [TL, TR, BR, BL].

    Strategy: sum of coords is smallest for TL and largest for BR;
    difference (y - x) is smallest for TR and largest for BL.
    """
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    rect[0] = pts[np.argmin(s)]   # TL
    rect[2] = pts[np.argmax(s)]   # BR
    rect[1] = pts[np.argmin(d)]   # TR
    rect[3] = pts[np.argmax(d)]   # BL
    return rect


def detect_corners(
    image: np.ndarray,
    *,
    blur_ksize: int = 5,
    canny_low: int = 50,
    canny_high: int = 150,
    min_area_ratio: float = 0.15,
) -> Optional[Corners]:
    """Auto-detect the four corners of a document page in *image*.

    Args:
        image: BGR input image.
        blur_ksize: Gaussian blur kernel size.
        canny_low / canny_high: Canny edge thresholds.
        min_area_ratio: Minimum contour area as fraction of image area to be
            considered a page candidate.

    Returns:
        ``Corners`` if a quadrilateral is found, else ``None``.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    blurred = cv2.GaussianBlur(gray, (blur_ksize, blur_ksize), 0)
    edges = cv2.Canny(blurred, canny_low, canny_high)

    # Dilate to close small gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges = cv2.dilate(edges, kernel, iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    img_area = image.shape[0] * image.shape[1]
    min_area = img_area * min_area_ratio

    # Sort contours by area descending; try to approximate each as a quad.
    for cnt in sorted(contours, key=cv2.contourArea, reverse=True):
        area = cv2.contourArea(cnt)
        if area < min_area:
            break  # remaining are even smaller

        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        if len(approx) == 4:
            ordered = _order_points(approx.reshape(4, 2))
            return Corners(
                tl=tuple(ordered[0]),
                tr=tuple(ordered[1]),
                br=tuple(ordered[2]),
                bl=tuple(ordered[3]),
            )

    # Fallback: use the convex hull of the largest contour
    hull = cv2.convexHull(contours[0])
    if len(hull) >= 4:
        peri = cv2.arcLength(hull, True)
        approx = cv2.approxPolyDP(hull, 0.02 * peri, True)
        if len(approx) == 4:
            ordered = _order_points(approx.reshape(4, 2))
            return Corners(
                tl=tuple(ordered[0]),
                tr=tuple(ordered[1]),
                br=tuple(ordered[2]),
                bl=tuple(ordered[3]),
            )

    return None


# ---------------------------------------------------------------------------
# Perspective warp
# ---------------------------------------------------------------------------

def warp_perspective(
    image: np.ndarray,
    corners: Corners,
    *,
    output_size: Optional[Tuple[int, int]] = None,
) -> np.ndarray:
    """Warp *image* so that *corners* map to a flat rectangle.

    Args:
        image: BGR input.
        corners: The four document corners.
        output_size: ``(width, height)`` of the output.  If ``None``, the
            size is computed from the corner distances.

    Returns:
        The perspective-corrected image.
    """
    src = corners.as_array()

    if output_size is None:
        # Compute output dimensions from corner distances
        w_top = np.linalg.norm(src[1] - src[0])
        w_bot = np.linalg.norm(src[2] - src[3])
        width = int(max(w_top, w_bot))

        h_left = np.linalg.norm(src[3] - src[0])
        h_right = np.linalg.norm(src[2] - src[1])
        height = int(max(h_left, h_right))
    else:
        width, height = output_size

    dst = np.array([
        [0, 0],
        [width - 1, 0],
        [width - 1, height - 1],
        [0, height - 1],
    ], dtype=np.float32)

    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(image, M, (width, height), borderValue=(255, 255, 255))
