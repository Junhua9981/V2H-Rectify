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
        if crop.size == 0:
            spacing_indexes.append(idx)
            continue

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)
        coords = cv2.findNonZero(binary)
        if coords is not None:
            rx, ry, rw, rh = cv2.boundingRect(coords)
            # Reject stray line artifacts: a thin line spanning most of the cell
            # is treated as blank rather than a character.
            is_horiz_line = rh <= max(3, bh * 0.12) and rw >= bw * 0.40
            is_vert_line  = rw <= max(3, bw * 0.12) and rh >= bh * 0.40
            if is_horiz_line or is_vert_line:
                spacing_indexes.append(idx)
            else:
                tight = crop[ry : ry + rh, rx : rx + rw]
                char_images.append(tight)
                max_char_h = max(max_char_h, tight.shape[0])
        else:
            spacing_indexes.append(idx)

    if not char_images:
        return image, spacing_indexes

    total_w = sum(ci.shape[1] for ci in char_images) + spacing * (len(char_images) + 1)
    result = np.ones((max_char_h, total_w, c), dtype=np.uint8) * 255

    cur_x = spacing
    for ci in char_images:
        ch, cw = ci.shape[:2]
        y_off = (max_char_h - ch) // 2
        result[y_off : y_off + ch, cur_x : cur_x + cw] = ci
        cur_x += cw + spacing

    return result, spacing_indexes


def reformat_columns(
    image: np.ndarray,
    grid_boxes: List[Dict],
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
        h_img, sp_idx = vertical_to_horizontal(image, char_boxes)
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
        text = t["text"].strip()
        si = t.get("spacing_indexes", [])

        # Count leading blanks
        leading = 0
        for i, num in enumerate(si):
            if num == i:
                leading += 1
            else:
                break

        # Title: only the very first column (rightmost on paper) with ≥4 leading blanks.
        if t["col_index"] == first_col_index and leading >= 4 and title is None:
            title = text.replace(" ", "")
            continue

        if leading > 0:
            combined += "\n"

        combined += "　" * leading  # full-width space
        combined += (
            text.replace(" ", "")
            .replace("||", "－－")
            .replace(",", "，")
            .replace(".", "。")
            .replace(";", "；")
            .replace(":", "：")
        )

    return title, combined