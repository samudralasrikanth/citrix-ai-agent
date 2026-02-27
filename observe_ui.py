import cv2
import numpy as np
from capture.screen_capture import ScreenCapture
from vision.element_detector import ElementDetector
from utils.coords import to_screen
import json
from pathlib import Path

def load_region():
    region_path = Path("memory/region.json")
    if region_path.exists():
        with open(region_path, "r") as f:
            return json.load(f).get("region")
    return None

def observe_window_ui():
    print("\n--- Starting Window UI Observation ---")
    capturer = ScreenCapture()
    detector = ElementDetector()
    
    # 1. Load your specific window frame
    region = load_region()
    if region:
        print(f"Targeting defined frame: {region}")
    else:
        print("No region.json found. Using full screen. (Run setup_region.py first)")

    # 2. Capture the specific window
    img = capturer.capture(region)
    
    # 3. Scan for UI boxes inside that window
    print("Scanning for UI elements inside the window...")
    elements = detector.detect_contours(img)
    
    # Sort top-to-bottom
    elements.sort(key=lambda e: (e['box'][1], e['box'][0]))
    
    debug_img = img.copy()
    
    print(f"\nDiscovered {len(elements)} possible elements in window:")
    
    for i, elem in enumerate(elements):
        box = elem['box']
        w = box[2] - box[0]
        h = box[3] - box[1]
        
        if w < 20 or h < 10 or w > 1000:
            continue
            
        # Add the Window Offset back to the relative box coordinates
        nx = elem['cx'] + region.get("left", 0) if region else elem['cx']
        ny = elem['cy'] + region.get("top", 0) if region else elem['cy']
        
        # Convert to Screen pixels
        sx, sy = to_screen(nx, ny)
        
        print(f"  [{i}] Element at Window Relative({elem['cx']}, {elem['cy']}) -> Screen({sx}, {sy})")
        
        cv2.rectangle(debug_img, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
        cv2.putText(debug_img, str(i), (box[0], box[1]-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    debug_path = Path("screenshots/window_observation_map.png")
    cv2.imwrite(str(debug_path), debug_img)
    print(f"\n[SUCCESS] Map saved: {debug_path.absolute()}")

if __name__ == "__main__":
    observe_window_ui()
