import time
import cv2
import pyautogui
import numpy as np
from pathlib import Path
import config
from capture.screen_capture import ScreenCapture
from utils.coords import to_screen

def visual_login(operator_id="admin", password="password"):
    print("Starting Visual Login (Template Matching)...")
    capturer = ScreenCapture()
    
    # 1. Capture screen
    screen = capturer.capture()
    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    
    def find_and_click(template_name, offset_x=0):
        template_path = Path(f"screenshots/{template_name}.png")
        if not template_path.exists():
            print(f"Error: {template_path} not found! Run capture_templates.py first.")
            return False
            
        tpl = cv2.imread(str(template_path), 0)
        res = cv2.matchTemplate(screen_gray, tpl, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        if max_val > 0.8: # Confidence threshold
            # Center of the match
            h, w = tpl.shape
            nx = max_loc[0] + (w // 2) + offset_x
            ny = max_loc[1] + (h // 2)
            
            sx, sy = to_screen(nx, ny)
            print(f"Found {template_name}! Clicking at ({sx}, {sy})")
            pyautogui.moveTo(sx, sy, duration=0.5)
            pyautogui.click()
            return True
        else:
            print(f"Match failed for {template_name} (Score: {max_val:.2f})")
            return False

    # SEQUENCE:
    # 1. Click Operator ID field (Lookup the label 'Operator ID' and click to the right)
    # Note: You would need a 'label_operator.png' or just manually click the first box
    print("Please make sure you have 'ok_btn.png' in the screenshots folder.")
    find_and_click("ok_btn")

if __name__ == "__main__":
    visual_login()
