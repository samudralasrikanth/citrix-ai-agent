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
            print(f"  [ERROR] File missing: {template_path}")
            return False
            
        tpl = cv2.imread(str(template_path), 0)
        th, tw = tpl.shape
        res = cv2.matchTemplate(screen_gray, tpl, cv2.TM_CCOEFF_NORMED)
        
        # 1. Find all potential candidates
        threshold = 0.7 # Slightly lower threshold for 'observation'
        locs = np.where(res >= threshold)
        all_candidates = []
        for pt in zip(*locs[::-1]): 
            score = res[pt[1], pt[0]]
            if not any(abs(pt[0]-m[0]) < 20 and abs(pt[1]-m[1]) < 20 for m in all_candidates):
                all_candidates.append((pt[0], pt[1], score))
        
        # Sort by vertical position
        all_candidates.sort(key=lambda c: c[1])
        
        print(f"\n--- Observation Report for '{template_name}' ---")
        print(f"  Found {len(all_candidates)} candidates on screen:")
        for i, (x, y, score) in enumerate(all_candidates):
            mark = "[TARGET]" if i == match_index else "        "
            print(f"  {mark} Index {i}: Pos({x}, {y}) Confidence: {score:.4f}")
        
        # Save a debug image so user can see what the script sees
        debug_img = screen.copy()
        for i, (x, y, score) in enumerate(all_candidates):
            color = (0, 255, 0) if i == match_index else (0, 165, 255)
            cv2.rectangle(debug_img, (x, y), (x + tw, y + th), color, 2)
            cv2.putText(debug_img, f"Idx:{i}", (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        
        debug_out = Path("screenshots/debug_view.png")
        cv2.imwrite(str(debug_out), debug_img)
        print(f"  [DEBUG] See what I observed here: {debug_out.absolute()}")

        if len(all_candidates) > match_index:
            x, y, score = all_candidates[match_index]
            # Calculate coordinates
            nx = x + (tw // 2) + offset_x
            ny = y + (th // 2)
            
            sx, sy = to_screen(nx, ny)
            print(f"  [ACTION] Moving to Index {match_index} at screen coords ({sx}, {sy})")
            
            pyautogui.moveTo(sx, sy, duration=0.6)
            pyautogui.click()
            time.sleep(0.4) # Wait for focus
            
            if action == "type" and value:
                print(f"  [ACTION] Typing value...")
                # Triple click to ensure field is cleared
                pyautogui.click(clicks=3, interval=0.1)
                pyautogui.press('backspace')
                pyautogui.write(value, interval=0.08)
            return True
        else:
            print(f"  [FAILED] Target index {match_index} not available.")
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
