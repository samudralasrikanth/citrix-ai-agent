"""
Enterprise Playbook Runner — Citrix AI Vision Agent
Robust, observable, and hardened for production use.
"""
from __future__ import annotations
import argparse
import json
import sys
import time
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import config
from capture.screen_capture import ScreenCapture
from vision.ocr_engine import OcrEngine
from vision.element_detector import ElementDetector
from agent.action_executor import ActionExecutor
from utils.logger import get_logger, ExecutionLogger
from utils.validator import validate_playbook_schema

log = get_logger(__name__)

class ExecutionContext:
    """Manages state for a single playbook execution."""
    def __init__(self, test_path: Path, dry_run: bool = False):
        self.test_path = test_path
        self.test_id = test_path.name
        self.dry_run = dry_run
        self.start_time = datetime.now()
        
        # Core Components
        self.capturer = ScreenCapture()
        self.ocr = OcrEngine()
        self.detector = ElementDetector()
        self.executor = ActionExecutor()
        
        # Execution State
        self.current_region = None
        self.steps_passed = 0
        self.steps_failed = 0
        self.audit_log = ExecutionLogger(self.test_id)
        
    def stream_json(self, status: str, message: str, **kwargs):
        """Stream structured JSON to stdout for parent process parsing."""
        payload = {
            "status": status,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        print(json.dumps(payload), flush=True)

    def close(self):
        self.capturer.close()

def run_production_test(context: ExecutionContext):
    """Execution logic utilizing state isolation and error classification."""
    
    # 1. Validation Phase
    context.stream_json("init", f"Starting hardened runner for: {context.test_id}")
    
    pb_res = validate_playbook_schema(context.test_path / "playbook.yaml")
    if not pb_res.is_valid:
        error_msg = f"Playbook Validation Failed: {'; '.join(pb_res.errors)}"
        context.stream_json("error", error_msg, code=400)
        return

    # 2. Initialization Phase
    ref_path = context.test_path / "reference.png"
    reg_path = context.test_path / "region.json"
    
    context.stream_json("scan", "Aligning interface coordinates...")
    context.current_region = context.capturer.locate_window(ref_path)
    
    if not context.current_region:
        if reg_path.exists():
            reg_data = json.loads(reg_path.read_text())
            context.current_region = reg_data.get("region", reg_data)
            context.stream_json("warning", "Visual match failed, falling back to static region.")
        else:
            context.stream_json("error", "Target window not found and no region data exists.", code=config.ERROR_CODES["ERR_MATCH_FAIL"])
            return

    # 3. Execution Phase
    steps = yaml.safe_load((context.test_path / "playbook.yaml").read_text()).get("steps", [])
    total = len(steps)
    context.stream_json("init", f"Loaded {total} steps.", total=total)
    
    for i, step in enumerate(steps, 1):
        try:
            success = _execute_hardened_step(i, step, context, total)
            if success:
                context.steps_passed += 1
            else:
                context.steps_failed += 1
                if not context.dry_run:
                    context.stream_json("error", f"Abort: Step {i} failed.", step=i)
                    break
        except Exception as e:
            context.stream_json("error", f"Step {i} crashed: {str(e)}", step=i, code=500)
            break

    # 4. Reporting Phase
    summary = {
        "passed": context.steps_passed,
        "failed": context.steps_failed,
        "total": len(steps),
        "duration": (datetime.now() - context.start_time).total_seconds()
    }
    context.stream_json("finish", "Audit complete.", summary=summary)
    
    # Save Final Report
    report_path = context.test_path / "report_hardened.json"
    report_path.write_text(json.dumps(summary, indent=2))

def _execute_hardened_step(step_idx: int, step: Dict[str, Any], context: ExecutionContext, total: int = 0) -> bool:
    """Atomic step execution with retry backoff and detailed logging."""
    action = step.get("action", "").lower()
    target = step.get("target", "")
    metadata = {"step": step_idx, "action": action, "target": target, "current": step_idx, "total": total}
    
    context.stream_json("step_start", f"[{step_idx}/{total}] {action}: {target}", **metadata)
    
    if context.dry_run:
        return True

    # 1. Optimised path for meta-actions (no vision required)
    if action in ["pause", "screenshot"]:
        res = context.executor.execute(
            action={"action": action, "target_text": target, "value": step.get("value", "")},
            elements=[],
            capture_fn=lambda: context.capturer.capture(region=context.current_region)
        )
        context.audit_log.log_step({**metadata, "res": res})
        if res["success"]:
            context.stream_json("step_success", f"OK: {action}", step=step_idx)
            return True
        return False

    # Retry mechanism with backoff
    for attempt in range(1, config.MAX_ACTION_RETRIES + 1):
        try:
            # 2. Capture and Vision
            frame = context.capturer.capture(region=context.current_region)
            ocr_results = context.ocr.extract(frame)
            elements = context.detector.detect_contours(frame)
            elements = context.detector.merge_with_ocr(elements, ocr_results)
            
            # 3. Offset mapping: convert region-relative → absolute screen coordinates
            reg = context.current_region or {}
            ox  = int(reg.get("left", 0))
            oy  = int(reg.get("top",  0))
            for e in elements:
                e["cx"] = int(e.get("cx", 0)) + ox
                e["cy"] = int(e.get("cy", 0)) + oy
            
            # 4. Execute
            res = context.executor.execute(
                action={"action": action, "target_text": target, "value": step.get("value", "")},
                elements=elements,
                capture_fn=lambda: context.capturer.capture(region=context.current_region)
            )
            
            # Log audit
            context.audit_log.log_step({**metadata, "attempt": attempt, "res": res})
            
            if res["success"]:
                context.stream_json("step_success", f"OK: {action}", step=step_idx)
                return True
                
            # Backoff before retry
            if attempt < config.MAX_ACTION_RETRIES:
                sleep_time = config.RETRY_BACKOFF_BASE * attempt
                context.stream_json("retry", f"No change, retrying in {sleep_time}s...", attempt=attempt)
                time.sleep(sleep_time)
                
        except Exception as e:
            log.error("Step execution error: %s", e)
            
    return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    ctx = None
    try:
        # Pre-emptive signaling for a smoother UI experience
        print(json.dumps({"status": "init", "message": "Preparing Vision Engine...", "timestamp": datetime.now().isoformat()}), flush=True)
        
        ctx = ExecutionContext(args.folder, dry_run=args.dry_run)
        run_production_test(ctx)
    except Exception as e:
        print(json.dumps({"status": "error", "message": f"Global failure: {str(e)}"}))
        sys.exit(1)
    finally:
        if ctx: ctx.close()

if __name__ == "__main__":
    main()
