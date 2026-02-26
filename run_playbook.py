"""
Playbook Runner — Citrix AI Vision Agent
==========================================
Reads a YAML test playbook and executes each step against the
saved capture region. Like UFT test scripts or Tosca test cases.

Usage:
    python run_playbook.py playbooks/citrix_login.yaml
    python run_playbook.py playbooks/citrix_login.yaml --dry-run
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

REGION_FILE = Path(__file__).parent / "memory" / "region.json"
DIVIDER     = "─" * 60


# ── Region loader ─────────────────────────────────────────────────────────────

def _load_region(name: str = "") -> dict:
    """Load a region by name, or fall back to the default region.json."""
    if name:
        path = Path(__file__).parent / "memory" / "regions" / f"{name.lower().replace(' ', '_')}.json"
        if not path.exists():
            print(f"\n⚠️  Named region '{name}' not found at: {path}\n")
            # fallback to default
            print(f"   Falling back to default region...\n")
            path = REGION_FILE
    else:
        path = REGION_FILE

    if not path.exists():
        print(f"\n⚠️  No capture region found at: {path}")
        print("   Run setup first: python run.py setup\n")
        sys.exit(1)

    data = json.loads(path.read_text())
    # support both old flat format and new nested format
    return data.get("region", data)


# ── Step executor ─────────────────────────────────────────────────────────────

def _run_step(
    step_num: int,
    step: dict[str, Any],
    capturer: ScreenCapture,
    ocr: OcrEngine,
    detector: ElementDetector,
    executor: ActionExecutor,
    memory: MemoryManager,
    region: dict,
    dry_run: bool = False,
) -> bool:
    """
    Execute one playbook step. Returns True on success.

    Supported step actions:
        click     target: <text>
        type      target: <field label>   value: <text to type>
        wait_for  target: <text>          timeout: <seconds>   (default 10)
        pause     seconds: <float>        (just waits)
        screenshot  (captures and saves, no action)
    """
    action  = step.get("action", "").lower()
    target  = step.get("target", "")
    value   = step.get("value", "")
    desc    = step.get("description", "")
    timeout = step.get("timeout", 10)
    seconds = step.get("seconds", 1.0)

    label = desc or f"{action} '{target}'"
    print(f"\n  Step {step_num:02d}: {label}")
    print(f"           action={action}  target='{target}'" +
          (f"  value='{value}'" if value else "") +
          ("  [DRY RUN]" if dry_run else ""))

    if dry_run:
        return True

    # ── Pause / screenshot don't need vision ─────────────────────────────────
    if action == "pause":
        log.info("Pausing %.1fs …", seconds)
        time.sleep(seconds)
        return True

    if action == "screenshot":
        _, path = capturer.capture_and_save(region=region)
        print(f"           → saved: {path}")
        return True

    # ── Capture current region ────────────────────────────────────────────────
    frame, _ = capturer.capture_and_save(region=region)
    ocr_results = ocr.extract(frame)
    elements    = detector.detect_contours(frame)
    elements    = detector.merge_with_ocr(elements, ocr_results)
    state       = build_screen_state(frame, ocr_results, elements, step=step_num)

    visible = state.get("visible_texts", [])
    print(f"           → OCR saw {len(ocr_results)} text(s): "
          f"{[r['text'] for r in ocr_results[:6]]}")

    if action == "wait_for":
        action_dict = {"action": "wait_for", "target_text": target}
    else:
        action_dict = {"action": action, "target_text": target, "value": value}

    result = executor.execute(
        action=action_dict,
        elements=elements,
        capture_fn=lambda: capturer.capture(region=region),
    )

    success = result["success"]
    if success:
        coords = result.get("coordinates")
        print(f"           ✅  OK" + (f" at {coords}" if coords else ""))
        memory.record(
            screen_id=state["screen_id"],
            target_text=target,
            success=True,
            reward=10,
            coordinates=tuple(coords) if coords else None,
        )
    else:
        err = result.get("error", "unknown")
        print(f"           ❌  FAILED — {err}")
        memory.record(
            screen_id=state["screen_id"],
            target_text=target,
            success=False,
            reward=-10,
        )

    return success


# ── Playbook loader + runner ──────────────────────────────────────────────────

def run_playbook(path: Path, dry_run: bool = False, stop_on_fail: bool = True) -> None:
    if not path.exists():
        print(f"\n❌  Playbook not found: {path}\n")
        sys.exit(1)

    data = yaml.safe_load(path.read_text())
    name    = data.get("name", path.stem)
    steps   = data.get("steps", [])
    region_name = data.get("region", "")

    print()
    print("┌──────────────────────────────────────────────────────┐")
    print(f"│  Playbook : {name:<41}│")
    print(f"│  Steps   : {len(steps):<42}│")
    print(f"│  Mode    : {'DRY RUN (no actions)' if dry_run else 'LIVE RUN':<41}│")
    print("└──────────────────────────────────────────────────────┘")

    region   = _load_region(region_name)
    capturer = ScreenCapture()
    ocr      = OcrEngine()
    detector = ElementDetector()
    executor = ActionExecutor()
    memory   = MemoryManager()

    print(f"\n  Region : {region}")
    print(DIVIDER)

    passed = failed = skipped = 0

    for i, step in enumerate(steps, 1):
        if step.get("skip"):
            print(f"\n  Step {i:02d}: [SKIPPED] {step.get('description', '')}")
            skipped += 1
            continue

        ok = _run_step(i, step, capturer, ocr, detector,
                       executor, memory, region, dry_run=dry_run)

        if ok:
            passed += 1
        else:
            failed += 1
            if stop_on_fail and not dry_run:
                print(f"\n  ⛔  Stopping at step {i} (stop_on_fail=true).")
                break

    print()
    print(DIVIDER)
    print(f"  Results:  ✅ {passed} passed  |  ❌ {failed} failed  |  ⏭  {skipped} skipped")
    print(DIVIDER)
    capturer.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a YAML playbook against the saved capture region"
    )
    parser.add_argument("playbook", type=Path, help="Path to a .yaml playbook file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print steps only, no actions executed")
    parser.add_argument("--no-stop", action="store_true",
                        help="Continue running after a failed step")
    args = parser.parse_args()

    try:
        run_playbook(args.playbook, dry_run=args.dry_run,
                     stop_on_fail=not args.no_stop)
    except KeyboardInterrupt:
        print("\n\n  Interrupted by user.\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
