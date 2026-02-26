"""
╔══════════════════════════════════════════════════════════════════════╗
║  OcrEngine — Enhanced PaddleOCR Wrapper                             ║
║                                                                      ║
║  Improvements over v1:                                              ║
║    • Pre-processing pipeline sharpens small text before OCR         ║
║    • extract_low_conf() drops threshold to 0.35 for short buttons   ║
║    • extract_with_scale() upscales a crop for tiny-text recovery    ║
║    • Consistent result schema: {text, norm, box, confidence}        ║
╚══════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import config

import config

log = logging.getLogger("OcrEngine")


class OcrEngine:
    """
    Singleton PaddleOCR wrapper with enhanced pre-processing.
    All extract methods return the same schema:
        [{"text": str, "box": [x1,y1,x2,y2], "confidence": float}, ...]
    """

    _instance:     Optional["OcrEngine"] = None
    _initialized:  bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if OcrEngine._initialized:
            return

        log.info("Initialising Vision OCR (lang=%s, prewarm=%s) …",
                 config.OCR_LANG, config.OCR_PREWARM)
        try:
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(
                lang=config.OCR_LANG,
                use_angle_cls=config.OCR_USE_ANGLE_CLS,
                show_log=False
            )
            if config.OCR_PREWARM:
                self._warm_up()
            OcrEngine._initialized = True
            log.info("OCR Engine ready.")
        except Exception as exc:
            log.error("CRITICAL: Failed to load OCR models: %s", exc)
            raise RuntimeError(f"OCR Initialization Error: {exc}")

    # ── Public extract methods ─────────────────────────────────────────────────

    def extract(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        Standard extract — uses config.OCR_MIN_CONFIDENCE (default 0.55).
        Applies pre-processing to improve small-text detection.
        """
        return self._run(image, min_conf=config.OCR_MIN_CONFIDENCE)

    def extract_low_conf(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        Low-confidence pass — use this when searching for short labels like
        "OK", "No", "Yes" that PaddleOCR often scores at 0.40–0.54.
        Threshold: 0.35 (catches more candidates; normalization handles FPs).
        """
        return self._run(image, min_conf=0.35)

    def extract_with_scale(
        self,
        image:     np.ndarray,
        scale:     float = config.OCR_UPSCALE_FACTOR,
        min_conf:  float = 0.35,
    ) -> List[Dict[str, Any]]:
        """
        Upscale *image* by *scale* before OCR — helps tiny buttons (< 20px tall).
        Bounding boxes are scaled back to original image coordinates.
        """
        h0, w0  = image.shape[:2]
        upscaled = cv2.resize(image, (int(w0 * scale), int(h0 * scale)),
                              interpolation=cv2.INTER_CUBIC)
        # Use _run directly, which will apply preprocessing once.
        results = self._run(upscaled, min_conf=min_conf)

        # Rescale boxes back to original coordinate space
        for r in results:
            r["box"] = [int(v / scale) for v in r["box"]]

        return results

    # ── Private ────────────────────────────────────────────────────────────────

    def _warm_up(self) -> None:
        blank = np.zeros((64, 64, 3), dtype=np.uint8)
        self._ocr.ocr(blank)
        log.debug("OCR Engine pre-warmed.")

    def _run(self, image: np.ndarray, min_conf: float) -> List[Dict[str, Any]]:
        """Internal: pre-process → PaddleOCR → filter → structure."""
        try:
            prepared = self._preprocess(image)
            raw      = self._ocr.ocr(prepared)
            return self._parse(raw, min_conf)
        except Exception as exc:
            log.error("OCR inference error: %s", exc)
            return []

    @staticmethod
    def _preprocess(image: np.ndarray) -> np.ndarray:
        """
        Pre-processing pipeline tuned for Citrix UI screenshots.
        Steps:
            1. Downscale very large images (RAM guard)
            2. Convert to LAB → CLAHE on L channel (contrast normalisation)
            3. Mild unsharp mask (sharpens small text)
            4. Denoise (reduces JPEG/Citrix compression noise)
        """
        h, w = image.shape[:2]

        # 1. Downscale if too large
        max_dim = 1920
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            image = cv2.resize(image, (int(w * scale), int(h * scale)),
                               interpolation=cv2.INTER_AREA)
            h, w  = image.shape[:2]

        # 2. CLAHE contrast normalisation
        lab   = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l     = clahe.apply(l)
        image = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

        # 3. Unsharp mask (sharpens button text edges)
        blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=1.0)
        image   = cv2.addWeighted(image, 1.5, blurred, -0.5, 0)

        # 4. Bilateral Filter (much faster than nlMeans, preserves edges)
        image = cv2.bilateralFilter(image, d=5, sigmaColor=75, sigmaSpace=75)
        return image

    @staticmethod
    def _parse(raw: Any, min_conf: float) -> List[Dict[str, Any]]:
        """Convert PaddleOCR raw output to our standard schema."""
        results: List[Dict[str, Any]] = []

        if not raw or not raw[0]:
            return results

        for line in raw[0]:
            polygon, (text, conf) = line
            text = (text or "").strip()
            if not text or conf < min_conf:
                continue

            xs  = [pt[0] for pt in polygon]
            ys  = [pt[1] for pt in polygon]
            box = [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]

            results.append({
                "text":       text,
                "box":        box,
                "confidence": round(float(conf), 4),
            })

        return results
