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

def align_region(playbook_path: Path) -> Optional[Dict[str, Any]]:
    """
    Alignment phase: Find the target window/region.
    Checks the current directory and parent directory for config/reference files.
    """
    search_paths = [playbook_path.parent, playbook_path.parent.parent]
    
    capturer = ScreenCapture()
    region = None

    try:
        for path in search_paths:
            ref_path = path / "reference.png"
            reg_path = path / "region.json"
            cfg_path = path / "suite_config.json"

            # 1. Try visual alignment if reference exists
            if ref_path.exists():
                region = capturer.locate_window(ref_path)
                if region:
                    log.info(f"Visual alignment success using {ref_path}")
                    return region

            # 2. Try suite_config.json
            if cfg_path.exists():
                try:
                    data = json.loads(cfg_path.read_text())
                    if data.get("platform") == "web":
                        log.info("Web platform detected, bypassing region alignment.")
                        return {}
                    static_reg = data.get("region")
                    if static_reg:
                        log.info(f"Using static region from {cfg_path.name}")
                        return static_reg
                except:
                    pass

            # 3. Fallback to region.json
            if reg_path.exists():
                try:
                    data = json.loads(reg_path.read_text())
                    log.info(f"Using static region from {reg_path.name}")
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
    
    # Try to find the suite root (where suite_config.json lives)
    suite_root = None
    for p in [playbook_file.parent, playbook_file.parent.parent]:
        if (p / "suite_config.json").exists():
            suite_root = p
            break

    region = align_region(playbook_file)
    
    if not region:
        # If no region found, we can still try to run (global mode) or fail
        print(json.dumps({"status": "warning", "message": "No specific region found. Running in global mode."}), flush=True)
        region = {}

    # 2. Execution Phase
    # Pass suite_root so executors know where to find their local memory/maps
    orch = Orchestrator(region=region, suite_root=suite_root)
    
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
