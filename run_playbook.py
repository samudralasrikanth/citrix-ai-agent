"""
Hardened Orchestrator Runner.
Wraps the enterprise orchestrator with SSE-compatible JSON streaming.
"""
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import config
from orchestrator.orchestrator import Orchestrator
from capture.screen_capture import ScreenCapture
from utils.logger import get_logger

log = get_logger("Runner")

def align_region(test_path: Path) -> Optional[Dict[str, Any]]:
    """
    Alignment phase: Find the target window/region.
    """
    ref_path = test_path / "reference.png"
    reg_path = test_path / "region.json"
    
    capturer = ScreenCapture()
    try:
        # 1. Try visual alignment
        region = capturer.locate_window(ref_path)
        if region:
            log.info(f"Visual alignment success: {region['left']},{region['top']}")
            return region
            
        # 2. Fallback to static region data
        if reg_path.exists():
            try:
                data = json.loads(reg_path.read_text())
                log.info("Visual match failed, using static region from region.json")
                return data.get("region", data)
            except:
                pass
    finally:
        capturer.close()
    
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("playbook", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    playbook_file = args.playbook
    test_path = playbook_file.parent

    # 1. Alignment Phase
    print(json.dumps({"status": "scan", "message": "Aligning interface coordinates..."}), flush=True)
    region = align_region(test_path)
    
    if not region:
        # If no region found, we can still try to run (global mode) or fail
        print(json.dumps({"status": "warning", "message": "No specific region found. Running in global mode."}), flush=True)
        region = {}

    # 2. Execution Phase
    orch = Orchestrator(region=region)
    
    def on_progress(p):
        print(json.dumps(p), flush=True)

    try:
        result = orch.run_playbook(playbook_file, dry_run=args.dry_run, on_progress=on_progress)
        
        if result.get("success"):
            summary = result.get("summary", {})
            print(json.dumps({"status": "finish", "message": "Audit complete.", "summary": summary}), flush=True)
        else:
            print(json.dumps({"status": "error", "message": result.get("error", "Execution failed.")}), flush=True)
            
    except Exception as e:
        print(json.dumps({"status": "error", "message": f"Global failure: {str(e)}"}), flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
