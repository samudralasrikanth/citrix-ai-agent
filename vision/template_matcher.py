"""
╔══════════════════════════════════════════════════════════════════╗
║  Template Matcher — Visual Fallback for OCR Failures            ║
║  Uses OpenCV multi-scale template matching to locate a saved    ║
║  reference image of a button when OCR cannot find it.           ║
╚══════════════════════════════════════════════════════════════════╝

Workflow:
    1. Caller saves a reference crop: save_template(label, crop)
    2. On OCR failure, ActionExecutor calls find_template(label, frame)
    3. Returns (cx, cy) of best match centre, or None

Template storage: memory/templates/<context_id>/<normalized_label>.png
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

import config
from vision.text_normalizer import normalize

log = logging.getLogger("TemplateMatcher")

_TEMPLATE_DIR = config.MEMORY_DIR / "templates"
_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

# ── Tuning constants ──────────────────────────────────────────────────────────
_MIN_MATCH_SCORE = 0.72    # Normalised cross-correlation threshold
_SCALE_RANGE     = (0.85, 1.15, 0.05)   # start, stop, step for multi-scale


class TemplateMatcher:
    """
    Stateless multi-scale OpenCV template matcher.
    Instantiate once and reuse; it holds no mutable state.
    """

    def save_template(self, label: str, crop: np.ndarray, context_id: str = "default") -> None:
        """
        Persist a cropped button image for future visual matching.

        Args:
            label:      Human-readable button label.
            crop:       BGR image array.
            context_id: Folder name (e.g. test_id or app_name).
        """
        key  = normalize(label) or "unknown"
        ctx_dir = _TEMPLATE_DIR / context_id
        ctx_dir.mkdir(parents=True, exist_ok=True)
        
        path = ctx_dir / f"{key}.png"
        ok   = cv2.imwrite(str(path), crop)
        if ok:
            log.debug("Template saved: [%s] %s → %s", context_id, label, path.name)
        else:
            log.warning("Failed to save template for '%s' in context '%s'", label, context_id)

    def find(
        self,
        label:      str,
        frame:      np.ndarray,
        region:     Optional[dict] = None,
        context_id: str = "default",
    ) -> Optional[Tuple[int, int]]:
        """
        Search *frame* for a stored template image of *label*.
        """
        key  = normalize(label) or "unknown"
        path = _TEMPLATE_DIR / context_id / f"{key}.png"
        if not path.exists():
            log.debug("No template found for '%s' in context '%s'", label, context_id)
            return None

        tmpl = cv2.imread(str(path))
        if tmpl is None or tmpl.size == 0:
            log.warning("Template file corrupt: %s", path)
            return None

        result = self._multi_scale_match(frame, tmpl)
        if result is None:
            log.debug("Template match failed for '%s' (score below threshold)", label)
            return None

        rx, ry = result  # region-relative centre
        ox     = int(region.get("left", 0)) if region else 0
        oy     = int(region.get("top",  0)) if region else 0
        cx, cy = rx + ox, ry + oy
        log.info("Template match '%s' → screen (%d, %d)", label, cx, cy)
        return cx, cy

    def find_from_crop(
        self,
        template_crop: np.ndarray,
        frame: np.ndarray,
        region: Optional[dict] = None,
    ) -> Optional[Tuple[int, int]]:
        """
        Match an *ad-hoc* template crop (not from disk) against *frame*.
        Useful when a reference image is captured live.
        """
        result = self._multi_scale_match(frame, template_crop)
        if result is None:
            return None
        ox = int(region.get("left", 0)) if region else 0
        oy = int(region.get("top",  0)) if region else 0
        return result[0] + ox, result[1] + oy

    # ── Private ────────────────────────────────────────────────────────────────

    def _multi_scale_match(
        self,
        haystack: np.ndarray,
        needle: np.ndarray,
    ) -> Optional[Tuple[int, int]]:
        """
        Run TM_CCOEFF_NORMED at multiple scales.
        Returns (cx, cy) *relative to haystack origin* for the best match.
        """
        h_gray = cv2.cvtColor(haystack, cv2.COLOR_BGR2GRAY)
        n_gray = cv2.cvtColor(needle,   cv2.COLOR_BGR2GRAY)

        th, tw = n_gray.shape[:2]
        best_score = -1.0
        best_loc   = None
        best_scale = 1.0

        start, stop, step = _SCALE_RANGE
        scale = start
        while scale <= stop + 1e-6:
            nh = max(4, int(th * scale))
            nw = max(4, int(tw * scale))
            resized = cv2.resize(n_gray, (nw, nh))

            # Skip if template is larger than haystack
            if resized.shape[0] > h_gray.shape[0] or resized.shape[1] > h_gray.shape[1]:
                scale += step
                continue

            result = cv2.matchTemplate(h_gray, resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val > best_score:
                best_score = max_val
                best_loc   = max_loc
                best_scale = scale

            scale = round(scale + step, 3)

        if best_score < _MIN_MATCH_SCORE or best_loc is None:
            return None

        th_s = int(th * best_scale)
        tw_s = int(tw * best_scale)
        cx   = best_loc[0] + tw_s // 2
        cy   = best_loc[1] + th_s // 2
        log.debug("Template match score=%.3f scale=%.2f → (%d, %d)", best_score, best_scale, cx, cy)
        return cx, cy
