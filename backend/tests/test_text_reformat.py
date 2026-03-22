import numpy as np
import cv2

from core.text_reformat import TextReformatConfig, refine_text_raw, vertical_to_horizontal


def _make_blank_canvas(height: int = 24, width: int = 72) -> np.ndarray:
    return np.full((height, width, 3), 255, dtype=np.uint8)


def _three_boxes(cell_w: int = 24, cell_h: int = 24):
    return [
        {"x": 0, "y": 0, "w": cell_w, "h": cell_h},
        {"x": cell_w, "y": 0, "w": cell_w, "h": cell_h},
        {"x": cell_w * 2, "y": 0, "w": cell_w, "h": cell_h},
    ]


def test_vertical_to_horizontal_keeps_tiny_punctuation_but_filters_line_noise():
    img = _make_blank_canvas()
    boxes = _three_boxes()

    # Cell 1: tiny punctuation-like dot (should be kept)
    cv2.circle(img, (24 + 12, 12), 1, (0, 0, 0), thickness=-1)
    # Cell 2: thin long horizontal line artifact (should be blank)
    cv2.line(img, (48 + 3, 12), (48 + 21, 12), (0, 0, 0), thickness=1)

    _, spacing_indexes = vertical_to_horizontal(img, boxes)

    assert 1 not in spacing_indexes
    assert 2 in spacing_indexes


def test_vertical_to_horizontal_keeps_small_yi_stroke():
    img = _make_blank_canvas(height=24, width=24)
    boxes = [{"x": 0, "y": 0, "w": 24, "h": 24}]

    # Small "一" stroke: short, thin, but not spanning enough to be artifact line.
    cv2.line(img, (8, 12), (15, 12), (0, 0, 0), thickness=1)

    _, spacing_indexes = vertical_to_horizontal(img, boxes)

    assert spacing_indexes == []


def test_vertical_to_horizontal_configurable_spacing():
    img = _make_blank_canvas(height=20, width=20)
    cv2.rectangle(img, (7, 6), (12, 13), (0, 0, 0), thickness=-1)
    boxes = [{"x": 0, "y": 0, "w": 20, "h": 20}]

    custom = TextReformatConfig(spacing=9)
    out, spacing_indexes = vertical_to_horizontal(img, boxes, config=custom)

    assert spacing_indexes == []
    # output width = char_w(6) + spacing*2
    assert out.shape[1] == 6 + 18


def test_vertical_to_horizontal_marks_blank_using_heatmap_low_energy():
    img = _make_blank_canvas(height=24, width=24)
    boxes = [{"x": 0, "y": 0, "w": 24, "h": 24}]

    # Tiny random noise in image should still be considered blank when
    # heatmap says there is no character evidence.
    img[11, 11] = (0, 0, 0)
    heat = np.zeros((24, 24), dtype=np.float32)

    _, spacing_indexes = vertical_to_horizontal(img, boxes, ink_map=heat)

    assert spacing_indexes == [0]


def test_vertical_to_horizontal_rescues_cell_with_strong_heatmap_signal():
    img = _make_blank_canvas(height=24, width=24)
    boxes = [{"x": 0, "y": 0, "w": 24, "h": 24}]

    # No binary foreground in the image, but heatmap indicates strong text evidence.
    heat = np.zeros((24, 24), dtype=np.float32)
    heat[8:16, 8:16] = 0.85

    _, spacing_indexes = vertical_to_horizontal(img, boxes, ink_map=heat)

    assert spacing_indexes == []


def test_refine_text_raw_restores_internal_gaps_with_fullwidth_space():
    title, body = refine_text_raw(
        [
            {"text": "題目", "col_index": 0, "spacing_indexes": [0, 1, 2, 3], "num_rows": 6},
            {"text": "天地人", "col_index": 1, "spacing_indexes": [1, 3], "num_rows": 5},
        ]
    )

    assert title == "題目"
    assert body == "天　地　人"


def test_refine_text_raw_restores_leading_and_internal_gaps():
    title, body = refine_text_raw(
        [
            {"text": "文章", "col_index": 0, "spacing_indexes": [0, 1], "num_rows": 4},
        ]
    )

    assert title is None
    assert body == "\n　　文章"


def test_refine_text_raw_auto_upgrades_single_to_double_indent_when_pattern_matches():
    title, body = refine_text_raw(
        [
            # num_rows=6, detected spacing only [0], text_len=4 => likely should be [0,1]
            {"text": "天地玄黃", "col_index": 0, "spacing_indexes": [0], "num_rows": 6},
        ]
    )

    assert title is None
    assert body == "\n　　天地玄黃"


def test_vertical_to_horizontal_treats_outer_border_line_as_blank():
    img = _make_blank_canvas(height=24, width=24)
    boxes = [{"x": 0, "y": 0, "w": 24, "h": 24}]

    # Simulate manuscript outer frame line near image border.
    cv2.line(img, (0, 3), (23, 3), (0, 0, 0), thickness=1)
    heat = np.zeros((24, 24), dtype=np.float32)

    _, spacing_indexes = vertical_to_horizontal(img, boxes, ink_map=heat)

    assert spacing_indexes == [0]
