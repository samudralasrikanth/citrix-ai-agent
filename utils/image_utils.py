"""
Image helper utilities: saving, pixel diffing, cropping, and colour transforms.
"""

from __future__ import annotations

import cv2
import numpy as np

from utils.logger import get_logger

log = get_logger(__name__)


def save_image(image: np.ndarray, path: str) -> None:
    """
    Persist a NumPy BGR image to disk.

    Args:
        image: BGR image array.
        path:  Destination file path (PNG recommended).
    """
    ok = cv2.imwrite(path, image)
    if not ok:
        log.error("Failed to write image → %s", path)
    else:
        log.debug("Image saved → %s", path)


def pixel_diff_ratio(img_a: np.ndarray, img_b: np.ndarray) -> float:
    """
    Fraction of pixels that differ between two same-size images.

    Args:
        img_a: First BGR frame.
        img_b: Second BGR frame (must match shape of img_a).

    Returns:
        Float in [0.0, 1.0].
    """
    if img_a.shape != img_b.shape:
        img_b = cv2.resize(img_b, (img_a.shape[1], img_a.shape[0]))

    diff = cv2.absdiff(img_a, img_b)
    gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 25, 255, cv2.THRESH_BINARY)
    ratio = np.count_nonzero(thresh) / thresh.size
    log.debug("Pixel diff ratio: %.4f", ratio)
    return float(ratio)


def image_hash(image: np.ndarray) -> str:
    """
    Compute a perceptual hash of an image for stable screen-ID generation.

    Uses a simple 8x8 average-hash (aHash):
    - Resize to 8x8 grayscale
    - Threshold at mean pixel value
    - Encode as 16-character hex string

    Args:
        image: BGR image array.

    Returns:
        16-character hex string.
    """
    small = cv2.resize(image, (8, 8))
    gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    mean  = gray.mean()
    bits  = (gray > mean).flatten()
    # Pack 64 bits into 16 hex nibbles
    value = int("".join("1" if b else "0" for b in bits), 2)
    return f"{value:016x}"


def crop_region(image: np.ndarray, box: list[int]) -> np.ndarray:
    """
    Crop [x1, y1, x2, y2] from image.

    Args:
        image: Source BGR image.
        box:   [x1, y1, x2, y2].

    Returns:
        Cropped array.
    """
    x1, y1, x2, y2 = box
    return image[y1:y2, x1:x2]


def to_grayscale(image: np.ndarray) -> np.ndarray:
    """BGR → grayscale."""
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
