"""
OCR engine built on PaddleOCR.
Returns structured list of dicts: {text, box, confidence}.

Supports both PaddleOCR v2.x and v3.x APIs automatically.
"""

from __future__ import annotations

from typing import Any, List

import numpy as np
from paddleocr import PaddleOCR

import config
from utils.logger import get_logger

log = get_logger(__name__)

OcrResult = dict[str, Any]
# {"text": str, "box": [x1, y1, x2, y2], "confidence": float}


class OcrEngine:
    """Thin, stateless wrapper around PaddleOCR for structured text extraction.

    Handles both PaddleOCR v2.x (.ocr()) and v3.x (.predict()) APIs.
    Uses the lightweight mobile model variant to stay within RAM limits on macOS.
    """

    # Max width to feed to OCR — downscaling saves ~80% memory on Retina screens
    _MAX_OCR_WIDTH = 1280

    def __init__(self) -> None:
        log.info("Initialising PaddleOCR (lang=%s) …", config.OCR_LANG)
        # PaddleOCR 3.x removed `show_log` and `use_angle_cls` from constructor.
        # Use ocr_version=PP-OCRv4 (mobile) to avoid OOM on large screens.
        for kwargs in [
            {"lang": config.OCR_LANG, "ocr_version": "PP-OCRv4"},                # v3.x mobile
            {"lang": config.OCR_LANG},                                            # v3.x default
            {"use_angle_cls": config.OCR_USE_ANGLE_CLS, "lang": config.OCR_LANG},# v2.x
        ]:
            try:
                self._ocr = PaddleOCR(**kwargs)
                break
            except TypeError:
                continue
        log.info("PaddleOCR ready.")

    def extract(self, image: np.ndarray) -> List[OcrResult]:
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
        results: List[OcrResult] = []

        # Downscale large Retina screens before OCR to avoid OOM kill
        image = self._maybe_downscale(image)

        # ── Try PaddleOCR v3.x API first (.predict) ──────────────────────────
        if hasattr(self._ocr, "predict"):
            try:
                raw = self._ocr.predict(image)
                return self._parse_v3(raw)
            except Exception as exc:
                log.debug("predict() failed (%s), falling back to ocr().", exc)

        # ── Fall back to PaddleOCR v2.x API (.ocr) ───────────────────────────
        try:
            raw = self._ocr.ocr(image)
            return self._parse_v2(raw)
        except Exception as exc:
            log.warning("OCR extraction failed: %s", exc)

        return results

    # ── Private parsers ───────────────────────────────────────────────────────

    def _parse_v3(self, raw: Any) -> List[OcrResult]:
        """Parse PaddleOCR v3.x predict() output."""
        results: List[OcrResult] = []
        if not raw:
            log.debug("OCR v3 returned no results.")
            return results

        # v3 returns a list of result objects with .rec_texts, .rec_scores, .dt_boxes
        for page in raw:
            texts  = getattr(page, "rec_texts",  None) or []
            scores = getattr(page, "rec_scores", None) or []
            boxes  = getattr(page, "dt_boxes",   None) or []

            for text, conf, polygon in zip(texts, scores, boxes):
                conf = float(conf)
                if conf < config.OCR_MIN_CONFIDENCE:
                    continue
                if not text or not text.strip():
                    continue

                xs  = [pt[0] for pt in polygon]
                ys  = [pt[1] for pt in polygon]
                box = [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]

                results.append({
                    "text":       text.strip(),
                    "box":        box,
                    "confidence": round(conf, 4),
                })

        log.debug("OCR v3 found %d text regions.", len(results))
        return results

    def _parse_v2(self, raw: Any) -> List[OcrResult]:
        """Parse PaddleOCR v2.x ocr() output."""
        results: List[OcrResult] = []
        if not raw or raw[0] is None:
            log.debug("OCR v2 returned no results.")
            return results

        for line in raw[0]:
            polygon, (text, conf) = line
            conf = float(conf)
            if conf < config.OCR_MIN_CONFIDENCE:
                continue
            if not text or not text.strip():
                continue

            xs  = [pt[0] for pt in polygon]
            ys  = [pt[1] for pt in polygon]
            box = [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]

            results.append({
                "text":       text.strip(),
                "box":        box,
                "confidence": round(conf, 4),
            })

        log.debug("OCR v2 found %d text regions.", len(results))
        return results

    def _maybe_downscale(self, image: np.ndarray) -> np.ndarray:
        """Downscale image if wider than _MAX_OCR_WIDTH to reduce memory usage."""
        import cv2
        h, w = image.shape[:2]
        if w <= self._MAX_OCR_WIDTH:
            return image
        scale  = self._MAX_OCR_WIDTH / w
        new_w  = self._MAX_OCR_WIDTH
        new_h  = int(h * scale)
        resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
        log.debug("Downscaled image: %dx%d → %dx%d for OCR.", w, h, new_w, new_h)
        return resized
