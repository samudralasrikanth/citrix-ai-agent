"""
╔═══════════════════════════════════════════════════════════════════╗
║  Citrix AI Vision Agent — Enterprise Element Fingerprinter        ║
║  Tosca-style semantic element identification:                     ║
║    • Text label (primary locator)                                 ║
║    • Element type (button / input / label / link / checkbox)      ║
║    • Context label (nearest sibling or ancestor text)             ║
║    • Relative position inside region (percentage, stable)         ║
║  Zero coordinate dependency — playbooks work even if window moves ║
╚═══════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))

import cv2
import numpy as np
import config
from utils.logger import get_logger

log = get_logger("ElementFingerprinter")


# ── Element type heuristics ────────────────────────────────────────────────────
_BUTTON_RE  = re.compile(r'\b(ok|cancel|yes|no|submit|login|sign in|connect|save|apply|'
                          r'close|next|back|finish|continue|run|stop|open|search|reset|'
                          r'add|remove|delete|edit|new|create|confirm|accept|reject)\b', re.I)
_INPUT_RE   = re.compile(r'\b(username|password|user name|user id|email|'
                          r'domain|address|host|port|name|search|filter)\b', re.I)
_CHECKBOX_RE= re.compile(r'^\s*[□✓✗☐☑☒]\s*', re.I)


class ElementFingerprint:
    """
    Position-independent descriptor for a UI element.
    Equivalent to Tosca TBox/TCD — stable across window moves and resolutions.
    """
    __slots__ = (
        "label", "elem_type", "context",
        "rel_x", "rel_y", "rel_w", "rel_h",
        "confidence",
    )

    def __init__(
        self,
        label:     str,
        elem_type: str,
        context:   str,
        rel_x:     float,
        rel_y:     float,
        rel_w:     float,
        rel_h:     float,
        confidence: float = 1.0,
    ):
        self.label      = label.strip()
        self.elem_type  = elem_type
        self.context    = context.strip()
        self.rel_x      = round(rel_x, 4)
        self.rel_y      = round(rel_y, 4)
        self.rel_w      = round(rel_w, 4)
        self.rel_h      = round(rel_h, 4)
        self.confidence = round(confidence, 3)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label":      self.label,
            "type":       self.elem_type,
            "context":    self.context,
            "rel_pos":    {"x": self.rel_x, "y": self.rel_y,
                           "w": self.rel_w, "h": self.rel_h},
            "confidence": self.confidence,
        }

    def to_playbook_target(self) -> str:
        """
        Returns the canonical playbook target string.
        Preferred: label text.  Fallback: type + context.
        """
        if self.label:
            return self.label
        if self.context:
            return f"{self.elem_type}:{self.context}"
        return f"element_at_{self.rel_x:.2f}_{self.rel_y:.2f}"

    def __repr__(self) -> str:
        return (f"<{self.elem_type} label={self.label!r} "
                f"ctx={self.context!r} pos=({self.rel_x:.2f},{self.rel_y:.2f})>")


class ElementFingerprinter:
    """
    Analyses a screenshot + OCR results to produce rich, stable ElementFingerprints
    for any (x, y) coordinate — even if no text is directly at that point.
    """

    def fingerprint_at(
        self,
        frame:       np.ndarray,
        ocr_results: List[Dict[str, Any]],
        rx:          float,   # relative x (pixels from region left)
        ry:          float,   # relative y (pixels from region top)
    ) -> ElementFingerprint:
        """
        Build the best possible semantic descriptor for the element at (rx, ry).
        """
        h_img, w_img = frame.shape[:2]

        # 1. Direct hit: text box containing the click point
        direct = self._find_direct_hit(ocr_results, rx, ry)

        if direct:
            label, box = direct
            elem_type  = self._classify_text(label, frame, box)
            context    = self._find_context(ocr_results, box, rx, ry, exclude=label)
            rx1, ry1, rx2, ry2 = box
            return ElementFingerprint(
                label     = label,
                elem_type = elem_type,
                context   = context,
                rel_x     = rx1 / w_img,
                rel_y     = ry1 / h_img,
                rel_w     = (rx2 - rx1) / w_img,
                rel_h     = (ry2 - ry1) / h_img,
                confidence= 0.95,
            )

        # 2. Nearest neighbour: closest OCR text within 80px
        nearest = self._find_nearest(ocr_results, rx, ry, max_dist=80)
        if nearest:
            label, box, dist = nearest
            elem_type = self._classify_text(label, frame, box)
            context   = self._find_context(ocr_results, box, rx, ry, exclude=label)
            rx1, ry1, rx2, ry2 = box
            conf = max(0.5, 1.0 - dist / 160)
            return ElementFingerprint(
                label     = label,
                elem_type = elem_type,
                context   = context,
                rel_x     = rx1 / w_img,
                rel_y     = ry1 / h_img,
                rel_w     = (rx2 - rx1) / w_img,
                rel_h     = (ry2 - ry1) / h_img,
                confidence= conf,
            )

        # 3. Visual contour — no text at all (icon / image button)
        contour = self._find_contour_element(frame, rx, ry)
        if contour:
            x1, y1, x2, y2 = contour
            ctx = self._find_context_by_pos(ocr_results, (x1+x2)//2, (y1+y2)//2)
            return ElementFingerprint(
                label     = "",
                elem_type = "icon_button",
                context   = ctx,
                rel_x     = x1 / w_img,
                rel_y     = y1 / h_img,
                rel_w     = (x2 - x1) / w_img,
                rel_h     = (y2 - y1) / h_img,
                confidence= 0.4,
            )

        # 4. Absolute fallback (should be very rare)
        return ElementFingerprint(
            label     = "",
            elem_type = "unknown",
            context   = "",
            rel_x     = rx / w_img,
            rel_y     = ry / h_img,
            rel_w     = 0.0,
            rel_h     = 0.0,
            confidence= 0.1,
        )

    # ── Private helpers ──────────────────────────────────────────────────────────

    def _find_direct_hit(
        self,
        ocr: List[Dict],
        rx: float,
        ry: float,
    ) -> Optional[Tuple[str, List[int]]]:
        for res in ocr:
            bx1, by1, bx2, by2 = res["box"]
            pad = 12
            if bx1 - pad <= rx <= bx2 + pad and by1 - pad <= ry <= by2 + pad:
                return res["text"].strip(), res["box"]
        return None

    def _find_nearest(
        self,
        ocr: List[Dict],
        rx: float,
        ry: float,
        max_dist: float,
    ) -> Optional[Tuple[str, List[int], float]]:
        best_d, best_res = float("inf"), None
        for res in ocr:
            bx1, by1, bx2, by2 = res["box"]
            cx, cy = (bx1 + bx2) / 2, (by1 + by2) / 2
            d = ((cx - rx) ** 2 + (cy - ry) ** 2) ** 0.5
            if d < best_d and d <= max_dist:
                best_d, best_res = d, res
        if best_res:
            return best_res["text"].strip(), best_res["box"], best_d
        return None

    def _find_contour_element(
        self,
        frame: np.ndarray,
        rx: float,
        ry: float,
    ) -> Optional[List[int]]:
        """Find smallest contour box that contains the click point."""
        gray    = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        edges   = cv2.Canny(blurred, 30, 100)
        cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best_area, best_box = float("inf"), None
        for cnt in cnts:
            x, y, w, h = cv2.boundingRect(cnt)
            area = w * h
            if area < 100:
                continue
            if x <= rx <= x + w and y <= ry <= y + h:
                if area < best_area:
                    best_area = area
                    best_box  = [x, y, x + w, y + h]
        return best_box

    def _classify_text(
        self,
        text: str,
        frame: np.ndarray,
        box: List[int],
    ) -> str:
        """
        Classify the element type from text patterns and visual cues.
        This mirrors Tosca's control-type classification.
        """
        if _CHECKBOX_RE.match(text):
            return "checkbox"
        if _INPUT_RE.search(text):
            return "input_field"
        if _BUTTON_RE.search(text):
            return "button"

        # Visual cue: sample background colour inside box for button-like appearance
        try:
            x1, y1, x2, y2 = box
            roi = frame[max(0,y1):y2, max(0,x1):x2]
            if roi.size > 0:
                mean_val = roi.mean()
                if mean_val > 180:      # Light background → likely a button
                    return "button"
                elif mean_val < 50:     # Dark → text label on dark bg
                    return "label"
        except Exception:
            pass

        return "text_element"

    def _find_context(
        self,
        ocr: List[Dict],
        box: List[int],
        rx: float,
        ry: float,
        exclude: str,
    ) -> str:
        """
        Find the nearest context label: prefer text ABOVE or to LEFT of the element.
        Mirrors how Tosca finds form-field labels.
        """
        bx1, by1, bx2, by2 = box
        candidates = []

        for res in ocr:
            t = res["text"].strip()
            if not t or t == exclude:
                continue
            rx1, ry1, rx2, ry2 = res["box"]
            cx, cy = (rx1 + rx2) / 2, (ry1 + ry2) / 2

            # Above: within x-range and above our box
            if rx1 < bx2 and rx2 > bx1 and cy < by1:
                dist = by1 - cy
                candidates.append((dist, t))
            # To the left: same y-band, left of box
            elif cy > by1 and cy < by2 and cx < bx1:
                dist = bx1 - cx
                candidates.append((dist, t))

        if candidates:
            candidates.sort()
            return candidates[0][1]
        return ""

    def _find_context_by_pos(self, ocr: List[Dict], cx: float, cy: float) -> str:
        best_d, ctx = float("inf"), ""
        for res in ocr:
            bx1, by1, bx2, by2 = res["box"]
            ecx, ecy = (bx1 + bx2) / 2, (by1 + by2) / 2
            d = ((ecx - cx) ** 2 + (ecy - cy) ** 2) ** 0.5
            if d < best_d:
                best_d = d
                ctx    = res["text"].strip()
        return ctx
