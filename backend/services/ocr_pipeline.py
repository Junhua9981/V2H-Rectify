"""
OCR pipeline — the orchestrator.

Replaces v2's ``CRAFTOCRAgent`` + ``CRAFTOCRAgentConcurrent``.

Key improvements over v2:
- **Single CRAFT inference** per image — the heatmap is computed once and
  passed to rotation correction, print removal, and grid extraction.
- **No global singleton** — ``CRAFTService`` and ``VLMService`` are injected.
- **Concurrent VLM calls** — ``ThreadPoolExecutor`` for I/O-bound API calls.
- **No mutable state leaks** — every run starts fresh, results are returned
  as dataclasses, and the pipeline never modifies ``self`` flags mid-run.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import cv2
import numpy as np
from PIL import Image

from config.settings import OCRPipelineSettings
from core import grid_extractor, print_removal, rotation
from core.image_utils import bgr_to_pil, pil_to_bgr, split_if_wide, to_grayscale
from core.text_reformat import (
    ReformattedColumn,
    TextReformatConfig,
    apply_double_indent_heuristic,
    refine_text_raw,
    reformat_columns,
)
from services.craft_service import CRAFTService
from services.vlm_service import SYSTEM_PROMPT_OCR, USER_PROMPT_OCR, VLMService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ColumnData:
    """Per-column OCR data for manuscript (稿紙) layout reconstruction."""

    col_index: int
    text: str
    spacing_indexes: List[int]
    num_rows: int


@dataclass
class OCRResult:
    """Final output of the OCR pipeline."""

    text: str = ""
    title: Optional[str] = None
    columns: List[ColumnData] = field(default_factory=list)
    rotation_angle: float = 0.0
    print_removed: bool = False
    was_split: bool = False
    num_columns: int = 0
    elapsed_seconds: float = 0.0
    debug_dir: str = ""


@dataclass
class _ColumnOCR:
    """Intermediate per-column OCR result."""

    text: str
    col_index: int
    spacing_indexes: List[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class OCRPipeline:
    """End-to-end OCR for Chinese handwritten essay paper.

    Usage::

        pipeline = OCRPipeline(craft_svc, vlm_svc)
        result = pipeline.run(pil_image)
        print(result.text)
    """

    def __init__(
        self,
        craft_service: CRAFTService,
        vlm_service: VLMService,
        settings: Optional[OCRPipelineSettings] = None,
    ) -> None:
        self._craft = craft_service
        self._vlm = vlm_service
        self._cfg = settings or OCRPipelineSettings()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        image: Image.Image,
        *,
        auto_rotate: Optional[bool] = None,
        remove_print: Optional[bool] = None,
        auto_split: Optional[bool] = None,
        debug: Optional[bool] = None,
        debug_tag: Optional[str] = None,
    ) -> OCRResult:
        """Execute the full OCR pipeline on *image*.

        Feature flags default to the values in ``OCRPipelineSettings`` but
        can be overridden per-call.
        """
        t0 = time.time()
        do_rotate = auto_rotate if auto_rotate is not None else self._cfg.auto_rotate
        do_print = remove_print if remove_print is not None else self._cfg.remove_print
        do_split = auto_split if auto_split is not None else self._cfg.auto_split
        do_debug = debug if debug is not None else self._cfg.debug_enabled
        debug_dir = self._prepare_debug_dir(debug_tag) if do_debug else None

        img_bgr = pil_to_bgr(image)
        if debug_dir is not None:
            self._save_debug_image(debug_dir / "00_input.png", img_bgr)

        # Optional split
        if do_split:
            parts, was_split = split_if_wide(img_bgr, aspect_threshold=self._cfg.split_aspect_ratio)
        else:
            parts, was_split = [img_bgr], False

        if debug_dir is not None:
            self._save_debug_text(debug_dir / "meta.txt", f"was_split={was_split}\nnum_parts={len(parts)}\n")
            for i, part in enumerate(parts):
                self._save_debug_image(debug_dir / f"01_split_part_{i:02d}.png", part)

        all_texts: list[str] = []
        all_titles: list[Optional[str]] = []
        all_columns: list[ColumnData] = []
        total_angle = 0.0
        total_print_removed = False
        total_columns = 0

        for idx, part in enumerate(reversed(parts)):
            text, part_title, part_columns, angle, pr, num_cols = self._process_single(
                part,
                do_rotate=do_rotate,
                do_print_removal=(do_print and idx == 0),
                debug_dir=debug_dir,
                part_index=idx,
            )
            # Offset col_index so columns from different parts don't collide.
            # parts are processed right→left; each subsequent part's columns
            # must continue after the already-accumulated column count.
            if total_columns > 0:
                part_columns = [
                    ColumnData(
                        col_index=c.col_index + total_columns,
                        text=c.text,
                        spacing_indexes=c.spacing_indexes,
                        num_rows=c.num_rows,
                    )
                    for c in part_columns
                ]
            all_texts.append(text)
            all_titles.append(part_title)
            all_columns.extend(part_columns)
            total_angle = angle  # last one wins for reporting
            total_print_removed = total_print_removed or pr
            total_columns += num_cols

        final_title = next((t for t in all_titles if t), None)

        # Normalise col_index to be globally consecutive 0, 1, 2, …
        # Sort by the offset-adjusted col_index (relative order is already
        # correct), then re-assign clean integers so the frontend always
        # receives deduplicated, consecutive indices regardless of how each
        # half's grid numbered its own columns.
        all_columns.sort(key=lambda c: c.col_index)
        all_columns = [
            ColumnData(
                col_index=i,
                text=c.text,
                spacing_indexes=c.spacing_indexes,
                num_rows=c.num_rows,
            )
            for i, c in enumerate(all_columns)
        ]

        return OCRResult(
            text="".join(all_texts),
            title=final_title,
            columns=all_columns,
            rotation_angle=total_angle,
            print_removed=total_print_removed,
            was_split=was_split,
            num_columns=total_columns,
            elapsed_seconds=round(time.time() - t0, 2),
            debug_dir=str(debug_dir) if debug_dir is not None else "",
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _process_single(
        self,
        img_bgr: np.ndarray,
        *,
        do_rotate: bool,
        do_print_removal: bool,
        debug_dir: Optional[Path],
        part_index: int,
    ) -> tuple[str, Optional[str], List[ColumnData], float, bool, int]:
        """Process a single (possibly half) image through the pipeline.

        Returns ``(body, title, columns, rotation_angle, print_was_removed, num_columns)``.
        """
        prefix = f"part_{part_index:02d}"
        if debug_dir is not None:
            self._save_debug_image(debug_dir / f"{prefix}_10_input.png", img_bgr)

        # ---- CRAFT detection (ONE pass) ----
        det_result, heatmap = self._craft.detect_with_heatmap(img_bgr, canvas_size=5120)
        if debug_dir is not None:
            self._save_debug_heatmap(debug_dir / f"{prefix}_11_heatmap_initial.png", heatmap)

        # ---- Rotation correction ----
        angle = 0.0
        if do_rotate:
            img_bgr, angle = rotation.correct_skew(img_bgr, heatmap)
            if debug_dir is not None:
                self._save_debug_image(debug_dir / f"{prefix}_20_after_rotation.png", img_bgr)
            if abs(angle) > 0.1:
                logger.info("Rotated by %.2f°", angle)
                # Re-detect after rotation
                det_result, heatmap = self._craft.detect_with_heatmap(img_bgr, canvas_size=5120)
                if debug_dir is not None:
                    self._save_debug_heatmap(debug_dir / f"{prefix}_21_heatmap_after_rotation.png", heatmap)

        # ---- Print-text removal ----
        print_removed = False
        if do_print_removal:
            pr_result = print_removal.detect_and_remove(
                img_bgr, heatmap, direction="horizontal"
            )
            if debug_dir is not None:
                self._save_debug_text(
                    debug_dir / f"{prefix}_30_print_removal.txt",
                    (
                        f"status={pr_result.status}\n"
                        f"boundary={pr_result.boundary}\n"
                        f"num_print={pr_result.num_print}\n"
                        f"num_handwriting={pr_result.num_handwriting}\n"
                    ),
                )
            if pr_result.status == "success":
                img_bgr = pr_result.image
                print_removed = True
                logger.info("Removed printed text (boundary=%d)", pr_result.boundary)
                if debug_dir is not None:
                    self._save_debug_image(debug_dir / f"{prefix}_31_after_print_removal.png", img_bgr)
                # Re-detect after crop
                det_result, heatmap = self._craft.detect_with_heatmap(img_bgr)
                if debug_dir is not None:
                    self._save_debug_heatmap(debug_dir / f"{prefix}_32_heatmap_after_print_removal.png", heatmap)

        # ---- Grid extraction ----
        gray = to_grayscale(img_bgr)
        char_mask = grid_extractor.character_mask_from_heatmap(heatmap)
        if debug_dir is not None:
            self._save_debug_image(debug_dir / f"{prefix}_40_gray.png", gray)
            self._save_debug_heatmap(debug_dir / f"{prefix}_41_char_mask.png", char_mask)

        try:
            grid = grid_extractor.extract_grid(gray, char_mask)
        except RuntimeError:
            logger.warning("Grid extraction failed — returning empty text")
            return "", None, [], angle, print_removed, 0

        if debug_dir is not None:
            self._save_debug_image(
                debug_dir / f"{prefix}_42_grid_boxes.png",
                self._draw_grid_boxes(img_bgr, grid.boxes),
            )

        # ---- Vertical → Horizontal ----
        box_dicts = [
            {"x": b.x, "y": b.y, "w": b.w, "h": b.h, "row": b.row, "col": b.col}
            for b in grid.boxes
        ]
        columns = reformat_columns(
            img_bgr,
            box_dicts,
            config=self._text_reformat_config(),
            ink_map=char_mask,
        )

        if not columns:
            return "", None, [], angle, print_removed, 0

        if debug_dir is not None:
            for i, col in enumerate(columns):
                self._save_debug_image(debug_dir / f"{prefix}_50_column_{i:02d}.png", col.image)

        # ---- Concurrent VLM OCR ----
        column_results = self._ocr_columns(columns)
        # ---- Merge ----
        title, body = refine_text_raw(column_results)
        if debug_dir is not None:
            debug_content = (f"[title]\n{title}\n\n[body]\n{body}") if title else body
            self._save_debug_text(debug_dir / f"{prefix}_99_text.txt", debug_content)

        col_data = []
        for r in sorted(column_results, key=lambda r: r["col_index"]):
            text = r["text"].strip()
            num_rows = int(r.get("num_rows", 0) or 0)
            si = sorted({int(i) for i in r.get("spacing_indexes", []) if isinstance(i, int)})
            si = [i for i in si if i >= 0 and (num_rows <= 0 or i < num_rows)]
            si = apply_double_indent_heuristic(si, num_rows, len(text))
            col_data.append(ColumnData(
                col_index=r["col_index"],
                text=r["text"],
                spacing_indexes=si,
                num_rows=num_rows,
            ))
        return body, title, col_data, angle, print_removed, len(columns)

    def _ocr_columns(self, columns: List[ReformattedColumn]) -> List[Dict]:
        """OCR all columns concurrently via the VLM service."""
        results: list[dict | None] = [None] * len(columns)

        def _ocr_one(idx: int, col: ReformattedColumn) -> tuple[int, dict]:
            pil_img = bgr_to_pil(col.image)
            try:
                text = self._vlm.ocr(pil_img, USER_PROMPT_OCR, SYSTEM_PROMPT_OCR)
            except Exception as e:
                logger.warning("VLM OCR failed for column %d: %s", col.col_index, e)
                text = ""
            return idx, {
                "text": text,
                "col_index": col.col_index,
                "spacing_indexes": col.spacing_indexes,
                "num_rows": col.num_rows,
            }

        workers = min(self._cfg.max_workers, len(columns))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_ocr_one, i, c): i for i, c in enumerate(columns)}
            for fut in as_completed(futs):
                idx, result = fut.result()
                results[idx] = result

        return [r for r in results if r is not None]

    def _prepare_debug_dir(self, debug_tag: Optional[str]) -> Path:
        base_dir = Path(self._cfg.debug_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        suffix = self._sanitize_tag(debug_tag) if debug_tag else uuid.uuid4().hex[:8]
        out_dir = base_dir / f"{timestamp}_{suffix}"
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir

    def _text_reformat_config(self) -> TextReformatConfig:
        return TextReformatConfig(
            spacing=self._cfg.reformat_spacing,
            binary_threshold=self._cfg.reformat_binary_threshold,
            blank_ink_ratio=self._cfg.reformat_blank_ink_ratio,
            heat_rescue_peak=self._cfg.reformat_heat_rescue_peak,
        )

    @staticmethod
    def _sanitize_tag(raw: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", raw).strip("_")
        return cleaned[:64] if cleaned else uuid.uuid4().hex[:8]

    @staticmethod
    def _save_debug_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    @staticmethod
    def _save_debug_image(path: Path, image: np.ndarray) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        arr = OCRPipeline._to_uint8(image)
        cv2.imwrite(str(path), arr)

    @staticmethod
    def _save_debug_heatmap(path: Path, heatmap: np.ndarray) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        arr = OCRPipeline._to_uint8(heatmap)
        if arr.ndim == 2:
            arr = cv2.applyColorMap(arr, cv2.COLORMAP_JET)
        cv2.imwrite(str(path), arr)

    @staticmethod
    def _to_uint8(image: np.ndarray) -> np.ndarray:
        arr = image
        if arr.dtype == np.uint8:
            return arr

        arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        arr_min = float(arr.min()) if arr.size else 0.0
        arr_max = float(arr.max()) if arr.size else 0.0
        if arr_max - arr_min < 1e-8:
            return np.zeros(arr.shape, dtype=np.uint8)
        arr = (arr - arr_min) / (arr_max - arr_min)
        return (arr * 255).astype(np.uint8)

    @staticmethod
    def _draw_grid_boxes(image: np.ndarray, boxes: List) -> np.ndarray:
        vis = image.copy()
        for b in boxes:
            cv2.rectangle(vis, (b.x, b.y), (b.x + b.w, b.y + b.h), (0, 255, 0), 1)
        return vis
