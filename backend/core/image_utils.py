"""
Common image utilities — splitting, format conversion, encoding.
"""

from __future__ import annotations

import base64
import io
from typing import List, Tuple

import cv2
import numpy as np
from PIL import Image


def pil_to_bgr(image: Image.Image) -> np.ndarray:
    """Convert a PIL Image to an OpenCV BGR numpy array."""
    if image.mode != "RGB":
        image = image.convert("RGB")
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def bgr_to_pil(image: np.ndarray) -> Image.Image:
    """Convert an OpenCV BGR numpy array to a PIL Image."""
    return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))


def to_grayscale(image: np.ndarray) -> np.ndarray:
    """Safely convert to grayscale regardless of input format."""
    if image.ndim == 2:
        return image
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def image_to_base64(image: Image.Image, fmt: str = "PNG") -> str:
    """Encode a PIL Image as a base64 data-URI string."""
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/{fmt.lower()};base64,{b64}"


def split_if_wide(
    image: np.ndarray,
    *,
    aspect_threshold: float = 2.0,
) -> Tuple[List[np.ndarray], bool]:
    """Split a wide image (aspect > threshold) into left and right halves.

    Returns:
        ``(image_list, was_split)``
    """
    h, w = image.shape[:2]
    if w > h * aspect_threshold:
        mid = w // 2
        return [image[:, :mid], image[:, mid:]], True
    return [image], False
