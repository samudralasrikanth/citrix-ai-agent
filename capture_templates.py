import cv2
import pyautogui
import numpy as np
from capture.screen_capture import ScreenCapture
from pathlib import Path

def capture_button_templates():
    """
    Instructions:
    1. Make sure your Citrix window is visible.
    2. Run this script.
    3. It will take a full-screen screenshot and save it.
    4. You will then need to manually crop the 'OK' and 'Cancel' buttons.
    """
    print("\n--- Citrix Template Creator ---")
    print("Capturing screen... Please wait 3 seconds.")
    import time
    time.sleep(3)
    
    capturer = ScreenCapture()
    img = capturer.capture()
    
    # Save the full image so you can crop it
    debug_path = Path("screenshots/full_screen_for_cropping.png")
    cv2.imwrite(str(debug_path), img)
    
    print(f"\n1. Open this image: {debug_path.absolute()}")
    print("2. Crop the 'OK' button and save it as 'screenshots/ok_btn.png'")
    print("3. Crop the 'Cancel' button and save it as 'screenshots/cancel_btn.png'")
    print("\nOnce you have these two files, we can run the Login script without OCR errors!")

if __name__ == "__main__":
    capture_button_templates()
