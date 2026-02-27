import time
import sys
import os
import json
import pyautogui
import numpy as np
from pathlib import Path

# Add project root to path for imports
sys.path.append(os.getcwd())

import config
from capture.screen_capture import ScreenCapture
from vision.ocr_engine import OcrEngine
from utils.coords import to_screen
from utils.logger import get_logger

log = get_logger("SampleClickTest")

def load_default_region():
    """Attempts to load the last setup region from memory/region.json"""
    region_path = Path("memory/region.json")
    if region_path.exists():
        try:
            with open(region_path, "r") as f:
                data = json.load(f)
                return data.get("region")
        except Exception as e:
            log.warning(f"Failed to load region.json: {e}")
    return None

def sample_click_by_text(targets=["ok", "cancel"], region=None):
    """
    Finds and clicks buttons based on text labels within a specific region.
    
    Args:
        targets: List of text labels to find.
        region: Optional dict {"top": y, "left": x, "width": w, "height": h}
    """
    # 1. Resolve Region (Manual > memory/region.json > Full Desktop)
    if not region:
        region = load_default_region()
    
    if region:
        log.info(f"Using frame: {region}")
    else:
        log.info("No region defined, using full desktop.")
        region = {} # Default for offset math

    # 2. Initialize engines
    capturer = ScreenCapture()
    ocr = OcrEngine()
    
    # 3. Capture & Process
    log.info("Capturing frame...")
    frame = capturer.capture(region if region else None)
    
    log.info("Running OCR extraction...")
    results = ocr.extract(frame)
    
    # 4. Search for targets
    found_targets = []
    for target in targets:
        target_lower = target.lower()
        # Find best match (exact or substring)
        matches = [r for r in results if target_lower in r["text"].lower()]
        if matches:
            # Pick the one with highest confidence or first found
            best_match = max(matches, key=lambda x: x.get("confidence", 0))
            log.info(f"MATCH FOUND: '{target}' -> '{best_match['text']}' at {best_match['box']}")
            found_targets.append((target, best_match))
        else:
            log.warning(f"Target '{target}' NOT found in the frame.")

    # 5. Execute Moves
    for name, match in found_targets:
        box = match["box"]
        # Center of the match relative to the CROP
        cx_crop = (box[0] + box[2]) // 2
        cy_crop = (box[1] + box[3]) // 2

        # Translate to Screen coordinates
        # 1. Native Relative -> Native Absolute (Add region top/left)
        nx = cx_crop + region.get("left", 0)
        ny = cy_crop + region.get("top", 0)
        
        # 2. Native Absolute -> Logical Screen (Adjust for Retina/DPI)
        sx, sy = to_screen(nx, ny)
        
        log.info(f"Moving to '{name}' at ({sx}, {sy})")
        
        # Move first to visualize accuracy
        pyautogui.moveTo(sx, sy, duration=0.8)
        # pyautogui.click(sx, sy) # Uncomment to actually click
        
        log.info(f"Hover simulation for '{name}' completed.")
        time.sleep(1.5)

if __name__ == "__main__":
    # To define a custom frame manually, uncomment and edit here:
    # CUSTOM_FRAME = {"top": 100, "left": 100, "width": 800, "height": 600}
    CUSTOM_FRAME = None 

    test_targets = ["ok", "cancel", "accept", "reject"]
    sample_click_by_text(test_targets, region=CUSTOM_FRAME)
