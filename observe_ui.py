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
    
    # 3. Pre-process for better box detection (Sharpening & Thresholding)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Increase contrast
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    enhanced = clahe.apply(gray)
    # Sharpen
    kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
    sharpened = cv2.filter2D(enhanced, -1, kernel)
    # Conver back to BGR for the detector
    proc_img = cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)

    # 4. Scan for UI boxes inside that window
    print("Scanning for UI elements inside the window...")
    elements = detector.detect_contours(proc_img)
    
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

    # 5. Export Metadata and Save Map
    debug_path = Path("screenshots/window_observation_map.png")
    cv2.imwrite(str(debug_path), debug_img)
    
    json_path = Path("memory/ui_map.json")
    exported_data = {
        "timestamp": time.time(),
        "region": region,
        "elements": []
    }
    
    for i, elem in enumerate(elements):
        box = elem['box']
        w = box[2] - box[0]
        h = box[3] - box[1]
        
        if w < 20 or h < 10 or w > 1000:
            continue
            
        nx = elem['cx'] + region.get("left", 0) if region else elem['cx']
        ny = elem['cy'] + region.get("top", 0) if region else elem['cy']
        sx, sy = to_screen(nx, ny)
        
        exported_data["elements"].append({
            "id": i,
            "box": box,
            "center_native": [nx, ny],
            "center_screen": [sx, sy],
            "size": [w, h]
        })

    with open(json_path, "w") as f:
        json.dump(exported_data, f, indent=2)

    print(f"\n[SUCCESS] Map saved: {debug_path.absolute()}")
    print(f"[SUCCESS] JSON Metadata saved: {json_path.absolute()}")
    print(f"Total elements preserved: {len(exported_data['elements'])}")

if __name__ == "__main__":
    import time
    observe_window_ui()
