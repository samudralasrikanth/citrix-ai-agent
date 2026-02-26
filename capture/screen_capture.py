from __future__ import annotations
import os
import cv2
import mss
import mss.tools
import numpy as np
from datetime import datetime
from pathlib import Path

class ScreenCapture:
    def __init__(self):
        self.sct = mss.mss()

    def capture(self, region: dict | None = None) -> np.ndarray:
        """Capture a region or full screen."""
        # Note: on macOS Retina, mss returns pixels at 2x scale 
        # but the region coords are in logical points.
        monitor = self.sct.monitors[0] if not region else region
        
        screenshot = self.sct.grab(monitor)
        img = np.array(screenshot)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def locate_window(self, reference_path: str | Path) -> dict | None:
        """
        Robustly find where the window is currently located on the screen.
        Handles scaling differences (Retina vs Standard) by trying multiple scales.
        """
        if not os.path.exists(reference_path):
            return None

        # 1. Take a full screenshot
        full_screen = self.capture()
        template = cv2.imread(str(reference_path))
        
        if template is None or full_screen is None:
            return None

        # Convert both to grayscale for faster/easier matching
        full_gray = cv2.cvtColor(full_screen, cv2.COLOR_BGR2GRAY)
        temp_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        best_match = None
        best_score = 0.75 # Minimum confidence threshold

        # 2. Try matching at multiple scales (especially 0.5 for Retina downscaling)
        # MacOS Retina: full_screen might be 2x what was intended by 'logical' region coords
        scales = [1.0, 0.5, 0.75, 1.25, 1.5, 2.0]
        
        for scale in scales:
            sw = int(temp_gray.shape[1] * scale)
            sh = int(temp_gray.shape[0] * scale)
            
            # Skip if template is bigger than screen
            if sw > full_gray.shape[1] or sh > full_gray.shape[0] or sw < 10 or sh < 10:
                continue
                
            resized = cv2.resize(temp_gray, (sw, sh), interpolation=cv2.INTER_AREA)
            
            res = cv2.matchTemplate(full_gray, resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)

            if max_val > best_score:
                best_score = max_val
                best_match = {
                    "left": max_loc[0],
                    "top": max_loc[1],
                    "width": sw,
                    "height": sh,
                    "score": max_val
                }
                # If we have a very high confidence, stop early
                if max_val > 0.95:
                    break

        return best_match

    def capture_and_save(self, region: dict | None = None, folder: str | Path = "screenshots") -> tuple[np.ndarray, str]:
        """Captures and saves a timestamped image."""
        img = self.capture(region)
        
        Path(folder).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = os.path.join(folder, f"capture_{timestamp}.png")
        
        cv2.imwrite(path, img)
        return img, path

    def close(self):
        self.sct.close()
