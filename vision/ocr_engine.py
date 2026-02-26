"""
OCR engine built on PaddleOCR.
Returns structured list of dicts: {text, box, confidence}.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from paddleocr import PaddleOCR

import config
from utils.logger import get_logger

log = get_logger(__name__)

OcrResult = dict[str, Any]
# {"text": str, "box": [x1, y1, x2, y2], "confidence": float}


class OcrEngine:
    """Thin, stateless wrapper around PaddleOCR for structured text extraction."""

    def __init__(self) -> None:
        log.info("Initialising PaddleOCR (lang=%s) …", config.OCR_LANG)
        self._ocr = PaddleOCR(
            use_angle_cls=config.OCR_USE_ANGLE_CLS,
            lang=config.OCR_LANG,
            show_log=False,
        )
        log.info("PaddleOCR ready.")

    def extract(self, image: np.ndarray) -> list[OcrResult]:
        """
        Run OCR on a BGR NumPy image.

        Args:
            image: BGR frame from ScreenCapture.

        Returns:
            List of OCR result dicts, filtered by config.OCR_MIN_CONFIDENCE.
            Each dict:
              {
                "text":       str,
                "box":        [x1, y1, x2, y2],   ← axis-aligned bbox
                "confidence": float
              }
        """
        raw = self._ocr.ocr(image, cls=config.OCR_USE_ANGLE_CLS)

        results: list[OcrResult] = []
        if not raw or raw[0] is None:
            log.debug("OCR returned no results.")
            return results

        for line in raw[0]:
            polygon, (text, conf) = line
            if conf < config.OCR_MIN_CONFIDENCE:
                continue

            xs  = [pt[0] for pt in polygon]
            ys  = [pt[1] for pt in polygon]
            box = [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]

            results.append(
                {
                    "text":       text.strip(),
                    "box":        box,
                    "confidence": round(float(conf), 4),
                }
            )

        log.debug("OCR found %d text regions.", len(results))
        return results
