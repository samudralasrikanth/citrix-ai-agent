import logging
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import config

class JsonFormatter(logging.Formatter):
    """
    Custom formatter that outputs logs as JSON strings.
    """
    def format(self, record):
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }
        
        # Merge extra attributes if present
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            log_data.update(record.extra_data)
            
        return json.dumps(log_data)

def get_logger(name: str):
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
        
    logger.setLevel(os.environ.get("LOG_LEVEL", config.LOG_LEVEL))
    
    # ── Console Handler ──────────────────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    if config.LOG_FORMAT == "json":
        console.setFormatter(JsonFormatter())
    else:
        console.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    logger.addHandler(console)
    
    # ── File Handler (Enterprise Audit Trail) ───────────────────
    if config.LOGS_DIR:
        file_handler = logging.FileHandler(config.LOG_FILE)
        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)
        
    return logger

class ExecutionLogger:
    """
    Special helper for logging structured test step information.
    """
    def __init__(self, test_name: str, execution_id: str = None):
        self.test_name = test_name
        self.execution_id = execution_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = config.LOGS_DIR / f"exec_{self.test_name}_{self.execution_id}.jsonl"
        
    def log_step(self, step_data: Dict[str, Any]):
        """Append a structured JSON line for one step."""
        step_entry = {
            "timestamp": datetime.now().isoformat(),
            "test": self.test_name,
            "execution_id": self.execution_id,
            **step_data
        }
        with open(self.log_path, "a") as f:
            f.write(json.dumps(step_entry) + "\n")
