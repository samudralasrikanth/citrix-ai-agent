"""
Element detector: locates clickable UI regions using Canny edge + contour analysis,
then merges OCR labels onto those regions.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

import config
from utils.logger import get_logger

log = get_logger(__name__)

Element = dict[str, Any]
# {"box": [x1,y1,x2,y2], "label": str, "cx": int, "cy": int, "source": str}


class ElementDetector:
    """
    Detects UI elements (buttons, text fields, panels) via contour analysis
    and annotates them with OCR labels where bounding boxes overlap.
    """

    def detect_contours(self, image: np.ndarray) -> list[Element]:
        """
        Identify rectangular UI regions through Canny edges → contours.

        Args:
            image: BGR image array.

        Returns:
            List of Element dicts (label is empty at this stage).
        """
        gray    = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges   = cv2.Canny(blurred, config.EDGE_CANNY_LOW, config.EDGE_CANNY_HIGH)
        # Use RETR_LIST to find nested elements (not just the outer window frame)
        contours, _ = cv2.findContours(
            edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
        )

        elements: list[Element] = []
        img_h, img_w = image.shape[:2]
        
        for cnt in contours:
            # Approximate the contour to a polygon to check if it is rectangular
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            
            if cv2.contourArea(cnt) < config.MIN_CONTOUR_AREA:
                continue
                
            x, y, w, h = cv2.boundingRect(cnt)
            
            # Skip the very large outer window box (usually >= 95% of image size)
            if w > img_w * 0.95 and h > img_h * 0.95:
                continue
                
            # Deduplicate very similar boxes (avoids double-detecting same box edges)
            is_dupe = False
            for existing in elements:
                ex1, ey1, ex2, ey2 = existing["box"]
                if abs(x - ex1) < 10 and abs(y - ey1) < 10 and abs(w - (ex2 - ex1)) < 10:
                    is_dupe = True
                    break
            
            if not is_dupe:
                elements.append(_make_element([x, y, x + w, y + h], "", "contour"))

        log.debug("Detected %d contour elements.", len(elements))
        return elements

    def merge_with_ocr(
        self,
        elements: list[Element],
        ocr_results: list[dict],
    ) -> list[Element]:
        """
        Label contour elements whose boxes overlap with OCR bounding boxes.
        Orphan OCR results (no matching contour) are appended as their own elements.

        Args:
            elements:    Output of detect_contours().
            ocr_results: Output of OcrEngine.extract().

        Returns:
            Combined, labelled element list.
        """
        for elem in elements:
            ex1, ey1, ex2, ey2 = elem["box"]
            for ocr in ocr_results:
                ox1, oy1, ox2, oy2 = ocr["box"]
                if ox1 < ex2 and ox2 > ex1 and oy1 < ey2 and oy2 > ey1:
                    from vision.text_normalizer import normalize
                    txt = normalize(ocr["text"])
                    sep = " " if elem["label"] else ""
                    elem["label"] += sep + txt

        seen: set[tuple] = {tuple(e["box"]) for e in elements}
        for ocr in ocr_results:
            if tuple(ocr["box"]) not in seen:
                from vision.text_normalizer import normalize
                elements.append(_make_element(ocr["box"], normalize(ocr["text"]), "ocr_only"))

        return elements


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_element(box: list[int], label: str, source: str) -> Element:
    x1, y1, x2, y2 = box
    return {
        "box":    box,
        "label":  label,
        "cx":     (x1 + x2) // 2,
        "cy":     (y1 + y2) // 2,
        "source": source,
    }
