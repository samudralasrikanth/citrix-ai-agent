import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import config

class MemoryEngine:
    """
    Adaptive Memory Engine for self-healing automation.
    Stores historical success/failure of actions indexed by screen state and target.
    """

    def __init__(self, storage_path: Path = None):
        self.path = storage_path or config.MEMORY_DIR / "adaptive_memory.json"
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except:
                return {}
        return {}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2))

    def get_key(self, screen_hash: str, target: str) -> str:
        return f"{screen_hash}:{target.lower().strip()}"

    def get_entry(self, screen_hash: str, target: str) -> Optional[Dict[str, Any]]:
        key = self.get_key(screen_hash, target)
        return self._data.get(key)

    def record_success(self, screen_hash: str, target: str, coords: Tuple[int, int]):
        key = self.get_key(screen_hash, target)
        entry = self._data.setdefault(key, {
            "target": target,
            "screen_hash": screen_hash,
            "coordinates": list(coords),
            "success_count": 0,
            "failure_count": 0,
            "last_seen": ""
        })
        entry["success_count"] += 1
        entry["coordinates"] = list(coords)
        entry["last_seen"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.save()

    def record_failure(self, screen_hash: str, target: str):
        key = self.get_key(screen_hash, target)
        if key in self._data:
            self._data[key]["failure_count"] += 1
            self.save()

    def get_historical_score(self, screen_hash: str, target: str) -> float:
        """Returns success rate in [0.0, 1.0]. Neutral (0.5) if unknown."""
        entry = self.get_entry(screen_hash, target)
        if not entry:
            return 0.5
        total = entry["success_count"] + entry["failure_count"]
        if total == 0:
            return 0.5
        return entry["success_count"] / total
