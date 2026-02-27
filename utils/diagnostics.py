"""
Universal Diagnostic Utility — Citrix AI Vision Agent
=====================================================
Performs a 4-stage health check to find root causes of cross-platform failures:
1.  Dependencies: Can we load CV2, Paddle, PyAutoGUI?
2.  Screen Capture: Can mss capture the screen? (Mac permissions)
3.  Coordinate Scaling: Detect Windows DPI / Mac Retina factors.
4.  OCR Pass: Can the engine run a simple 'Hello World' match?
"""
import sys
import os
import time
import json
import platform
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))

import numpy as np
import cv2
import mss
import pyautogui

import config
from capture.screen_capture import ScreenCapture
from vision.ocr_engine import OcrEngine

def run_diagnostics():
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "os": f"{platform.system()} {platform.release()}",
        "python": sys.version,
        "results": {},
        "errors": []
    }

    print("\n🚀 Starting Citrix AI Agent Universal Diagnostics...")
    print("--------------------------------------------------")

    # --- 1. Dependencies ---
    print("[1/4] Checking Dependencies...", end=" ", flush=True)
    try:
        import PIL
        import pydantic
        import yaml
        report["results"]["dependencies"] = "PASS"
        print("✅")
    except Exception as e:
        report["results"]["dependencies"] = "FAIL"
        report["errors"].append(f"Missing dependency: {str(e)}")
        print("❌")

    # --- 2. Screen Capture & Permissions ---
    print("[2/4] Verifying Screen Capture...", end=" ", flush=True)
    try:
        cap = ScreenCapture()
        frame = cap.capture()
        cap.close()
        
        # Check if frame is all black (common Mac permission issue)
        if np.mean(frame) < 0.1:
            report["results"]["capture"] = "FAIL (Black Screen)"
            report["errors"].append("Screen capture returned black image. Check macOS Screen Recording permissions.")
            print("❌ (Black Screen)")
        else:
            report["results"]["capture"] = "PASS"
            # Save debug capture
            diag_path = ROOT / "logs" / "diag_capture.png"
            cv2.imwrite(str(diag_path), frame)
            report["results"]["capture_path"] = str(diag_path)
            print("✅")
    except Exception as e:
        report["results"]["capture"] = "FAIL"
        report["errors"].append(f"Capture error: {str(e)}")
        print("❌")

    # --- 3. Coordinate Scaling & DPI ---
    print("[3/4] Analyzing Coordinate Scaling...", end=" ", flush=True)
    try:
        screen_size = pyautogui.size()
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            mss_size = (monitor["width"], monitor["height"])
        
        scaling_x = mss_size[0] / screen_size[0]
        scaling_y = mss_size[1] / screen_size[1]
        
        report["results"]["pyautogui_size"] = f"{screen_size[0]}x{screen_size[1]}"
        report["results"]["mss_size"] = f"{mss_size[0]}x{mss_size[1]}"
        report["results"]["scaling_factor"] = (scaling_x, scaling_y)
        
        if abs(scaling_x - 1.0) > 0.05 or abs(scaling_y - 1.0) > 0.05:
            print(f"⚠️  (Scaling: {scaling_x:.2f}x)")
            report["results"]["scaling_status"] = "ACTIVE"
        else:
            print("✅ (1.0x)")
            report["results"]["scaling_status"] = "NORMAL"
    except Exception as e:
        report["results"]["scaling_status"] = "ERROR"
        report["errors"].append(f"Scaling check failed: {str(e)}")
        print("❌")

    # --- 4. OCR Engine Health ---
    print("[4/4] Testing OCR Engine (might take 10s)...", end=" ", flush=True)
    try:
        start_ocr = time.time()
        ocr = OcrEngine()
        
        # Create a test image with text
        test_img = np.zeros((100, 300, 3), dtype=np.uint8) + 255
        cv2.putText(test_img, "DIAGNOSTIC", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,0), 2)
        
        results = ocr.extract(test_img)
        ocr_time = time.time() - start_ocr
        
        found = any("DIAGNOSTIC" in r["text"].upper() for r in results)
        if found:
            report["results"]["ocr"] = "PASS"
            report["results"]["ocr_time"] = round(ocr_time, 2)
            print(f"✅ ({round(ocr_time, 1)}s)")
        else:
            report["results"]["ocr"] = "FAIL (No Text Found)"
            report["errors"].append("OCR engine loaded but failed to detect text in test image.")
            print("❌")
    except Exception as e:
        report["results"]["ocr"] = "FAIL"
        report["errors"].append(f"OCR Error: {str(e)}")
        print("❌")

    # --- Write Report ---
    report_file = ROOT / "logs" / "diagnostic_report.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    print("--------------------------------------------------")
    if not report["errors"]:
        print("✨ DIAGNOSTICS PASSED: Your environment looks healthy.")
    else:
        print(f"🚨 FOUND {len(report['errors'])} ISSUE(S):")
        for err in report["errors"]:
            print(f"   - {err}")
    
    print(f"\nReport saved to: {report_file}")
    return report

if __name__ == "__main__":
    run_diagnostics()
