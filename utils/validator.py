"""
Playbook and Environment Validator for Citrix AI Vision Agent.
"""
from __future__ import annotations
import yaml
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

class ValidationResult:
    def __init__(self, is_valid: bool, errors: List[str] = None, warnings: List[str] = None):
        self.is_valid = is_valid
        self.errors = errors or []
        self.warnings = warnings or []

    def to_dict(self):
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings
        }

def validate_playbook_schema(playbook_path: Path) -> ValidationResult:
    errors = []
    warnings = []
    
    if not playbook_path.exists():
        return ValidationResult(False, [f"Playbook file not found: {playbook_path}"])
        
    try:
        content = playbook_path.read_text()
        data = yaml.safe_load(content)
        
        if not isinstance(data, dict):
            return ValidationResult(False, ["Playbook must be a YAML dictionary"])
            
        if "name" not in data:
            errors.append("Missing 'name' field")
            
        steps = data.get("steps", [])
        if not isinstance(steps, list):
            errors.append("'steps' must be a list")
        elif len(steps) == 0:
            warnings.append("Playbook has no steps")
            
        valid_actions = {"click", "type", "wait_for", "pause", "screenshot"}
        
        for i, step in enumerate(steps):
            action = step.get("action")
            if not action:
                errors.append(f"Step {i+1}: Missing 'action'")
            elif action not in valid_actions:
                errors.append(f"Step {i+1}: Invalid action '{action}'")
            
            # Semantic check
            desc = step.get("description", "")
            target = step.get("target", "")
            if action in ["click", "type"] and not target:
                errors.append(f"Step {i+1}: Action '{action}' requires a 'target'")
                
    except Exception as e:
        errors.append(f"YAML Parse Error: {str(e)}")
        
    return ValidationResult(len(errors) == 0, errors, warnings)

def validate_environment() -> ValidationResult:
    errors = []
    warnings = []
    
    # Check for critical libraries
    try:
        import mss
        import cv2
        import numpy as np
        import paddleocr
        import pyautogui
        import rapidfuzz
    except ImportError as e:
        errors.append(f"Missing dependency: {str(e)}")
        
    # Check for monitor access
    try:
        import mss
        with mss.mss() as sct:
            if len(sct.monitors) < 1:
                errors.append("No monitors detected by MSS")
    except Exception as e:
        errors.append(f"Failed to initialize screen capture: {str(e)}")
        
    return ValidationResult(len(errors) == 0, errors, warnings)
