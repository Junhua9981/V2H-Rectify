"""
Grid extraction — projection-based row / column detection for essay paper.

Extracted from v2 ``enhanced_grid_extractor.py`` (505 lines → ~200 lines core).
Visualisation helpers are **not** migrated (kept in a separate debug utility).

Pipeline
--------
1. Build a character mask (from a CRAFT heatmap **or** traditional connected
   components).
2. Compute vertical / horizontal projection histograms.
3. Find peaks → determine grid lines → generate grid boxes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np
from scipy.signal import find_peaks

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GridBox:
    """One cell in the detected grid."""

    x: int
    y: int
    w: int
    h: int
    row: int
    col: int


@dataclass
class GridResult:
    """Full result of grid extraction."""

    boxes: List[GridBox] = field(default_factory=list)
    boxes_by_column: List[List[Tuple[int, int, int, int]]] = field(default_factory=list)
    col_lines: List[int] = field(default_factory=list)
    row_lines: List[int] = field(default_factory=list)
    char_mask: Optional[np.ndarray] = None


# ---------------------------------------------------------------------------
# Character mask
# ---------------------------------------------------------------------------

def character_mask_from_heatmap(heatmap: np.ndarray) -> np.ndarray:
    """Create a character-presence mask directly from a resized CRAFT heatmap.

    The raw heatmap values are used as the mask (no thresholding) — the
    projection histograms operate on the continuous density.
    """
    return heatmap


def character_mask_traditional(image_gray: np.ndarray) -> np.ndarray:
    """Fallback character mask using adaptive thresholding + connected components."""
    blur = cv2.GaussianBlur(image_gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 15, 10,
    )
    kernel = np.ones((2, 2), np.uint8)
    opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(opening, connectivity=8)
    min_area, max_area = 50, image_gray.size // 10
    mask = np.zeros_like(image_gray)

    for i in range(1, num_labels):
        x, y, w, h, area = stats[i]
        if not (min_area < area < max_area):
            continue
        ar = w / h if h > 0 else 0
        if 0.25 < ar < 4.0:
            mask[y : y + h, x : x + w] = 255

    close_k = np.ones((10, 10), np.uint8)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_k)


# ---------------------------------------------------------------------------
# Peak / line detection
# ---------------------------------------------------------------------------

def _find_peaks(data: np.ndarray, *, height_frac: float = 0.15, distance_div: int = 100) -> np.ndarray:
    """Find peaks in a 1-D projection histogram."""
    max_val = data.max()
    if max_val == 0:
        return np.array([], dtype=int)
    peaks, _ = find_peaks(
        data,
        height=max_val * height_frac,
        distance=max(1, len(data) // distance_div),
        prominence=max_val // 100,
    )
    return peaks


def _peaks_to_grid_lines(peaks: np.ndarray) -> List[int]:
    """Convert peak positions to grid-line positions (midpoints + extrapolated edges)."""
    if len(peaks) < 2:
        return []
    avg_dist = float(np.mean(np.diff(peaks)))
    lines = [(int(peaks[i]) + int(peaks[i + 1])) // 2 for i in range(len(peaks) - 1)]
    lines.insert(0, int(peaks[0] - avg_dist / 2))
    lines.append(int(peaks[-1] + avg_dist / 2))
    return lines


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_grid(
    image_gray: np.ndarray,
    char_mask: np.ndarray,
) -> GridResult:
    """Extract a grid of character boxes from *image_gray* using *char_mask*.

    Args:
        image_gray: Greyscale version of the (pre-processed) image.
        char_mask: Character-presence mask (from CRAFT or traditional method).

    Returns:
        ``GridResult`` with boxes ordered right-to-left, top-to-bottom
        (standard Chinese vertical writing order).

    Raises:
        RuntimeError: If not enough rows or columns are detected.
    """
    h, w = image_gray.shape[:2]

    vert_proj = np.sum(char_mask, axis=0)
    horiz_proj = np.sum(char_mask, axis=1)

    col_peaks = _find_peaks(vert_proj, distance_div=100)
    row_peaks = _find_peaks(horiz_proj, distance_div=60)

    col_lines = _peaks_to_grid_lines(col_peaks)
    row_lines = _peaks_to_grid_lines(row_peaks)

    if not col_lines or not row_lines:
        raise RuntimeError("Grid detection failed — not enough peaks detected.")

    boxes: list[GridBox] = []
    boxes_by_column: list[list[tuple[int, int, int, int]]] = []

    # Right-to-left (Chinese vertical writing order)
    for c_idx in range(len(col_lines) - 2, -1, -1):
        x1, x2 = col_lines[c_idx], col_lines[c_idx + 1]
        col_boxes: list[tuple[int, int, int, int]] = []
        for r_idx in range(len(row_lines) - 1):
            y1, y2 = row_lines[r_idx], row_lines[r_idx + 1]
            bx = max(0, min(x1, x2))
            by = max(0, min(y1, y2))
            bw = abs(x2 - x1)
            bh = abs(y2 - y1)
            boxes.append(GridBox(
                x=bx, y=by, w=bw, h=bh,
                row=r_idx,
                col=len(col_lines) - 2 - c_idx,
            ))
            col_boxes.append((bx, by, bw, bh))
        boxes_by_column.append(col_boxes)

    return GridResult(
        boxes=boxes,
        boxes_by_column=boxes_by_column,
        col_lines=col_lines,
        row_lines=row_lines,
        char_mask=char_mask,
    )
