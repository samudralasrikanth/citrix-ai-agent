import time
import uuid
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

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

    def __init__(self, region: Optional[Dict[str, Any]] = None):
        self.region = region
        self.executors = {
            ChannelType.VISION: VisionExecutor(region=region),
            ChannelType.WEB: WebExecutor(),
            ChannelType.API: APIExecutor()
        }

    def run_playbook(self, playbook_path: Path, dry_run: bool = False) -> Dict[str, Any]:
        """
        Main entry point for running a structured playbook.
        """
        run_id = f"run_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        analytics = ExecutionLogger(run_id)
        
        log.info(f"--- Starting Orchestrator Run: {run_id} ---")

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
        for i, step in enumerate(playbook.steps, 1):
            log.info(f"Step {i}/{len(playbook.steps)}: {step.action} {step.target} via {step.channel}")
            
            # Determine channel
            channel = self._detect_channel(step)
            executor = self.executors.get(channel)
            
            if not executor:
                log.error(f"No executor found for channel: {channel}")
                overall_success = False
                break
                
            step_start = time.time()
            if dry_run:
                result = {"success": True, "message": "Dry run skipped"}
            else:
                result = executor.execute(step.dict())
            
            # Enrich result for analytics
            step_analytics = {
                "step_id": i,
                "action": step.action,
                "target": step.target,
                "channel": channel,
                "duration": round(time.time() - step_start, 3),
                **result
            }
            analytics.log_step(step_analytics)
            
            if not result.get("success"):
                log.error(f"Step {i} failed: {result.get('error')}")
                overall_success = False
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
