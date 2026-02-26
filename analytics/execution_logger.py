import json
import time
from pathlib import Path
from typing import Any, Dict, List
import config

class ExecutionLogger:
    """
    Structured execution analytics logger.
    Captures every step in detail for offline analysis and reporting.
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.log_dir = config.LOGS_DIR / "runs" / run_id
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "analytics.jsonlines"
        self.steps: List[Dict[str, Any]] = []

    def log_step(self, step_data: Dict[str, Any]):
        """
        Append a single step execution record.
        """
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "run_id": self.run_id,
            **step_data
        }
        self.steps.append(entry)
        
        # Append to JSONLines for streaming persistence
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def get_summary(self) -> Dict[str, Any]:
        """
        Calculate execution statistics.
        """
        if not self.steps:
            return {"empty": True}
            
        successes = [s for s in self.steps if s.get("success")]
        durations = [s.get("duration", 0) for s in self.steps]
        retries = [s.get("retry_count", 0) for s in self.steps]
        
        summary = {
            "run_id": self.run_id,
            "total_steps": len(self.steps),
            "success_rate": round(len(successes) / len(self.steps), 2),
            "avg_duration": round(sum(durations) / len(durations), 3),
            "max_duration": round(max(durations), 3),
            "total_retries": sum(retries),
            "flaky_targets": self._find_flaky_targets()
        }
        
        # Save summary to disk
        (self.log_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        return summary

    def _find_flaky_targets(self) -> List[str]:
        target_retries = {}
        for s in self.steps:
            t = s.get("target", "unknown")
            target_retries[t] = target_retries.get(t, 0) + s.get("retry_count", 0)
            
        # Return targets with > 0 retries sorted by retry count
        flaky = [t for t, count in target_retries.items() if count > 0]
        flaky.sort(key=lambda x: target_retries[x], reverse=True)
        return flaky
