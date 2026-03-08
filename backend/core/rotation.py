"""
Image rotation / skew correction — pure algorithm functions.

Extracted from v2 ``rotation_corrector.py`` (824 lines → ~180 lines of core logic).

The 300-line ``_detect_skew_angle`` God Method has been decomposed into:
    1. ``extract_centroids``  — binary threshold → connected components → centres.
    2. ``cluster_centroids``  — DBSCAN (with simple fallback).
    3. ``estimate_angle``     — minAreaRect + PCA + linear regression fusion.
    4. ``correct_skew``       — single entry point that chains 1-2-3 + affine warp.

All functions are pure: numpy in → numpy / float out.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import cv2
import numpy as np
from scipy.signal import find_peaks

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Centroid extraction
# ---------------------------------------------------------------------------

def extract_centroids(
    heatmap: np.ndarray,
    *,
    min_area: int = 10,
    percentile: float = 90.0,
) -> np.ndarray:
    """Extract text-region centroids from a CRAFT heatmap.

    Args:
        heatmap: Float heatmap resized to original image dimensions.
        min_area: Minimum connected-component area to keep.
        percentile: Percentile threshold for binarisation.

    Returns:
        ``(N, 2)`` array of ``[cx, cy]`` centroids.
    """
    heatmap_u8 = (heatmap * 255).astype(np.uint8)
    nonzero = heatmap_u8[heatmap_u8 > 0]
    if len(nonzero) == 0:
        return np.empty((0, 2))

    thresh_val = max(50, int(np.percentile(nonzero, percentile)))
    _, binary = cv2.threshold(heatmap_u8, thresh_val, 255, cv2.THRESH_BINARY)

    num_labels, _, stats, centroids_all = cv2.connectedComponentsWithStats(binary, connectivity=8)

    valid = []
    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            valid.append(centroids_all[i])

    return np.array(valid) if valid else np.empty((0, 2))


# ---------------------------------------------------------------------------
# 2. Clustering
# ---------------------------------------------------------------------------

def cluster_centroids(
    centroids: np.ndarray,
    *,
    min_samples: int = 3,
) -> List[np.ndarray]:
    """Group centroids into clusters (rows / columns of text).

    Uses DBSCAN with an adaptive ``eps`` derived from nearest-neighbour
    distances.  Falls back to a simple Y-sorted grouping when scikit-learn
    is unavailable.

    Returns:
        List of ``(M, 2)`` arrays, one per cluster.
    """
    if len(centroids) < min_samples:
        return []

    try:
        from sklearn.cluster import DBSCAN
        from scipy.spatial.distance import cdist

        dists = cdist(centroids, centroids)
        np.fill_diagonal(dists, np.inf)
        nn_dists = np.min(dists, axis=1)
        eps = nn_dists.mean() * 3.0

        labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(centroids)
        unique = set(labels)
        unique.discard(-1)

        clusters = []
        for lab in unique:
            pts = centroids[labels == lab]
            if len(pts) >= min_samples:
                clusters.append(pts)
        return clusters

    except ImportError:
        logger.warning("scikit-learn not available; using simple Y-sort grouping")
        return _cluster_simple(centroids, min_samples)


def _cluster_simple(centroids: np.ndarray, min_points: int) -> List[np.ndarray]:
    """Fallback grouping when DBSCAN is unavailable."""
    order = np.argsort(centroids[:, 1])
    sorted_c = centroids[order]
    y_diffs = np.diff(sorted_c[:, 1])
    gap = max(np.median(y_diffs[y_diffs > np.percentile(y_diffs, 60)]) / 2, 5)

    groups: list[list] = [[sorted_c[0].tolist()]]
    for i in range(1, len(sorted_c)):
        if abs(sorted_c[i, 1] - groups[-1][-1][1]) <= gap:
            groups[-1].append(sorted_c[i].tolist())
        else:
            groups.append([sorted_c[i].tolist()])

    return [np.array(g) for g in groups if len(g) >= min_points]


# ---------------------------------------------------------------------------
# 3. Angle estimation (multi-method fusion)
# ---------------------------------------------------------------------------

def _angle_minarearect(pts: np.ndarray) -> float:
    rect = cv2.minAreaRect(pts.astype(np.float32))
    angle = rect[2]
    w, h = rect[1]
    if w < h:
        angle += 90
    if angle > 45:
        angle -= 90
    elif angle < -45:
        angle += 90
    return angle


def _angle_pca(pts: np.ndarray) -> float:
    centered = pts - pts.mean(axis=0)
    cov = np.cov(centered.T)
    eigenvalues, eigenvectors = np.linalg.eig(cov)
    main_axis = eigenvectors[:, np.argmax(eigenvalues)]
    angle = np.degrees(np.arctan2(main_axis[1], main_axis[0]))
    if angle > 45:
        angle -= 90
    elif angle < -45:
        angle += 90
    return angle


def _angle_linreg(pts: np.ndarray) -> Optional[float]:
    from scipy.stats import linregress

    xs, ys = pts[:, 0], pts[:, 1]
    x_range = xs.max() - xs.min()
    y_range = ys.max() - ys.min()

    try:
        if x_range > y_range * 1.5:
            slope, _, r, _, _ = linregress(xs, ys)
            if abs(r) > 0.3:
                return np.degrees(np.arctan(slope))
        elif y_range > x_range * 1.5:
            slope, _, r, _, _ = linregress(ys, xs)
            if abs(r) > 0.3:
                angle = 90 - np.degrees(np.arctan(slope))
                if angle > 45:
                    angle -= 90
                elif angle < -45:
                    angle += 90
                return angle
    except Exception:
        pass
    return None


def estimate_angle(clusters: List[np.ndarray]) -> Optional[float]:
    """Estimate skew angle from clustered centroids using multi-method fusion.

    Each cluster votes via minAreaRect, PCA and (optionally) linear regression.
    The final angle is a consistency-weighted average with peak-histogram
    verification.

    Returns:
        Skew angle in degrees (clockwise positive), or ``None``.
    """
    if len(clusters) < 3:
        return None

    cluster_angles: list[float] = []
    consistencies: list[float] = []

    for pts in clusters:
        methods: dict[str, float] = {}
        methods["rect"] = _angle_minarearect(pts)
        methods["pca"] = _angle_pca(pts)
        lr = _angle_linreg(pts)
        if lr is not None:
            methods["lr"] = lr

        vals = list(methods.values())
        if len(vals) < 2:
            continue

        med = float(np.median(vals))
        if abs(med) < 45:
            cluster_angles.append(med)
            consistencies.append(float(np.std(vals)))

    if len(cluster_angles) < 3:
        return None

    # Weighted average (lower std → higher weight)
    weights = np.array([1.0 / (c + 1.0) for c in consistencies])
    weights /= weights.sum()
    weighted_avg = float(np.average(cluster_angles, weights=weights))
    median_angle = float(np.median(cluster_angles))

    # Histogram peak verification
    hist, bin_edges = np.histogram(cluster_angles, bins=30)
    peaks, _ = find_peaks(hist)
    if len(peaks) > 0:
        dominant = peaks[np.argmax(hist[peaks])]
        if hist[dominant] > 1:
            peak_angle = (bin_edges[dominant] + bin_edges[dominant + 1]) / 2
            return float(np.clip(-peak_angle, -45, 45))

    if abs(weighted_avg - median_angle) < 3.0:
        return float(np.clip(-weighted_avg, -45, 45))
    return float(np.clip(-median_angle, -45, 45))


# ---------------------------------------------------------------------------
# 4. Image rotation
# ---------------------------------------------------------------------------

def rotate_image(image: np.ndarray, angle: float) -> np.ndarray:
    """Rotate *image* by *angle* degrees (small angle, white-fill borders)."""
    if abs(angle) < 0.1:
        return image

    h, w = image.shape[:2]
    cx, cy = w // 2, h // 2
    M = cv2.getRotationMatrix2D((cx, cy), -angle, 1.0)

    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw = int(h * sin + w * cos)
    nh = int(h * cos + w * sin)
    M[0, 2] += nw / 2 - cx
    M[1, 2] += nh / 2 - cy

    return cv2.warpAffine(
        image, M, (nw, nh),
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


# ---------------------------------------------------------------------------
# 5. Public entry point
# ---------------------------------------------------------------------------

def correct_skew(
    image: np.ndarray,
    heatmap: np.ndarray,
    *,
    min_centroids: int = 10,
    min_clusters: int = 3,
) -> Tuple[np.ndarray, float]:
    """Detect and correct small-angle skew from a CRAFT heatmap.

    This is the only function most callers need.

    Args:
        image: Original BGR image.
        heatmap: CRAFT heatmap **already resized** to ``image.shape[:2]``.
        min_centroids: Minimum centroids required to attempt correction.
        min_clusters: Minimum clusters required to attempt correction.

    Returns:
        ``(corrected_image, angle_degrees)``
    """
    centroids = extract_centroids(heatmap)
    if len(centroids) < min_centroids:
        return image, 0.0

    clusters = cluster_centroids(centroids)
    if len(clusters) < min_clusters:
        return image, 0.0

    angle = estimate_angle(clusters)
    if angle is None or abs(angle) < 0.1:
        return image, 0.0

    return rotate_image(image, angle), angle
