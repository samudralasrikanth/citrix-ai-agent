import time
import os
import cv2
import pyautogui
import numpy as np
from pathlib import Path
import config
from capture.screen_capture import ScreenCapture
from utils.coords import to_screen

def visual_login(operator_id="MY_USER", password="MY_PASSWORD"):
    print(f"Starting Visual Login for User: {operator_id}...")
    capturer = ScreenCapture()
    
    # 1. Capture screen
    screen = capturer.capture()
    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    
    def find_and_interact(template_name, action="click", value=None, offset_x=0, match_index=0):
        template_path = Path(f"screenshots/{template_name}.png")
        if not template_path.exists():
            print(f"Error: {template_path} not found!")
            return False
            
        tpl = cv2.imread(str(template_path), 0)
        res = cv2.matchTemplate(screen_gray, tpl, cv2.TM_CCOEFF_NORMED)
        
        # Find all matches above 80% confidence
        threshold = 0.8
        locs = np.where(res >= threshold)
        matches = []
        for pt in zip(*locs[::-1]): # (x, y) coordinates
            # Check if this match is too close to an existing one (clumping)
            if not any(abs(pt[0]-m[0]) < 10 and abs(pt[1]-m[1]) < 10 for m in matches):
                matches.append(pt)
        
        # Sort matches by Y-coordinate (top to bottom)
        matches.sort(key=lambda p: p[1])
        
        if len(matches) > match_index:
            target_loc = matches[match_index]
            h, w = tpl.shape
            # Calculate coordinates
            nx = target_loc[0] + (w // 2) + offset_x
            ny = target_loc[1] + (h // 2)
            
            sx, sy = to_screen(nx, ny)
            print(f"Target '{template_name}' [index {match_index}] found at ({sx}, {sy})")
            
            pyautogui.moveTo(sx, sy, duration=0.5)
            pyautogui.click()
            
            if action == "type" and value:
                time.sleep(0.3)
                pyautogui.hotkey('ctrl', 'a') if os.name == 'nt' else pyautogui.hotkey('command', 'a')
                pyautogui.press('backspace')
                pyautogui.write(value, interval=0.05)
            return True
        else:
            print(f"Could not find match index {match_index} for '{template_name}'. Found {len(matches)} total.")
            return False

    # --- EXECUTION SEQUENCE ---
    # We can now use a single template (e.g. 'label.png') and pick them by order
    # Index 0 = First field (User), Index 1 = Second field (Password) 
    
    # Target 0 (Operator ID)
    if find_and_interact("label", action="type", value=operator_id, offset_x=150, match_index=0):
        time.sleep(0.5)
        # Target 1 (Password)
        find_and_interact("label", action="type", value=password, offset_x=150, match_index=1)
        time.sleep(0.5)
        # Final OK button
        find_and_interact("ok_btn", action="click")

if __name__ == "__main__":
    # pass MY_USER and MY_PASSWORD
    visual_login(operator_id="ADMIN_USER", password="SAFE_PASSWORD_123")
