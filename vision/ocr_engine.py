from __future__ import annotations
import os
import cv2
import numpy as np
from typing import Any, List, Optional
from paddleocr import PaddleOCR

import config
from utils.logger import get_logger

log = get_logger(__name__)

class OcrEngine:
    """
    Singleton-like wrapper for PaddleOCR for production stability.
    Includes model pre-warming and high-DPI scaling support.
    """
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OcrEngine, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if OcrEngine._initialized:
            return
            
        log.info("Initialising Vision OCR (lang=%s, prewarm=%s) ...", 
                 config.OCR_LANG, config.OCR_PREWARM)
        
        try:
            self._ocr = PaddleOCR(
                lang=config.OCR_LANG,
                use_angle_cls=config.OCR_USE_ANGLE_CLS
            )
            
            if config.OCR_PREWARM:
                self._warm_up()
                
            OcrEngine._initialized = True
            log.info("Vision OCR Engine Ready.")
        except Exception as e:
            log.error("CRITICAL: Failed to load OCR models: %s", e)
            raise RuntimeError(f"OCR Initialization Error: {e}")

    def _warm_up(self):
        """Warm up the model with a blank image to avoid lag on first execution."""
        blank = np.zeros((100, 100, 3), dtype=np.uint8)
        self._ocr.ocr(blank)
        log.debug("OCR Engine pre-warmed.")

    def extract(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        Run OCR on an image and return structured results.
        """
        try:
            # Downscale if needed to save RAM on high-res monitors
            image = self._preprocess(image)
            
            # PaddleOCR v2.x returns list containing results
            raw = self._ocr.ocr(image)
            
            results = []
            if not raw or not raw[0]:
                return results

            for line in raw[0]:
                polygon, (text, conf) = line
                if conf < config.OCR_MIN_CONFIDENCE:
                    continue
                
                # Convert 4-point polygon to axis-aligned [x1, y1, x2, y2]
                xs = [pt[0] for pt in polygon]
                ys = [pt[1] for pt in polygon]
                box = [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]
                
                results.append({
                    "text": text.strip(),
                    "box": box,
                    "confidence": round(float(conf), 4)
                })
            
            return results
        except Exception as e:
            log.error("OCR Inference Error: %s", e)
            return []

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        """Apply noise reduction or scaling if necessary."""
        # For now just simple scaling if image is massive
        h, w = image.shape[:2]
        max_dim = 1600
        if w > max_dim or h > max_dim:
            scale = max_dim / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
        return image
