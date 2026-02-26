"""
Screen state builder.
Produces a JSON-serialisable snapshot of the current screen using
a perceptual image hash as the screen_id.
"""

from __future__ import annotations

import json
import time
from typing import Any

import numpy as np

from utils.image_utils import image_hash
from utils.logger import get_logger

log = get_logger(__name__)

ScreenState = dict[str, Any]


def build_screen_state(
    image: np.ndarray,
    ocr_results: list[dict],
    elements: list[dict],
    step: int = 0,
) -> ScreenState:
    """
    Construct a structured, hashable screen snapshot.

    The screen_id is derived from the *image pixels* (perceptual hash),
    not from text content, so visually identical screens share the same ID
    even if OCR produces slightly different results.

    Args:
        image:       BGR frame used for hashing.
        ocr_results: Output of OcrEngine.extract().
        elements:    Output of ElementDetector (after merge_with_ocr).
        step:        Current agent step counter.

    Returns:
        ScreenState dict with keys:
          screen_id, timestamp, step, visible_texts, elements.
    """
    screen_id     = image_hash(image)
    visible_texts = [r["text"] for r in ocr_results]

    state: ScreenState = {
        "screen_id":     screen_id,
        "timestamp":     time.strftime("%Y-%m-%dT%H:%M:%S"),
        "step":          step,
        "visible_texts": visible_texts,
        "elements":      elements,
    }

    log.debug(
        "Screen state | id=%s | texts=%d | elements=%d",
        screen_id, len(visible_texts), len(elements),
    )
    return state


def state_to_json(state: ScreenState) -> str:
    """Serialise a ScreenState to an indented JSON string."""
    return json.dumps(state, indent=2)
