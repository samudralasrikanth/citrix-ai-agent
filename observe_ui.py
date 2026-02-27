import cv2
import numpy as np
from capture.screen_capture import ScreenCapture
from vision.element_detector import ElementDetector
from utils.coords import to_screen
import json
from pathlib import Path

def observe_whole_ui():
    print("\n--- Starting Deep UI Observation ---")
    capturer = ScreenCapture()
    detector = ElementDetector()
    
    # 1. Capture the screen
    img = capturer.capture()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 2. Find all Rectangular Elements (Buttons, Text boxes)
    print("Scanning for UI elements (boxes, buttons, fields)...")
    elements = detector.detect_contours(img)
    
    # Sort elements by position (top-to-bottom, then left-to-right)
    elements.sort(key=lambda e: (e['box'][1], e['box'][0]))
    
    print(f"\nDiscovered {len(elements)} possible UI elements:")
    
    debug_img = img.copy()
    
    discovered_report = []
    for i, elem in enumerate(elements):
        box = elem['box']
        # x1, y1, x2, y2
        w = box[2] - box[0]
        h = box[3] - box[1]
        
        # Filter out tiny noise or huge backgrounds
        if w < 20 or h < 10 or w > 1000:
            continue
            
        # Get screen coordinates for your actual monitor
        sx, sy = to_screen(elem['cx'], elem['cy'])
        
        item = {
            "id": i,
            "type": "button/field",
            "screen_pos": [sx, sy],
            "size": [w, h]
        }
        discovered_report.append(item)
        
        print(f"  [{i}] Element found at Screen({sx}, {sy}) | Size: {w}x{h}")
        
        # Draw on debug image
        cv2.rectangle(debug_img, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
        cv2.putText(debug_img, str(i), (box[0], box[1]-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    # 3. Save the vision map
    debug_path = Path("screenshots/ui_observation_map.png")
    cv2.imwrite(str(debug_path), debug_img)
    
    print(f"\n[SUCCESS] UI Analysis complete.")
    print(f"I have saved a 'Map' of everything I saw here: {debug_path.absolute()}")
    print("You can use the 'Index' numbers from this map to click anything accurately.")

if __name__ == "__main__":
    observe_whole_ui()
