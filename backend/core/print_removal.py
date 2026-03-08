"""
Print-text removal — detect and crop away printed headers / margins.

Extracted from v2 ``print_text_remover.py`` (2076 lines → ~200 lines core).
The 1200+ lines of matplotlib visualisation code are **not** migrated.

Algorithm summary
-----------------
1. Extract centroids from the CRAFT heatmap (reuses ``core.rotation.extract_centroids``).
2. Compute **weighted** nearest-neighbour distances (X axis scaled by *x_weight*
   to increase sensitivity to vertical alignment).
3. Classify centroids: printed text has both **small vertical angle** to its
   nearest neighbour *and* moderate distance.  Hand-written text has larger,
   more variable distances.
4. Find the boundary between the printed and handwritten regions and crop.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Optional, Tuple

import cv2
import numpy as np
from scipy.spatial.distance import cdist

from core.rotation import extract_centroids

logger = logging.getLogger(__name__)


@dataclass
class PrintRemovalResult:
    """Outcome of printed-text detection and removal."""

    image: np.ndarray
    status: str                              # "success" | "too_few_*" | …
    boundary: int = 0
    direction: str = "horizontal"
    num_print: int = 0
    num_handwriting: int = 0


def detect_and_remove(
    image: np.ndarray,
    heatmap: np.ndarray,
    *,
    direction: Literal["vertical", "horizontal"] = "horizontal",
    x_weight: float = 3.0,
    angle_threshold: float = 3.0,
    row_ratio_threshold: float = 0.8,
) -> PrintRemovalResult:
    """Detect and crop away the printed-text region.

    Args:
        image: Original BGR image.
        heatmap: CRAFT heatmap **already resized** to ``image.shape[:2]``.
        direction: ``"vertical"`` → print at top; ``"horizontal"`` → print at right.
        x_weight: Weight multiplier for X-axis distances (increases vertical
            alignment sensitivity).
        angle_threshold: Maximum angle (degrees) from vertical to count as
            "vertically aligned".
        row_ratio_threshold: Fraction of points in a row/column that must be
            classified as printed to mark the whole row/column.

    Returns:
        ``PrintRemovalResult`` with the cropped image and metadata.
    """
    h, w = image.shape[:2]

    # --- Step 1: centroids --------------------------------------------------
    centroids = extract_centroids(heatmap, percentile=90.0)
    if len(centroids) < 10:
        return PrintRemovalResult(image=image, status="too_few_centroids")

    # --- Step 2: weighted nearest-neighbour distances -----------------------
    weighted = centroids.copy()
    weighted[:, 0] *= x_weight

    dists_w = cdist(weighted, weighted)
    np.fill_diagonal(dists_w, np.inf)
    nn_idx = np.argmin(dists_w, axis=1)

    dists_raw = cdist(centroids, centroids)
    np.fill_diagonal(dists_raw, np.inf)
    nn_dists_raw = np.min(dists_raw, axis=1)

    # --- Step 3: classify ---------------------------------------------------
    vectors = centroids[nn_idx] - centroids
    vert_angles = np.abs(np.degrees(np.arctan2(vectors[:, 0], vectors[:, 1])))
    vert_angles = np.minimum(vert_angles, 180 - vert_angles)

    nn_dists_w = np.min(dists_w, axis=1)
    dist_upper = nn_dists_w.mean()

    is_vertical = vert_angles < angle_threshold
    is_dist_ok = nn_dists_raw < dist_upper
    is_print = is_vertical & is_dist_ok

    print_pts = centroids[is_print]
    handwriting_pts = centroids[~is_print]

    if len(print_pts) < 3:
        return PrintRemovalResult(image=image, status="too_few_print_points")

    # --- Step 4: determine boundary -----------------------------------------
    if direction == "vertical":
        boundary = int(print_pts[:, 1].max()) + int(h * 0.02)
        boundary = min(boundary, h)
        cropped = image[boundary:, :]
    else:
        # For horizontal: find the column with highest print ratio
        col_width = max(1, int(np.percentile(nn_dists_raw, 50)))
        col_coord = centroids[:, 0]
        num_cols = int((col_coord.max() - col_coord.min()) / col_width) + 1
        col_idx = ((col_coord - col_coord.min()) / col_width).astype(int)
        col_idx = np.clip(col_idx, 0, num_cols - 1)

        best_col_x = None
        best_count = 0
        for ci in range(num_cols):
            mask = col_idx == ci
            if mask.sum() < 3:
                continue
            ratio = is_print[mask].sum() / mask.sum()
            if ratio >= row_ratio_threshold and mask.sum() > best_count:
                best_count = int(mask.sum())
                best_col_x = float(col_coord[mask].min())

        if best_col_x is not None:
            boundary = max(0, int(best_col_x) - int(col_width * 0.02))
        else:
            boundary = max(0, int(print_pts[:, 0].min()))

        cropped = image[:, :boundary]

    return PrintRemovalResult(
        image=cropped,
        status="success",
        boundary=boundary,
        direction=direction,
        num_print=len(print_pts),
        num_handwriting=len(handwriting_pts),
    )
