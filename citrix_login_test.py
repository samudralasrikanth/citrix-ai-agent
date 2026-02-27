import time
import sys
import os
import json
import pyautogui
from pathlib import Path

# Add project root to path for imports
sys.path.append(os.getcwd())

import config
from capture.screen_capture import ScreenCapture
from vision.ocr_engine import OcrEngine
from utils.coords import to_screen
from utils.logger import get_logger

log = get_logger("CitrixLoginTest")

def citrix_login_flow(operator_id="test_user", password="test_password"):
    """
    Automates the Citrix Login flow:
    1. Finds 'Operator ID' box -> types ID
    2. Finds 'Password' box -> types password
    3. Finds 'OK' button -> clicks it
    """
    log.info("Starting Citrix Login automation...")
    
    capturer = ScreenCapture()
    ocr = OcrEngine()
    
    # 1. Capture and Find Elements
    # We use the region if saved in memory/region.json
    region_path = Path("memory/region.json")
    region = None
    if region_path.exists():
        with open(region_path, "r") as f:
            region = json.load(f).get("region")
            log.info(f"Using saved region: {region}")

    frame = capturer.capture(region)
    results = ocr.extract(frame)
    
    def find_and_interact(label_text, action="click", value=None):
        target = label_text.lower()
        # Find the label on screen
        match = next((res for res in results if target in res["text"].lower()), None)
        
        if not match:
            log.warning(f"Could not find label: '{label_text}'")
            return False
            
        box = match["box"]
        # For 'Operator ID' or 'Password', the input box is usually to the RIGHT of the text
        # So we offset the click to the right of the bounding box
        if action == "type":
            # Click roughly 150 pixels to the right of the label's center to hit the input field
            nx = box[2] + 100 + region.get("left", 0) if region else box[2] + 100
        else:
            # For buttons, click the center
            nx = (box[0] + box[2]) // 2 + region.get("left", 0) if region else (box[0] + box[2]) // 2
            
        ny = (box[1] + box[3]) // 2 + region.get("top", 0) if region else (box[1] + box[3]) // 2
        
        sx, sy = to_screen(nx, ny)
        
        log.info(f"Action '{action}' on '{label_text}' at ({sx}, {sy})")
        pyautogui.moveTo(sx, sy, duration=0.5)
        pyautogui.click()
        
        if action == "type" and value:
            time.sleep(0.5)
            # Clear existing text
            pyautogui.hotkey('ctrl', 'a') if os.name == 'nt' else pyautogui.hotkey('command', 'a')
            pyautogui.press('backspace')
            # Type new value
            pyautogui.write(value, interval=0.1)
            pyautogui.press('enter')
            
        return True

    # EXECUTION SEQUENCE
    # 1. Enter Operator ID
    find_and_interact("Operator ID", action="type", value=operator_id)
    time.sleep(1)
    
    # 2. Enter Password
    find_and_interact("Password", action="type", value=password)
    time.sleep(1)
    
    # 3. Click OK
    log.info("Clicking the OK button...")
    find_and_interact("OK", action="click")

if __name__ == "__main__":
    # Update your actual credentials here for testing manually
    # Or keep them as placeholders to verify the mouse movement first
    citrix_login_flow(operator_id="MY_ADMIN", password="MY_PASSWORD_123")
