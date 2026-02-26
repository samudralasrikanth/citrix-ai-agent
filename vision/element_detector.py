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
        contours, _ = cv2.findContours(
            edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        elements: list[Element] = []
        for cnt in contours:
            if cv2.contourArea(cnt) < config.MIN_CONTOUR_AREA:
                continue
            x, y, w, h = cv2.boundingRect(cnt)
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
                    sep = " " if elem["label"] else ""
                    elem["label"] += sep + ocr["text"]

        seen: set[tuple] = {tuple(e["box"]) for e in elements}
        for ocr in ocr_results:
            if tuple(ocr["box"]) not in seen:
                elements.append(_make_element(ocr["box"], ocr["text"], "ocr_only"))

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
