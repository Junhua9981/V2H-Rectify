"""
Text reformatting — vertical-to-horizontal conversion and post-processing.

Extracted from v2 ``craft_ocr_agent.py`` methods:
- ``_convert_vertical_to_horizontal``
- ``_refine_text_raw``
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hardcoded constants for blank-cell detection (no need to expose as params)
# ---------------------------------------------------------------------------
_LINE_THICKNESS_RATIO = 0.10   # Max line thickness as fraction of cell dimension
_LINE_SPAN_RATIO = 0.50        # Min span of ink bounding box to be classified as a line
_HEAT_ACTIVE_THRESHOLD = 0.35  # Heatmap pixel value above which a pixel counts as "active"
_HEAT_RESCUE_ACTIVE = 0.03     # Min active ratio inside a line-shaped cell to rescue it
_HEAT_CENTER_MARGIN = 0.20     # Fraction trimmed from each edge before reading heatmap;
                               # avoids picking up activation that bleeds from neighbour chars


@dataclass(frozen=True)
class TextReformatConfig:
    """Tunable thresholds for blank-cell detection.

    Only the parameters that meaningfully affect real-world accuracy are
    exposed here.  Everything else is hardcoded as module-level constants.
    """

    spacing: int = 20               # Pixel gap between characters in the output strip
    binary_threshold: int = 128     # Threshold for image → binary (ink) conversion
    blank_ink_ratio: float = 0.04   # Fill ratio below this is considered "sparse ink"
    heat_rescue_peak: float = 0.40  # Heatmap peak above this → definitely a character


@dataclass
class ReformattedColumn:
    """One column of characters converted to a horizontal strip."""

    image: np.ndarray
    col_index: int
    spacing_indexes: List[int] = field(default_factory=list)
    num_rows: int = 0  # total grid boxes in this column (blank + non-blank)


# ---------------------------------------------------------------------------
# Vertical → Horizontal
# ---------------------------------------------------------------------------

def vertical_to_horizontal(
    image: np.ndarray,
    char_boxes: List[Dict],
    *,
    spacing: int = 20,
    config: Optional[TextReformatConfig] = None,
    ink_map: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, List[int]]:
    """Convert a vertical column of character boxes to a single horizontal strip.

    Args:
        image: Full (preprocessed) BGR image.
        char_boxes: List of dicts with keys ``x, y, w, h`` (absolute coords).
        spacing: Pixel gap between characters in the output.

    Returns:
        ``(horizontal_image, spacing_indexes)`` where *spacing_indexes* lists
        the original box indices that were blank (no ink).
    """
    cfg = config or TextReformatConfig(spacing=spacing)

    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

    if not char_boxes:
        return image, []

    _h_img, _w_img, c = image.shape
    char_images: list[np.ndarray] = []
    spacing_indexes: list[int] = []
    max_char_h = 0

    for idx, box in enumerate(char_boxes):
        x, y, bw, bh = box["x"], box["y"], box["w"], box["h"]
        crop = image[y : y + bh, x : x + bw]
        ink_crop = None if ink_map is None else ink_map[y : y + bh, x : x + bw]
        if crop.size == 0:
            spacing_indexes.append(idx)
            continue

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, cfg.binary_threshold, 255, cv2.THRESH_BINARY_INV)

        if _is_blank_cell(binary, ink_crop, bw, bh, cfg):
            spacing_indexes.append(idx)
        else:
            coords = cv2.findNonZero(binary)
            if coords is not None:
                rx, ry, rw, rh = cv2.boundingRect(coords)
                tight = crop[ry : ry + rh, rx : rx + rw]
                char_images.append(tight)
                max_char_h = max(max_char_h, tight.shape[0])
            else:
                # No binary foreground but not blank (rescued by heatmap peak).
                char_images.append(crop)
                max_char_h = max(max_char_h, crop.shape[0])

    if not char_images:
        return image, spacing_indexes

    total_w = sum(ci.shape[1] for ci in char_images) + cfg.spacing * (len(char_images) + 1)
    result = np.ones((max_char_h, total_w, c), dtype=np.uint8) * 255

    cur_x = cfg.spacing
    for ci in char_images:
        ch, cw = ci.shape[:2]
        y_off = (max_char_h - ch) // 2
        result[y_off : y_off + ch, cur_x : cur_x + cw] = ci
        cur_x += cw + cfg.spacing

    return result, spacing_indexes


def _is_blank_cell(
    binary: np.ndarray,
    ink_crop: Optional[np.ndarray],
    bw: int,
    bh: int,
    cfg: TextReformatConfig,
) -> bool:
    """Return True if the cell should be treated as blank (no handwritten content).

    Decision tree (evaluated in priority order):

    1. Strong heatmap peak  → definitely a character, stop.
    2. No binary ink        → blank (faint chars already caught by step 1).
    3. Line-shaped ink      → manuscript grid/border line → blank,
                              unless heatmap active-ratio says otherwise.
    4. Sparse ink + heatmap → noise/dirt → blank.
    5. Meaningful ink       → not blank.
    """
    has_heat = ink_crop is not None and ink_crop.size > 0
    # Use only the central region of the heatmap to avoid picking up activation
    # that bleeds in from neighbouring character cells.
    _, heat_peak, heat_active = _center_heat_stats(ink_crop, _HEAT_ACTIVE_THRESHOLD)

    # Priority 1: strong character evidence in heatmap → keep unconditionally.
    if has_heat and heat_peak >= cfg.heat_rescue_peak:
        return False

    fill_ratio = int(np.count_nonzero(binary)) / max(1, bw * bh)

    # Priority 2: no ink at all → blank.
    if fill_ratio == 0:
        return True

    # Priority 3: line-artifact detection (printed grid lines, border frames).
    coords = cv2.findNonZero(binary)
    rx, ry, rw, rh = cv2.boundingRect(coords)
    thickness_h = max(2, int(bh * _LINE_THICKNESS_RATIO))
    thickness_w = max(2, int(bw * _LINE_THICKNESS_RATIO))
    is_line = (rh <= thickness_h and rw >= bw * _LINE_SPAN_RATIO) or (
        rw <= thickness_w and rh >= bh * _LINE_SPAN_RATIO
    )
    if is_line:
        # Rescue only when the heatmap is meaningfully active (e.g. character「一」).
        # Printed grid lines produce near-zero heatmap activity.
        if has_heat and heat_active >= _HEAT_RESCUE_ACTIVE:
            return False
        return True

    # Priority 4: sparse ink with heatmap confirmation → noise/dirt → blank.
    if fill_ratio <= cfg.blank_ink_ratio:
        if has_heat:
            return True   # weak ink AND weak heatmap → not a character
        return False      # no heatmap: give benefit of the doubt

    # Priority 5: meaningful ink → not blank.
    return False


def reformat_columns(
    image: np.ndarray,
    grid_boxes: List[Dict],
    *,
    config: Optional[TextReformatConfig] = None,
    ink_map: Optional[np.ndarray] = None,
) -> List[ReformattedColumn]:
    """Convert all columns in a grid to horizontal strips.

    Args:
        image: Full preprocessed BGR image.
        grid_boxes: Flat list of grid-box dicts (with ``x,y,w,h,row,col``).

    Returns:
        One ``ReformattedColumn`` per column, ordered by column index.
    """
    # Group by column
    col_map: dict[int, list[dict]] = {}
    for b in grid_boxes:
        col_map.setdefault(b["col"], []).append(b)

    results: list[ReformattedColumn] = []
    for c_idx in sorted(col_map):
        boxes_sorted = sorted(col_map[c_idx], key=lambda b: b["row"])
        char_boxes = [{"x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"]} for b in boxes_sorted]
        h_img, sp_idx = vertical_to_horizontal(
            image,
            char_boxes,
            config=config,
            ink_map=ink_map,
        )
        results.append(ReformattedColumn(
            image=h_img,
            col_index=c_idx,
            spacing_indexes=sp_idx,
            num_rows=len(boxes_sorted),
        ))

    return results


# ---------------------------------------------------------------------------
# Raw text refinement (no LLM — pure string processing)
# ---------------------------------------------------------------------------

def refine_text_raw(
    recognized_texts: List[Dict],
) -> Tuple[Optional[str], str]:
    """Merge per-column OCR results into a ``(title, body)`` tuple.

    Reproduces the v2 ``_refine_text_raw`` logic:
    - Detect title (4 leading blanks) and return it separately.
    - Insert paragraph indentation from spacing indexes.
    - Normalize punctuation to full-width.

    Args:
        recognized_texts: List of dicts with keys
            ``text``, ``col_index``, ``spacing_indexes``.

    Returns:
        ``(title, body)`` where *title* is ``None`` when absent.
    """
    sorted_texts = sorted(recognized_texts, key=lambda t: t["col_index"])
    combined = ""
    title: Optional[str] = None
    first_col_index = sorted_texts[0]["col_index"] if sorted_texts else -1

    for t in sorted_texts:
        text = _normalize_text(t["text"].strip())
        num_rows = int(t.get("num_rows", 0) or 0)
        si = sorted({int(i) for i in t.get("spacing_indexes", []) if isinstance(i, int)})
        si = [i for i in si if i >= 0 and (num_rows <= 0 or i < num_rows)]
        si = apply_double_indent_heuristic(si, num_rows, len(text))

        # Count leading blanks
        leading = _count_leading_blanks(si, num_rows)

        # Title: only the very first column (rightmost on paper) with ≥4 leading blanks.
        if t["col_index"] == first_col_index and leading >= 4 and title is None:
            title = text
            continue

        if leading > 0:
            combined += "\n"

        if num_rows > 0:
            combined += _rebuild_column_text_with_gaps(text, si, num_rows)
        else:
            combined += "　" * leading + text

    return title, combined


def _normalize_text(text: str) -> str:
    return (
        text.replace(" ", "")
        .replace("||", "－－")
        .replace(",", "，")
        .replace(".", "。")
        .replace(";", "；")
        .replace(":", "：")
    )


def _count_leading_blanks(spacing_indexes: List[int], num_rows: int) -> int:
    if num_rows <= 0:
        return 0
    blank_set = set(spacing_indexes)
    leading = 0
    while leading < num_rows and leading in blank_set:
        leading += 1
    return leading


def _rebuild_column_text_with_gaps(text: str, spacing_indexes: List[int], num_rows: int) -> str:
    blank_set = set(spacing_indexes)
    chars = list(text)
    out: list[str] = []
    char_idx = 0

    for row in range(num_rows):
        if row in blank_set:
            out.append("　")
            continue
        if char_idx < len(chars):
            out.append(chars[char_idx])
            char_idx += 1
        else:
            out.append("　")

    if char_idx < len(chars):
        # Keep extra recognized chars to avoid data loss when OCR length drifts.
        out.extend(chars[char_idx:])

    return "".join(out)


def apply_double_indent_heuristic(
    spacing_indexes: List[int],
    num_rows: int,
    text_len: int,
) -> List[int]:
    """Apply manuscript rule: a detected one-space indent is often actually two."""
    if num_rows <= 0:
        return spacing_indexes

    leading = _count_leading_blanks(spacing_indexes, num_rows)
    if leading != 1:
        return spacing_indexes

    # Strict rule for safety:
    # - only one detected blank (at row 0)
    # - visible chars are exactly one short after accounting that first blank
    #   i.e. text_len + 1 == num_rows - 1  -> text_len == num_rows - 2
    if len(spacing_indexes) == 1 and spacing_indexes[0] == 0 and text_len == (num_rows - 2):
        return [0, 1]
    return spacing_indexes


def _heat_stats(ink_crop: Optional[np.ndarray], active_threshold: float) -> Tuple[float, float, float]:
    """Return (mean, peak, active_ratio) for a heatmap crop, all in [0, 1]."""
    if ink_crop is None or ink_crop.size == 0:
        return 0.0, 0.0, 0.0

    arr = np.asarray(ink_crop, dtype=np.float32)
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)

    if arr.max() > 1.0:
        arr = arr / 255.0
    arr = np.clip(arr, 0.0, 1.0)

    mean_val = float(arr.mean())
    peak_val = float(arr.max())
    active_ratio = float(np.mean(arr >= active_threshold))
    return mean_val, peak_val, active_ratio


def _center_heat_stats(ink_crop: Optional[np.ndarray], active_threshold: float) -> Tuple[float, float, float]:
    """Like _heat_stats but restricted to the inner region of the crop.

    CRAFT heatmaps bleed activation beyond the actual character boundary.  A
    blank cell adjacent to a character will show elevated values along its
    edges.  By trimming _HEAT_CENTER_MARGIN from every side we read only the
    region where a *genuine* character signal would appear, ignoring the
    neighbour bleed-over at the periphery.
    """
    if ink_crop is None or ink_crop.size == 0:
        return 0.0, 0.0, 0.0
    h, w = ink_crop.shape[:2]
    my = max(1, int(h * _HEAT_CENTER_MARGIN))
    mx = max(1, int(w * _HEAT_CENTER_MARGIN))
    center = ink_crop[my : max(my + 1, h - my), mx : max(mx + 1, w - mx)]
    return _heat_stats(center, active_threshold)