"""
╔══════════════════════════════════════════════════════════════════════╗
║  Hardened Action Executor — Production Citrix Automation            ║
║                                                                      ║
║  Integrates the full MatchEngine reliability chain:                 ║
║    • Text normalisation                                             ║
║    • Short-target adaptive threshold                               ║
║    • OCR multi-scorer fuzzy voting                                  ║
║    • Memory cache (fastest path)                                    ║
║    • Template matching fallback                                     ║
║    • Region boundary validation + automatic expansion              ║
║    • Post-click pixel-diff validation + retry with alternate match  ║
║    • Debug overlay saved on every step (when enabled)              ║
╚══════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np
import pyautogui

import config
from utils.image_utils import crop_region, pixel_diff_ratio, draw_elements, save_image
from utils.logger import get_logger
from vision.similarity   import best_match          # kept for wait_for
from vision.match_engine import MatchEngine, MatchResult
from vision.debug_overlay import save_debug_frame

log = get_logger(__name__)

# ── PyAutoGUI safety ──────────────────────────────────────────────────────────
pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.15   # slightly tighter than default for Citrix responsiveness

# ── Post-click retry budgets ──────────────────────────────────────────────────
_CLICK_RETRY_DELAY = 0.8   # seconds between post-click retries
_MAX_CLICK_RETRIES = 2     # extra attempts if no screen change detected


class ActionExecutor:
    """
    Executes automation actions against the live OS with high observability.

    lifecycle:
        executor = ActionExecutor(region=region_dict)
        result   = executor.execute(action, ocr_results, frame, capture_fn)
    """

    def __init__(self, region: Optional[Dict[str, Any]] = None):
        self.region       = region or {}
        self._engine      = MatchEngine(region)
        self._last_score  = 0.0

    def execute(
        self,
        action:      Dict[str, Any],
        ocr_results: List[Dict[str, Any]],
        frame:       np.ndarray,
        capture_fn:  Callable[[], np.ndarray],
    ) -> Dict[str, Any]:
        """
        Main entry point for all action types.

        Args:
            action:      Step dict with 'action', 'target', 'value' keys.
            ocr_results: Output of OcrEngine.extract() for the current frame.
            frame:       Current BGR screenshot (region-relative).
            capture_fn:  Zero-arg callable that returns a fresh BGR frame.

        Returns:
            Dict with keys: success, error, error_code, target_center,
                            fuzzy_score, screen_changed, match_method.
        """
        atype   = action.get("action",  "").lower()
        target  = action.get("target",  action.get("target_text", ""))
        value   = action.get("value",   "")

        result: Dict[str, Any] = {
            "success":        False,
            "error":          None,
            "error_code":     0,
            "target_center":  None,
            "fuzzy_score":    0.0,
            "screen_changed": False,
            "match_method":   "",
        }

        try:
            before_frame = capture_fn()

            if atype == "click":
                result.update(self._click(target, ocr_results, frame, capture_fn, before_frame))
            elif atype == "type":
                result.update(self._type(target, value, ocr_results, frame, capture_fn, before_frame))
            elif atype == "wait_for":
                return self._wait_for(target, capture_fn)
            elif atype == "screenshot":
                img   = capture_fn()
                fname = f"manual_{int(time.time())}.png"
                save_image(img, str(config.SCREENSHOTS_DIR / fname))
                result["message"] = f"Saved: {fname}"
                result["success"] = True
                return result
            elif atype == "pause":
                time.sleep(float(value or 1.0))
                result["success"] = True
                return result
            else:
                result["error"] = f"Unknown action type: '{atype}'"

        except Exception as exc:
            log.exception("Critical automation failure: %s", exc)
            result.update(success=False, error=str(exc), error_code=500)

        return result

    # ── Action implementations ─────────────────────────────────────────────────

    def _click(
        self,
        target:       str,
        ocr_results:  List[Dict[str, Any]],
        frame:        np.ndarray,
        capture_fn:   Callable[[], np.ndarray],
        before_frame: np.ndarray,
        action_name:  str = "click",
    ) -> Dict[str, Any]:
        """
        Resolve → click → validate → retry with alternate match if needed.
        """
        # ── Resolve target to coordinates ─────────────────────────────────────
        match = self._engine.match_target(target, ocr_results, frame, action_name)

        if not match.found:
            return {
                "success":    False,
                "error":      f"Element '{target}' not found "
                              f"[tried memory={match.tried_memory}, "
                              f"template={match.tried_template}, "
                              f"expand={match.tried_expand}]",
                "error_code": config.ERROR_CODES["ERR_MATCH_FAIL"],
            }

        # ── Execute click + validate ──────────────────────────────────────────
        cx, cy        = match.cx, match.cy
        screen_changed = False
        last_error     = None

        for attempt in range(1, _MAX_CLICK_RETRIES + 2):  # 1,2,3
            try:
                pyautogui.click(cx, cy)
            except pyautogui.FailSafeException:
                return {"success": False, "error": "PyAutoGUI failsafe triggered",
                        "error_code": config.ERROR_CODES["ERR_PERM"]}
            except Exception as exc:
                return {"success": False, "error": str(exc),
                        "error_code": config.ERROR_CODES["ERR_PERM"]}

            time.sleep(config.STEP_DELAY_SEC)
            after_frame   = capture_fn()
            diff          = pixel_diff_ratio(before_frame, after_frame)
            screen_changed = diff >= config.PIXEL_DIFF_THRESHOLD

            if screen_changed:
                # ✅ Successful click — save to memory and possible template
                self._engine.record_success(target, cx, cy)
                self._try_save_template(target, before_frame, match)
                break

            log.warning(
                "Click '%s' attempt %d — no screen change (diff=%.4f px). %s",
                target, attempt, diff,
                "Retrying…" if attempt <= _MAX_CLICK_RETRIES else "Giving up.",
            )

            if attempt <= _MAX_CLICK_RETRIES:
                # Invalidate stale memory so next retry goes through full chain
                self._engine.record_failure(target)

                # Re-capture and re-resolve (screen may have changed since)
                new_frame = capture_fn()
                from vision.ocr_engine import OcrEngine
                new_ocr   = OcrEngine().extract(new_frame)
                new_match = self._engine.match_target(target, new_ocr, new_frame, action_name)
                if new_match.found:
                    cx, cy = new_match.cx, new_match.cy
                    match  = new_match

                time.sleep(_CLICK_RETRY_DELAY)

        # ── Populate result ───────────────────────────────────────────────────
        result = {
            "success":        True,
            "target_center":  (cx, cy),
            "fuzzy_score":    match.score,
            "screen_changed": screen_changed,
            "match_method":   match.method,
        }
        if not screen_changed:
            result["error_code"] = config.ERROR_CODES["ERR_NO_CHANGE"]
            log.warning(
                "Action '%s' on '%s' completed without a detectable screen change.",
                action_name, target,
            )
        return result

    def _type(
        self,
        target:       str,
        value:        str,
        ocr_results:  List[Dict[str, Any]],
        frame:        np.ndarray,
        capture_fn:   Callable[[], np.ndarray],
        before_frame: np.ndarray,
    ) -> Dict[str, Any]:
        res = self._click(target, ocr_results, frame, capture_fn, before_frame, action_name="type")
        if not res["success"]:
            return res
        time.sleep(0.3)
        pyautogui.hotkey("ctrl", "a")
        pyautogui.press("backspace")
        pyautogui.typewrite(value, interval=0.03)
        log.info("Typed '%s' into '%s'", value, target)
        return res

    def _wait_for(self, target: str, capture_fn: Callable) -> Dict[str, Any]:
        """
        Poll until *target* appears or timeout.
        Uses the normalizer-aware MatchEngine for each poll cycle.
        """
        from vision.ocr_engine import OcrEngine
        ocr     = OcrEngine()
        start   = time.time()
        timeout = config.STEP_TIMEOUT_SEC

        while time.time() - start < timeout:
            frame   = capture_fn()
            results = ocr.extract(frame)
            match   = self._engine.match_target(target, results, frame, "wait_for")

            if match.found:
                log.info("wait_for '%s' satisfied (method=%s score=%.1f).",
                         target, match.method, match.score)
                return {"success": True, "screen_changed": True, "fuzzy_score": match.score,
                        "match_method": match.method}

            time.sleep(1.0)

        return {
            "success":    False,
            "error":      f"Timeout waiting for '{target}' after {timeout}s",
            "error_code": config.ERROR_CODES["ERR_TIMEOUT"],
        }

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _try_save_template(
        self,
        target: str,
        frame:  np.ndarray,
        match:  MatchResult,
    ) -> None:
        """
        If we have a bounding box from OCR, save a template crop
        so future runs have a visual fallback even if OCR degrades.
        """
        try:
            box = match.box
            if box is None or frame is None:
                return
            x1, y1, x2, y2 = box
            pad = 4
            x1  = max(0, x1 - pad)
            y1  = max(0, y1 - pad)
            x2  = min(frame.shape[1], x2 + pad)
            y2  = min(frame.shape[0], y2 + pad)
            crop = frame[y1:y2, x1:x2]
            if crop.size > 0:
                self._engine.save_template(target, crop)
        except Exception as exc:
            log.debug("Template auto-save failed: %s", exc)
