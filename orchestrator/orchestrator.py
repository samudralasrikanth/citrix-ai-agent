import time
import uuid
import yaml
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from executors.vision_executor import VisionExecutor
from executors.web_executor import WebExecutor
from executors.api_executor import APIExecutor
from validation.playbook_schema import validate_playbook, ChannelType
from analytics.execution_logger import ExecutionLogger
from utils.logger import get_logger

log = get_logger("Orchestrator")

class Orchestrator:
    """
    Enterprise Orchestrator.
    Manages multi-channel execution, ranking, self-healing, and analytics.
    """

    def __init__(self, region: Optional[Dict[str, Any]] = None, suite_root: Optional[Path] = None):
        self.region = region
        self.suite_root = suite_root
        self.executors = {
            ChannelType.VISION: VisionExecutor(region=region, suite_root=suite_root),
            ChannelType.WEB: WebExecutor(),
            ChannelType.API: APIExecutor()
        }

    def run_playbook(self, playbook_path: Path, dry_run: bool = False, on_progress: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        """
        Main entry point for running a structured playbook.
        """
        def emit(status, message, **kwargs):
            if on_progress:
                on_progress({"status": status, "message": message, "timestamp": time.strftime("%Y-%m-%dT%H%M%SZ"), **kwargs})

        run_id = f"run_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        reports_dir = (self.suite_root / "reports") if self.suite_root else None
        analytics = ExecutionLogger(run_id, base_dir=reports_dir)
        
        emit("init", f"Starting hardened run: {run_id}")

        # 1. Load and Validate
        try:
            raw_data = yaml.safe_load(playbook_path.read_text())
            playbook = validate_playbook(raw_data)
            log.info(f"Playbook validated: {playbook.name} ({len(playbook.steps)} steps)")
        except Exception as e:
            log.error(f"Validation failed: {e}")
            return {"success": False, "error": f"Validation failed: {str(e)}"}

        # 2. Execution Loop
        overall_success = True
        total_steps = len(playbook.steps)
        emit("init", f"Loaded {total_steps} steps.", total=total_steps)

        for i, step in enumerate(playbook.steps, 1):
            msg = f"[{i}/{total_steps}] {step.action}: {step.target}"
            emit("step_start", msg, step=i, total=total_steps, action=step.action, target=step.target)
            
            # Determine channel
            channel = self._detect_channel(step)
            executor = self.executors.get(channel)
            
            if not executor:
                err = f"No executor for channel: {channel}"
                emit("error", err, step=i)
                overall_success = False
                break
                
            step_start = time.time()
            if dry_run:
                result = {"success": True, "message": "Dry run skipped"}
            else:
                result = executor.execute(step.dict())
            
            # Enrich result for analytics
            duration = round(time.time() - step_start, 3)
            step_analytics = {
                "step_id": i,
                "action": step.action,
                "target": step.target,
                "channel": channel,
                "duration": duration,
                **result
            }
            analytics.log_step(step_analytics)
            
            if result.get("success"):
                emit("step_success", f"OK: {step.action}", step=i)
            else:
                err = result.get("error", "Unknown error")
                emit("error", f"Step {i} failed: {err}", step=i)
                overall_success = False
                if not dry_run:
                    break

        # 3. Finalize
        summary = analytics.get_summary()
        log.info(f"--- Run {run_id} Complete. Success: {overall_success} ---")
        return {
            "success": overall_success,
            "run_id": run_id,
            "summary": summary
        }

    def _detect_channel(self, step: Any) -> ChannelType:
        """
        Heuristic to detect the correct automation channel if set to 'auto'.
        """
        if step.channel != ChannelType.AUTO:
            return step.channel
            
        # Logic for 'auto' detection
        if step.action == "call" or step.config:
            return ChannelType.API
        
        # Default to Vision for POC
        return ChannelType.VISION
