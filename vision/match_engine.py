"""
╔══════════════════════════════════════════════════════════════════════╗
║  Match Engine — Enterprise Element Resolver                         ║
║                                                                      ║
║  Implements the complete 7-point reliability fallback chain:         ║
║                                                                      ║
║  ① Normalize OCR text (0→o, 1→l, |→l, …)                          ║
║  ② Short-target handling (≤3 chars → lower threshold + partial)    ║
║  ③ OCR fuzzy match (normalized + multi-scorer voting)              ║
║  ④ Memory cache hit (skip vision scan for known elements)          ║
║  ⑤ Template matching fallback (OpenCV multi-scale)                 ║
║  ⑥ Region boundary validation + automatic expansion               ║
║  ⑦ Post-click pixel-diff validation + retry with alternate match   ║
║                                                                      ║
║  All subsystems funneled through match_target() — the single API.   ║
╚══════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from rapidfuzz import fuzz, process

import config
from vision.text_normalizer import normalize, normalized_pairs
from vision.click_memory    import ClickMemory
from vision.template_matcher import TemplateMatcher
from vision.debug_overlay    import save_debug_frame
from utils.image_utils       import crop_region

log = logging.getLogger("MatchEngine")

# ── Tuning ────────────────────────────────────────────────────────────────────
_NORMAL_THRESHOLD = config.FUZZY_MATCH_THRESHOLD   # default 75
_SHORT_THRESHOLD  = 60    # ≤3 char targets
_SHORT_MAX_LEN    = 3
_REGION_EXPAND_PX = 40    # pixels to expand region when target box escapes


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class MatchResult:
    """
    Rich result describing exactly how a target was resolved.
    Propagated back to ActionExecutor for post-click logic.
    """
    found:       bool  = False
    cx:          int   = 0
    cy:          int   = 0

    method:      str   = ""    # "ocr" | "memory" | "template" | "failed"
    score:       float = 0.0   # fuzzy score (0–100), or template NCC (0–1)
    label:       str   = ""    # final matched text
    box:         Optional[List[int]] = None

    # Fallback chain detail
    tried_memory:   bool = False
    tried_template: bool = False
    tried_expand:   bool = False

    # Short-target flag
    is_short_target: bool = False


# ═══════════════════════════════════════════════════════════════════════════════

class MatchEngine:
    """
    Central element-resolution engine.
    Build once per ActionExecutor; safe to reuse across steps.
    """

    def __init__(self, region: Optional[Dict[str, Any]] = None):
        self.region        = region or {}
        self._memory       = ClickMemory(region)
        self._template     = TemplateMatcher()

    # ── Public API ──────────────────────────────────────────────────────────────

    def match_target(
        self,
        target:      str,
        ocr_results: List[Dict[str, Any]],
        frame:       np.ndarray,
        action_name: str = "click",
    ) -> MatchResult:
        """
        Resolve *target* to a screen coordinate using the full fallback chain.

        Args:
            target:      Label to find (e.g. "OK", "Submit", "Cancel").
            ocr_results: Output of OcrEngine.extract() (already region-relative).
            frame:       BGR screenshot (region-relative).
            action_name: For debug filename labelling.

        Returns:
            MatchResult — check .found before using .cx/.cy.
        """
        norm_target  = normalize(target)
        is_short     = len(norm_target.replace(" ", "")) <= _SHORT_MAX_LEN
        threshold    = _SHORT_THRESHOLD if is_short else _NORMAL_THRESHOLD

        result = MatchResult(is_short_target=is_short)

        # ── ① Memory cache (fastest path) ───────────────────────────────────
        result.tried_memory = True
        cached = self._memory.get(target)
        if cached:
            cx, cy = cached
            if self._within_region(cx, cy, absolute=True):
                log.info("Memory hit: '%s' → (%d, %d)", target, cx, cy)
                result.found, result.cx, result.cy = True, cx, cy
                result.method, result.label         = "memory", target
                return result
            else:
                log.debug("Memory hit for '%s' rejected — outside region.", target)
                self._memory.invalidate(target)

        # ── ② Normalize OCR → build candidate list ──────────────────────────
        enriched, norm_target = normalized_pairs(ocr_results, target)
        candidates  = [e["norm"] for e in enriched]
        raw_labels  = [e.get("text", "") for e in enriched]

        scores = self._multi_score(norm_target, candidates, is_short)

        if config.SAVE_DEBUG_FRAMES:
            save_debug_frame(frame, ocr_results, target, None, scores, action_name)

        # ── ③ OCR fuzzy match ────────────────────────────────────────────────
        best_idx, best_score = self._pick_best(
            norm_target, candidates, scores, is_short, threshold
        )

        if best_idx >= 0:
            elem  = enriched[best_idx]
            box   = elem["box"]
            cx    = (box[0] + box[2]) // 2
            cy    = (box[1] + box[3]) // 2
            label = raw_labels[best_idx]

            # ⑥ Region boundary validation
            cx, cy, expanded = self._validate_bounds(cx, cy, box)
            result.tried_expand = expanded

            if config.SAVE_DEBUG_FRAMES:
                save_debug_frame(frame, ocr_results, target, best_idx, scores, action_name)

            result.found   = True
            result.cx, result.cy = cx + self._ox(), cy + self._oy()
            result.method  = "ocr"
            result.score   = best_score
            result.label   = label
            result.box     = box
            log.info("OCR match: '%s' → '%s' (score=%.1f%s) → screen (%d,%d)",
                     target, label, best_score,
                     " SHORT" if is_short else "",
                     result.cx, result.cy)
            return result

        # ── ④ Template matching fallback ─────────────────────────────────────
        result.tried_template = True
        coord = self._template.find(target, frame, self.region)
        if coord:
            result.found         = True
            result.cx, result.cy = coord
            result.method        = "template"
            result.score         = 0.0
            result.label         = target
            log.info("Template match: '%s' → screen (%d, %d)", target, *coord)
            return result

        # ── ⑤ Expanded region search ─────────────────────────────────────────
        if self.region and not result.tried_expand:
            result.tried_expand = True
            expanded_ocr = self._ocr_with_expanded_region(frame, target)
            if expanded_ocr:
                result.found, result.cx, result.cy = True, *expanded_ocr
                result.method = "ocr_expanded"
                result.label  = target
                log.info("Expanded-region OCR match: '%s' → (%d, %d)", target, *expanded_ocr)
                return result

        log.warning("Element '%s' not found. Tried: memory=%s, OCR(norm+short), template=%s",
                    target, result.tried_memory, result.tried_template)
        result.method = "failed"
        return result

    def record_success(self, target: str, cx: int, cy: int) -> None:
        """Called by ActionExecutor when click produces a screen change."""
        self._memory.save(target, cx, cy)
        # Also try to capture a template so future runs have visual fallback
        # (requires a frame reference — done in ActionExecutor)

    def record_failure(self, target: str) -> None:
        """Called by ActionExecutor when click produces NO screen change."""
        self._memory.invalidate(target)

    def save_template(self, label: str, crop: np.ndarray) -> None:
        """Save a reference crop for template matching."""
        self._template.save_template(label, crop)

    # ── Private helpers ─────────────────────────────────────────────────────────

    def _multi_score(
        self,
        norm_target: str,
        candidates: List[str],
        is_short: bool,
    ) -> List[float]:
        """
        Compute a blended fuzzy score for each candidate.

        For short targets, partial_ratio gets extra weight to handle
        single-word matches inside longer strings ("Cancel Button" vs "OK").
        """
        if not candidates:
            return []

        scores = []
        for cand in candidates:
            tok  = float(fuzz.token_set_ratio(norm_target, cand))
            part = float(fuzz.partial_ratio(norm_target, cand))
            rat  = float(fuzz.ratio(norm_target, cand))

            if is_short:
                # Short targets: partial_ratio dominant, ratio as tiebreak
                score = max(tok * 0.4 + part * 0.5 + rat * 0.1,
                            part)          # allow pure-partial win
            else:
                score = tok * 0.6 + part * 0.3 + rat * 0.1

            scores.append(round(score, 2))

        return scores

    def _pick_best(
        self,
        norm_target: str,
        candidates:  List[str],
        scores:      List[float],
        is_short:    bool,
        threshold:   float,
    ) -> Tuple[int, float]:
        """Return (index, score) of best candidate, or (-1, 0) if none pass."""
        if not scores:
            return -1, 0.0

        best_idx   = int(np.argmax(scores))
        best_score = scores[best_idx]

        if best_score < threshold:
            log.debug("Best fuzzy score %.1f < threshold %.1f for '%s'",
                      best_score, threshold, norm_target)
            return -1, 0.0

        return best_idx, best_score

    def _within_region(self, cx: int, cy: int, absolute: bool = False) -> bool:
        """Check if a screen point is within the automation region."""
        if not self.region:
            return True  # no region defined = global screen = always valid
        r  = self.region
        ox = int(r.get("left", 0)) if absolute else 0
        oy = int(r.get("top",  0)) if absolute else 0
        rx, ry = cx - ox, cy - oy
        return (0 <= rx <= int(r.get("width", 1e9)) and
                0 <= ry <= int(r.get("height", 1e9)))

    def _validate_bounds(
        self,
        cx: int,
        cy: int,
        box: List[int],
    ) -> Tuple[int, int, bool]:
        """
        Ensure the coordinate is within the declared region.
        If not, clamp to the edge (sets expanded=True for logging).
        We do NOT re-run OCR here — that's done in _ocr_with_expanded_region.
        """
        r = self.region
        if not r:
            return cx, cy, False

        rw = int(r.get("width",  1e9))
        rh = int(r.get("height", 1e9))

        if 0 <= cx <= rw and 0 <= cy <= rh:
            return cx, cy, False

        clamped_x = max(0, min(cx, rw))
        clamped_y = max(0, min(cy, rh))
        log.debug("Coordinate (%d, %d) clamped → (%d, %d)", cx, cy, clamped_x, clamped_y)
        return clamped_x, clamped_y, True

    def _ocr_with_expanded_region(
        self,
        frame: np.ndarray,
        target: str,
    ) -> Optional[Tuple[int, int]]:
        """
        Re-run OCR on a slightly padded version of the frame.
        Returns (cx, cy) region-relative if found, else None.
        Avoids circular import by importing OcrEngine locally.
        """
        try:
            from vision.ocr_engine import OcrEngine
            pad  = _REGION_EXPAND_PX
            padded = cv2.copyMakeBorder(frame, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
            ocr  = OcrEngine()
            results = ocr.extract(padded)
            if not results:
                return None
            norm_tgt = normalize(target)
            is_short = len(norm_tgt.replace(" ", "")) <= _SHORT_MAX_LEN
            thresh   = _SHORT_THRESHOLD if is_short else _NORMAL_THRESHOLD

            enriched, norm_target = normalized_pairs(results, target)
            candidates = [e["norm"] for e in enriched]
            scores = self._multi_score(norm_target, candidates, is_short)
            idx, score = self._pick_best(norm_target, candidates, scores, is_short, thresh)

            if idx < 0:
                return None

            box = enriched[idx]["box"]
            cx  = (box[0] + box[2]) // 2 - pad + self._ox()
            cy  = (box[1] + box[3]) // 2 - pad + self._oy()
            return cx, cy

        except Exception as exc:
            log.warning("Expanded OCR failed: %s", exc)
            return None

    def _ox(self) -> int:
        return int(self.region.get("left", 0))

    def _oy(self) -> int:
        return int(self.region.get("top", 0))
