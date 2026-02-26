"""
Hardened Action Executor for Production Citrix Automation.
==========================================================
Includes:
- Robust error classification
- Visual debug logging (bounding boxes)
- Failure reason categorization
- PyAutoGUI safety checks
"""
from __future__ import annotations
import time
import cv2
import pyautogui
from typing import Any, Dict, List, Tuple, Callable

import config
from utils.image_utils import pixel_diff_ratio, draw_elements, save_image
from utils.logger import get_logger
from vision.similarity import best_match

log = get_logger(__name__)

# Basic safety
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.2

class ActionExecutor:
    """
    Executes automation actions against the live OS with high observability.
    """
    def __init__(self):
        self._last_match_score = 0.0

    def execute(
        self,
        action: Dict[str, Any],
        elements: List[Dict],
        capture_fn: Callable[[], Any]
    ) -> Dict[str, Any]:
        """
        Main entry point for action execution.
        """
        atype = action.get("action", "").lower()
        target = action.get("target_text", "")
        value = action.get("value", "")
        
        result = {
            "success": False,
            "error": None,
            "error_code": 0,
            "target_center": None,
            "fuzzy_score": 0.0,
            "screen_changed": False
        }

        try:
            # 1. State preservation (for change detection)
            before_frame = capture_fn()
            
            # 2. Logic execution
            if atype == "click":
                match_res = self._click(target, elements)
                result.update(match_res)
            elif atype == "type":
                match_res = self._type(target, value, elements)
                result.update(match_res)
            elif atype == "wait_for":
                wait_res = self._wait_for(target, capture_fn)
                return wait_res
            elif atype == "screenshot":
                result["success"] = True
                return result
            else:
                result["error"] = f"Unsupported action: {atype}"
                return result

            # If element wasn't found, we already have success=False in result
            if not result["success"]:
                return result

            # 3. Post-execution validation
            time.sleep(config.STEP_DELAY_SEC)
            after_frame = capture_fn()
            
            diff = pixel_diff_ratio(before_frame, after_frame)
            result["screen_changed"] = diff >= config.PIXEL_DIFF_THRESHOLD
            
            # In Citrix, sometimes a click doesn't change anything (no-op)
            # but we still mark it as successful logic-wise if we found the button.
            # However, for robustness we check for no-change as a warning/failure code.
            if not result["screen_changed"]:
                result["error_code"] = config.ERROR_CODES["ERR_NO_CHANGE"]
                log.warning("Action performed but no screen change detected (diff=%.4f)", diff)
            
            # 4. Debugging Save
            if config.SAVE_DEBUG_FRAMES:
                self._save_debug_view(before_frame, elements, result.get("matched_idx"), atype)

            return result

        except Exception as e:
            log.exception("Critical automation failure: %s", e)
            result["success"] = False
            result["error"] = str(e)
            result["error_code"] = 500
            return result

    def _click(self, target: str, elements: List[Dict]) -> Dict:
        idx, score = self._resolve(target, elements)
        if idx < 0:
            return {"success": False, "error": f"Element '{target}' not found", "error_code": config.ERROR_CODES["ERR_MATCH_FAIL"]}
            
        elem = elements[idx]
        cx, cy = elem["cx"], elem["cy"]
        log.info("Clicking '%s' (score=%.1f) at [%d, %d]", target, score, cx, cy)
        
        try:
            pyautogui.click(cx, cy)
            return {"success": True, "target_center": (cx, cy), "fuzzy_score": score, "matched_idx": idx}
        except Exception as e:
            return {"success": False, "error": f"OS Permission Error: {e}", "error_code": config.ERROR_CODES["ERR_PERM"]}

    def _type(self, target: str, value: str, elements: List[Dict]) -> Dict:
        res = self._click(target, elements)
        if not res["success"]:
            return res
            
        time.sleep(0.3)
        # Standard Citrix interaction: Clear field before typing
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.press('backspace')
        pyautogui.typewrite(value, interval=0.03)
        pyautogui.press('enter')
        return res

    def _wait_for(self, target: str, capture_fn: Callable) -> Dict:
        from vision.ocr_engine import OcrEngine
        ocr = OcrEngine()
        
        start = time.time()
        timeout = config.STEP_TIMEOUT_SEC
        
        while time.time() - start < timeout:
            frame = capture_fn()
            results = ocr.extract(frame)
            texts = [r["text"] for r in results]
            match = best_match(target, texts)
            
            if match and match[1] >= config.FUZZY_MATCH_THRESHOLD:
                log.info("Wait success: '%s' appeared on screen.", target)
                return {"success": True, "screen_changed": True, "fuzzy_score": match[1]}
            
            time.sleep(1.0) # Poll every 1s
            
        return {
            "success": False, 
            "error": f"Timeout waiting for '{target}' after {timeout}s", 
            "error_code": config.ERROR_CODES["ERR_TIMEOUT"]
        }

    def _resolve(self, target: str, elements: List[Dict]) -> Tuple[int, float]:
        """Find index of best fuzzy-matching element."""
        if not elements:
            return -1, 0.0
            
        labels = [e.get("label", "") for e in elements]
        match = best_match(target, labels)
        
        if not match or match[1] < config.FUZZY_MATCH_THRESHOLD:
            log.warning("No fuzzy match for '%s'. Best was '%s' (%.1f)", 
                        target, match[0] if match else "None", match[1] if match else 0)
            return -1, 0.0
            
        best_label, score = match
        for i, e in enumerate(elements):
            if e.get("label") == best_label:
                return i, score
                
        return -1, 0.0

    def _save_debug_view(self, frame: Any, elements: List[Dict], matched_idx: int, action_name: str):
        """Visual verification - draws boxes and saves to disk."""
        try:
            debug_img = draw_elements(frame, elements, highlight_idx=matched_idx)
            fname = f"debug_{action_name}_{int(time.time())}.png"
            save_image(debug_img, str(config.SCREENSHOTS_DIR / fname))
        except:
            pass
