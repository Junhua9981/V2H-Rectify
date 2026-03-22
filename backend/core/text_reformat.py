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


@dataclass(frozen=True)
class TextReformatConfig:
    """Tunable thresholds for conservative blank-cell detection."""

    spacing: int = 20
    binary_threshold: int = 128
    line_thickness_ratio: float = 0.08
    line_span_ratio: float = 0.55
    min_fill_ratio: float = 0.040
    min_bbox_fill_ratio: float = 0.55
    heat_active_threshold: float = 0.35
    heat_blank_mean_max: float = 0.06
    heat_blank_active_ratio_max: float = 0.015
    heat_blank_peak_max: float = 0.28
    heat_line_active_ratio_max: float = 0.010
    heat_rescue_peak_min: float = 0.40
    heat_rescue_active_ratio_min: float = 0.030
    outer_border_margin_ratio: float = 0.015
    outer_border_margin_min_px: int = 2
    outer_border_line_span_ratio: float = 0.45
    outer_border_max_fill_ratio: float = 0.10
    outer_border_max_heat_active_ratio: float = 0.06


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

    h_img, w_img, c = image.shape
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
        has_heat = ink_crop is not None and ink_crop.size > 0
        heat_mean, heat_peak, heat_active_ratio = _heat_stats(ink_crop, cfg.heat_active_threshold)
        coords = cv2.findNonZero(binary)
        if coords is not None:
            rx, ry, rw, rh = cv2.boundingRect(coords)

            # Conservative blank classification:
            # only drop when line-like shape AND very low ink density.
            thickness_px_h = max(2, int(round(bh * cfg.line_thickness_ratio)))
            thickness_px_w = max(2, int(round(bw * cfg.line_thickness_ratio)))
            is_horiz_line = rh <= thickness_px_h and rw >= bw * cfg.line_span_ratio
            is_vert_line = rw <= thickness_px_w and rh >= bh * cfg.line_span_ratio

            ink_pixels = int(np.count_nonzero(binary))
            fill_ratio = ink_pixels / max(1, bw * bh)

            tight_mask = binary[ry : ry + rh, rx : rx + rw]
            bbox_fill_ratio = np.count_nonzero(tight_mask) / max(1, rw * rh)

            blank_like = (
                (is_horiz_line or is_vert_line)
                and fill_ratio <= cfg.min_fill_ratio
                and bbox_fill_ratio >= cfg.min_bbox_fill_ratio
                and (
                    not has_heat
                    or heat_active_ratio <= cfg.heat_line_active_ratio_max
                )
            )

            border_margin = max(
                cfg.outer_border_margin_min_px,
                int(round(min(h_img, w_img) * cfg.outer_border_margin_ratio)),
            )
            near_outer_border = (
                x <= border_margin
                or y <= border_margin
                or (x + bw) >= (w_img - border_margin)
                or (y + bh) >= (h_img - border_margin)
            )
            border_span_h = rh <= thickness_px_h and rw >= bw * cfg.outer_border_line_span_ratio
            border_span_v = rw <= thickness_px_w and rh >= bh * cfg.outer_border_line_span_ratio
            border_blank_like = (
                near_outer_border
                and (border_span_h or border_span_v)
                and fill_ratio <= cfg.outer_border_max_fill_ratio
                and (
                    (not has_heat)
                    or heat_active_ratio <= cfg.outer_border_max_heat_active_ratio
                )
            )
            blank_like = blank_like or border_blank_like

            if has_heat:
                blank_like = blank_like or (
                    fill_ratio <= cfg.min_fill_ratio
                    and heat_mean <= cfg.heat_blank_mean_max
                    and heat_active_ratio <= cfg.heat_blank_active_ratio_max
                    and heat_peak <= cfg.heat_blank_peak_max
                )

            heat_rescue = (
                has_heat
                and (
                    heat_peak >= cfg.heat_rescue_peak_min
                    or heat_active_ratio >= cfg.heat_rescue_active_ratio_min
                )
            )
            if heat_rescue:
                blank_like = False

            if blank_like:
                spacing_indexes.append(idx)
            else:
                tight = crop[ry : ry + rh, rx : rx + rw]
                char_images.append(tight)
                max_char_h = max(max_char_h, tight.shape[0])
        else:
            # When thresholding misses faint ink, keep the cell if heatmap still
            # indicates confident character evidence.
            if has_heat and (
                heat_peak >= cfg.heat_rescue_peak_min
                or heat_active_ratio >= cfg.heat_rescue_active_ratio_min
            ):
                char_images.append(crop)
                max_char_h = max(max_char_h, crop.shape[0])
            else:
                spacing_indexes.append(idx)

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