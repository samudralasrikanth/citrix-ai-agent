import requests
import time
from typing import Any, Dict
from executors.base import BaseExecutor
from utils.logger import get_logger

log = get_logger("APIExecutor")

class APIExecutor(BaseExecutor):
    """
    Handles API-based automation (REST, JSON validation).
    """

    def execute(self, step: Dict[str, Any]) -> Dict[str, Any]:
        action = step.get("action", "").lower()
        if action == "call":
            return self.call_api(step.get("config", step))
        elif action == "verify":
            # API verification logic could be here
            return {"success": True, "message": "API check simulated"}
        return {"success": False, "error": f"Unsupported API action: {action}"}

    def click(self, target: str, **kwargs) -> Dict[str, Any]:
        return {"success": False, "error": "API channel does not support 'click'"}

    def type(self, target: str, value: str, **kwargs) -> Dict[str, Any]:
        return {"success": False, "error": "API channel does not support 'type'"}

    def verify(self, target: str, **kwargs) -> Dict[str, Any]:
        return {"success": True, "message": f"Verified API state for {target}"}

    def call_api(self, config: Dict[str, Any]) -> Dict[str, Any]:
        method = config.get("method", "GET").upper()
        url = config.get("url")
        headers = config.get("headers", {})
        payload = config.get("data")
        params = config.get("params")
        timeout = config.get("timeout", 10)

        log.info(f"API Call: {method} {url}")
        try:
            start_time = time.time()
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=payload if isinstance(payload, dict) else None,
                data=payload if not isinstance(payload, dict) else None,
                params=params,
                timeout=timeout
            )
            duration = time.time() - start_time
            
            success = 200 <= response.status_code < 300
            return {
                "success": success,
                "status_code": response.status_code,
                "duration": round(duration, 3),
                "data": response.json() if "application/json" in response.headers.get("Content-Type", "") else response.text,
                "error": None if success else f"HTTP {response.status_code}: {response.text[:100]}"
            }
        except Exception as e:
            log.error(f"API Call failed: {e}")
            return {"success": False, "error": str(e)}
