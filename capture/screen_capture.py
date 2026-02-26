from __future__ import annotations
import os
import cv2
import mss
import mss.tools
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import config
from utils.logger import get_logger

log = get_logger(__name__)

class ScreenCapture:
    """
    Handles screen capture and template matching with error handling
    and multi-monitor support.
    """
    def __init__(self):
        try:
            self.sct = mss.mss()
            self._validate_monitor()
        except Exception as e:
            log.error("Failed to initialize MSS: %s", e)
            raise

    def _validate_monitor(self):
        """Auto-detect valid monitors and fallback if configuration is invalid."""
        monitors = self.sct.monitors
        # index 0 is always the virtual screen (all monitors combined)
        # index 1 is usually the primary monitor
        valid_indices = list(range(1, len(monitors)))
        
        target = config.DEFAULT_MONITOR_INDEX
        if target not in valid_indices:
            log.warning("Invalid monitor index %d. Valid indices: %s. Falling back to PRIMARY (1).", 
                        target, valid_indices)
            self.monitor_index = 1 if 1 in valid_indices else 0
        else:
            self.monitor_index = target
            
        log.info("Screen Capture ready on monitor [%d]: %s", 
                 self.monitor_index, monitors[self.monitor_index])

    def capture(self, region: dict | None = None) -> np.ndarray:
        """
        Capture a region or full screen.
        If region is provided, it must be in logical coordinates.
        mss will handle Retina/High-DPI scaling automatically if monitor/region is correct.
        """
        try:
            # If region is provided, it overrides monitor index
            # region should be {"top": y, "left": x, "width": w, "height": h}
            monitor = self.sct.monitors[self.monitor_index] if not region else region
            
            screenshot = self.sct.grab(monitor)
            img = np.array(screenshot)
            # Convert BGRA to BGR for OpenCV
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        except Exception as e:
            log.error("Capture failed: %s", e)
            raise

    def locate_window(self, reference_path: str | Path) -> dict | None:
        """
        Multi-scale template matching to find reference image on current screen.
        Useful for finding windows that might be scaled or moved.
        """
        if not Path(reference_path).exists():
            log.error("Reference image not found: %s", reference_path)
            return None
            
        ref_img = cv2.imread(str(reference_path))
        if ref_img is None:
            log.error("Failed to load reference image: %s", reference_path)
            return None
            
        scene_img = self.capture()
        
        # Grayscale for matching speed and stability
        ref_gray = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
        scene_gray = cv2.cvtColor(scene_img, cv2.COLOR_BGR2GRAY)
        
        # Multi-scale matching (e.g., handles 100%, 125%, 150% scaling)
        scales = [1.0, 0.8, 1.2, 1.5, 2.0]
        best_match = None
        max_val = -1
        
        for scale in scales:
            try:
                resized_ref = cv2.resize(ref_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                if resized_ref.shape[0] > scene_gray.shape[0] or resized_ref.shape[1] > scene_gray.shape[1]:
                    continue
                    
                res = cv2.matchTemplate(scene_gray, resized_ref, cv2.TM_CCOEFF_NORMED)
                _, val, _, loc = cv2.minMaxLoc(res)
                
                if val > max_val:
                    max_val = val
                    best_match = {
                        "top": loc[1],
                        "left": loc[0],
                        "width": resized_ref.shape[1],
                        "height": resized_ref.shape[0],
                        "score": val,
                        "scale": scale
                    }
            except:
                continue
                
        # threshold (0.8 is usually good)
        if best_match and max_val > 0.8:
            log.info("Window located with score %.2f at scale %.1f.", max_val, best_match["scale"])
            return best_match
            
        log.debug("Window not found (max score: %.2f)", max_val)
        return None

    def capture_and_save(self, region: dict | None = None, filename: str = None) -> tuple[np.ndarray, Path]:
        img = self.capture(region)
        if not filename:
            filename = f"cap_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
            
        save_path = config.SCREENSHOTS_DIR / filename
        cv2.imwrite(str(save_path), img)
        return img, save_path

    def close(self):
        if hasattr(self, 'sct'):
            self.sct.close()
