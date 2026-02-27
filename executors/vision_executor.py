import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import cv2
import numpy as np
import pyautogui

import config
from executors.base import BaseExecutor
from engine.ranking_engine import RankingEngine
from engine.memory_engine import MemoryEngine
from engine.state_engine import StateEngine
from vision.ocr_engine import OcrEngine
from vision.template_matcher import TemplateMatcher
from utils.logger import get_logger
from utils.image_utils import pixel_diff_ratio, save_image

log = get_logger("VisionExecutor")

class VisionExecutor(BaseExecutor):
    """
    Deterministic Citrix Vision Executor.
    Uses OCR, Ranking, Memory, and Screen State Hashing for robust automation.
    """

    def __init__(self, region: Optional[Dict[str, Any]] = None, context_id: str = "default"):
        self.region = region or {}
        self.context_id = context_id
        
        # Core Engines
        self.ocr = OcrEngine()
        self.ranking = RankingEngine()
        self.memory = MemoryEngine()
        self.state = StateEngine()
        self.template = TemplateMatcher()

    def execute(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Entry point for vision-based steps."""
        action = step.get("action", "").lower()
        target = step.get("target", "")
        value = step.get("value", "")
        
        # For simplicity in this POC, we use a global screen capture if no region is provided
        from capture.screen_capture import ScreenCapture
        capturer = ScreenCapture()
        
        def capture(): return capturer.capture(self.region)

        start_time = time.time()
        result = {"success": False, "retry_count": 0}
        
        try:
            if action == "click":
                result = self.click(target, capture_fn=capture)
            elif action == "type":
                result = self.type(target, value, capture_fn=capture)
            elif action == "verify":
                result = self.verify(target, capture_fn=capture)
            elif action == "pause":
                time.sleep(float(value or 1.0))
                result = {"success": True}
            elif action == "screenshot":
                img = capture()
                path = config.SCREENSHOTS_DIR / f"manual_{int(time.time())}.png"
                save_image(img, str(path))
                result = {"success": True, "path": str(path)}
                
        except Exception as e:
            log.exception(f"Vision execution error: {e}")
            result = {"success": False, "error": str(e)}

        result["duration"] = round(time.time() - start_time, 3)
        return result

    def click(self, target: str, capture_fn: Callable[[], np.ndarray]) -> Dict[str, Any]:
        log.info(f"Vision Click Resolution: '{target}'")
        
        frame = capture_fn()
        screen_hash = self.state.compute_screen_hash(frame)
        
        # 1. Self-Healing check: Try Memory first
        memory_entry = self.memory.get_entry(screen_hash, target)
        if memory_entry and self.memory.get_historical_score(screen_hash, target) > 0.8:
            nx, ny = memory_entry["coordinates"]
            # Convert native to screen for pyautogui
            from utils.coords import to_screen
            sx, sy = to_screen(nx, ny)
            log.info(f"Memory Hit! Trying native({nx}, {ny}) -> screen({sx}, {sy})")
            if self._perform_and_validate(sx, sy, capture_fn):
                self.memory.record_success(screen_hash, target, (nx, ny))
                return {"success": True, "method": "memory", "coords": (nx, ny)}
            else:
                log.warning("Memory click failed validation. Falling back to fresh detection.")
                self.memory.record_failure(screen_hash, target)

        # 2. Fresh Detection + Ranking
        ocr_results = self.ocr.extract(frame)
        memory_stats = {} 
        
        ranked = self.ranking.rank_candidates(target, ocr_results, memory_stats)
        
        if not ranked or ranked[0]["ranking_details"]["final"] < 0.6:
            # Try Template matching as fallback
            log.info("OCR Ranking too low. Falling back to template matching.")
            tpl_match = self.template.find(target, frame, self.region, context_id=self.context_id)
            if tpl_match:
                nx, ny = tpl_match
                from utils.coords import to_screen
                sx, sy = to_screen(nx, ny)
                if self._perform_and_validate(sx, sy, capture_fn):
                    return {"success": True, "method": "template", "coords": (nx, ny)}
            
            return {"success": False, "error": f"Target '{target}' not found with high confidence."}

        # Select best candidate
        best = ranked[0]
        box = best["box"]
        # Central point in NATIVE pixels (screenshot space)
        nx = (box[0] + box[2]) // 2 + self.region.get("left", 0)
        ny = (box[1] + box[3]) // 2 + self.region.get("top", 0)
        
        # Transform to SCREEN pixels for pyautogui
        from utils.coords import to_screen
        sx, sy = to_screen(nx, ny)

        if self._perform_and_validate(sx, sy, capture_fn):
            self.memory.record_success(screen_hash, target, (nx, ny))
            return {
                "success": True, 
                "method": "ocr", 
                "coords": (nx, ny),
                "ranking": best["ranking_details"]
            }
        
        return {"success": False, "error": "Click failed stabilization/validation."}

    def type(self, target: str, value: str, capture_fn: Callable[[], np.ndarray]) -> Dict[str, Any]:
        res = self.click(target, capture_fn)
        if not res["success"]:
            return res
        
        time.sleep(0.3) # Wait for focus
        modifier = "command" if sys.platform == "darwin" else "ctrl"
        pyautogui.hotkey(modifier, "a")
        pyautogui.press("backspace")
        pyautogui.typewrite(value, interval=0.03)
        return {"success": True, "method": res["method"], "coords": res.get("coords")}

    def verify(self, target: str, capture_fn: Callable[[], np.ndarray]) -> Dict[str, Any]:
        frame = capture_fn()
        ocr_results = self.ocr.extract(frame)
        ranked = self.ranking.rank_candidates(target, ocr_results)
        if ranked and ranked[0]["ranking_details"]["final"] > 0.7:
            return {"success": True, "score": ranked[0]["ranking_details"]["final"]}
        return {"success": False}

    def _perform_and_validate(self, cx: int, cy: int, capture_fn: Callable) -> bool:
        """Execute click and check for screen change."""
        before = capture_fn()
        pyautogui.click(cx, cy)
        time.sleep(config.STEP_DELAY_SEC)
        after = capture_fn()
        
        diff = self.state.get_pixel_diff(before, after)
        log.debug(f"Action validation: diff={diff:.4f}")
        return diff >= config.PIXEL_DIFF_THRESHOLD
