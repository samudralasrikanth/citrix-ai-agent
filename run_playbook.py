"""
Playbook Runner (Folder Based) — Citrix AI Vision Agent
======================================================
1. Loads a test from a folder path.
2. DYNAMICALLY scans the screen for 'reference.png' to find the window.
3. Executes steps relative to the window's current position.
"""

from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
import yaml

import config
from capture.screen_capture import ScreenCapture
from vision.ocr_engine import OcrEngine
from vision.element_detector import ElementDetector
from vision.screen_state import build_screen_state
from agent.action_executor import ActionExecutor
from agent.memory_manager import MemoryManager
from utils.logger import get_logger

log = get_logger(__name__)
DIVIDER = "─" * 60

def run_test_folder(folder_path: Path, dry_run: bool = False, stop_on_fail: bool = True) -> None:
    if not folder_path.exists() or not folder_path.is_dir():
        print(f"\n❌ Test folder not found: {folder_path}\n")
        sys.exit(1)

    pb_path = folder_path / "playbook.yaml"
    ref_path = folder_path / "reference.png"
    reg_path = folder_path / "region.json"

    if not pb_path.exists():
        print(f"❌ playbook.yaml missing in {folder_path}")
        sys.exit(1)

    data = yaml.safe_load(pb_path.read_text())
    name = data.get("name", folder_path.name)
    steps = data.get("steps", [])

    print()
    print("┌──────────────────────────────────────────────────────┐")
    print(f"│  Test Case : {name[:40]:<41}│")
    print(f"│  Folder    : {folder_path.name[:40]:<41}│")
    print(f"│  Mode      : {'DRY RUN' if dry_run else 'LIVE RUN':<41}│")
    print("└──────────────────────────────────────────────────────┘")

    capturer = ScreenCapture()
    
    # ── DYNAMIC WINDOW LOCATION ───────────────────────────────────────────────
    print("\n🔍 Scanning screen to locate application window...")
    current_region = capturer.locate_window(ref_path)
    
    if current_region:
        print(f"✅ Found window at: {current_region['left']}, {current_region['top']} ({current_region['width']}x{current_region['height']})")
    else:
        # Fallback to saved region if reference image match fails
        if reg_path.exists():
            print("⚠️  Reference image match failed. Using last saved region info.")
            reg_data = json.loads(reg_path.read_text())
            current_region = reg_data.get("region", reg_data)
        else:
            print("❌ Could not locate window and no region info exists.")
            sys.exit(1)

    # ── Init Components ───────────────────────────────────────────────────────
    ocr = OcrEngine()
    detector = ElementDetector()
    executor = ActionExecutor()
    memory = MemoryManager()
    
    print(DIVIDER)
    passed = failed = skipped = 0

    for i, step in enumerate(steps, 1):
        if step.get("skip"):
            print(f"\nStep {i:02d}: [SKIPPED] {step.get('description', '')}")
            skipped += 1
            continue

        # Execute step using the dynamic current_region
        ok = _run_step(i, step, capturer, ocr, detector, executor, memory, current_region, dry_run)

        if ok: passed += 1
        else:
            failed += 1
            if stop_on_fail and not dry_run:
                print(f"\n⛔ Stopping at step {i} (failure).")
                break

    print()
    print(DIVIDER)
    print(f"Results:  ✅ {passed} passed  |  ❌ {failed} failed  |  ⏭  {skipped} skipped")
    print(DIVIDER)
    capturer.close()

def _run_step(step_num, step, capturer, ocr, detector, executor, memory, region, dry_run) -> bool:
    action = step.get("action", "").lower()
    target = step.get("target", "")
    value = step.get("value", "")
    desc = step.get("description", "")
    timeout = step.get("timeout", 10)
    seconds = step.get("seconds", 1.0)

    label = desc or f"{action} '{target}'"
    print(f"\nStep {step_num:02d}: {label}")
    if dry_run: return True

    if action == "pause":
        time.sleep(seconds)
        return True

    if action == "screenshot":
        _, path = capturer.capture_and_save(region=region)
        print(f"      → saved: {path}")
        return True

    # ── Capture with dynamic region ───────────────────────────────────────────
    frame = capturer.capture(region=region)
    ocr_results = ocr.extract(frame)
    elements = detector.detect_contours(frame)
    elements = detector.merge_with_ocr(elements, ocr_results)
    
    action_dict = {"action": action, "target_text": target, "value": value}
    if action == "wait_for": action_dict["action"] = "wait_for"

    result = executor.execute(
        action=action_dict,
        elements=elements,
        capture_fn=lambda: capturer.capture(region=region),
    )

    if result["success"]:
        print(f"      ✅ OK")
        return True
    else:
        print(f"      ❌ FAILED: {result.get('error', 'unknown error')}")
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path, help="Path to test folder")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    run_test_folder(args.folder, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
