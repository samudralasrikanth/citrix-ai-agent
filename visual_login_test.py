import time
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
    
    def find_and_interact(template_name, action="click", value=None, offset_x=0):
        template_path = Path(f"screenshots/{template_name}.png")
        if not template_path.exists():
            print(f"Error: {template_path} not found! Please crop this label/button first.")
            return False
            
        tpl = cv2.imread(str(template_path), 0)
        res = cv2.matchTemplate(screen_gray, tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        
        if max_val > 0.8:
            h, w = tpl.shape
            # Calculate coordinates
            nx = max_loc[0] + (w // 2) + offset_x
            ny = max_loc[1] + (h // 2)
            
            sx, sy = to_screen(nx, ny)
            print(f"Found {template_name}! Performing {action} at ({sx}, {sy})")
            
            pyautogui.moveTo(sx, sy, duration=0.5)
            pyautogui.click()
            
            if action == "type" and value:
                time.sleep(0.3)
                # Clear and Type
                pyautogui.hotkey('ctrl', 'a') if os.name == 'nt' else pyautogui.hotkey('command', 'a')
                pyautogui.press('backspace')
                pyautogui.write(value, interval=0.05)
                pyautogui.press('tab') # Move to next field
            return True
        else:
            print(f"Target '{template_name}' not found (Score: {max_val:.2f})")
            return False

    # --- EXECUTION SEQUENCE ---
    
    # 1. Find "Operator ID" label and click the box to its right (+150 px)
    if find_and_interact("operator_label", action="type", value=operator_id, offset_x=150):
        time.sleep(0.5)
        
        # 2. Find "Password" label and click the box to its right (+150 px)
        if find_and_interact("password_label", action="type", value=password, offset_x=150):
            time.sleep(0.5)
            
            # 3. Click the "OK" button
            find_and_interact("ok_btn", action="click")

if __name__ == "__main__":
    # You can pass your credentials here:
    visual_login(operator_id="ADMIN_USER", password="SAFE_PASSWORD_123")
