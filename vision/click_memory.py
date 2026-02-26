"""
╔══════════════════════════════════════════════════════════════════╗
║  Coordinate Memory — Persistent Click Cache                     ║
║  Stores successful click coordinates keyed by normalized label  ║
║  AND region hash to handle multiple window layouts correctly.   ║
╚══════════════════════════════════════════════════════════════════╝

Storage schema (memory/click_memory.json):
{
  "ok": {
      "a3f01b72...": {  # region hash
          "cx": 843, "cy": 412,
          "hits": 7,
          "last_used": "2026-02-26T12:00:00"
      }
  }
}
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import config
from vision.text_normalizer import normalize

log = logging.getLogger("ClickMemory")

_MEMORY_FILE = config.MEMORY_DIR / "click_memory.json"
_MAX_ENTRIES = 1000  # Total keys across all regions


class ClickMemory:
    """
    Thread-safe-enough (GIL) in-process cache backed by a JSON file.
    Supports multiple window layouts via region hashing.
    """

    _instance: Optional["ClickMemory"] = None

    def __new__(cls, region: Optional[Dict[str, Any]] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data: Dict[str, Any] = {}
            cls._instance._loaded = False
        return cls._instance

    def __init__(self, region: Optional[Dict[str, Any]] = None):
        if not self._loaded:
            self._load()
        # Note: self._current_region_hash is NOT used in get/save anymore
        # to avoid singleton state corruption. We compute it on demand or 
        # pass the region object.

    # ── Public API ─────────────────────────────────────────────────────────────

    def get(self, label: str, region: Optional[Dict[str, Any]]) -> Optional[Tuple[int, int]]:
        """
        Return cached (cx, cy) for *label* if it exists for the current region layout.
        """
        r_hash = _hash_region(region)
        if not r_hash:
            return None
            
        key = normalize(label)
        label_entries = self._data.get(key)
        if not label_entries:
            return None
            
        entry = label_entries.get(r_hash)
        if not entry:
            return None
            
        return int(entry["cx"]), int(entry["cy"])

    def save(self, label: str, cx: int, cy: int, region: Optional[Dict[str, Any]]) -> None:
        """Persist a successfully clicked coordinate."""
        r_hash = _hash_region(region)
        if not r_hash:
            return
            
        key = normalize(label)
        if key not in self._data:
            self._data[key] = {}
            
        existing = self._data[key].get(r_hash, {})
        self._data[key][r_hash] = {
            "cx":          cx,
            "cy":          cy,
            "hits":        existing.get("hits", 0) + 1,
            "last_used":   datetime.now().isoformat(timespec="seconds"),
        }
        
        self._evict()
        self._write()
        log.debug("ClickMemory saved: '%s' [%s] → (%d, %d)", 
                  label, r_hash[:8], cx, cy)

    def invalidate(self, label: str, region: Optional[Dict[str, Any]]) -> None:
        """Remove a cached entry for the specific region."""
        r_hash = _hash_region(region)
        if not r_hash:
            return
            
        key = normalize(label)
        if key in self._data and r_hash in self._data[key]:
            del self._data[key][r_hash]
            if not self._data[key]:
                del self._data[key]
            self._write()
            log.debug("ClickMemory invalidated: '%s' [%s]", label, r_hash[:8])

    # ── Private ────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if _MEMORY_FILE.exists():
                self._data = json.loads(_MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Could not load click memory: %s — starting fresh.", exc)
            self._data = {}
        self._loaded = True

    def _write(self) -> None:
        try:
            _MEMORY_FILE.write_text(
                json.dumps(self._data, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            log.warning("Could not persist click memory: %s", exc)

    def _evict(self) -> None:
        """Simple eviction if storage grows too large."""
        if len(self._data) <= _MAX_ENTRIES:
            return
        # Very crude eviction: just pop a few keys
        # In a real enterprise system, we'd do global LRU across all sub-keys.
        keys = list(self._data.keys())
        for i in range(len(keys) - _MAX_ENTRIES):
            del self._data[keys[i]]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_region(region: Optional[Dict[str, Any]]) -> str:
    """Stable hash of region geometry."""
    if not region:
        return "global"
    canonical = json.dumps(
        {k: region.get(k, 0) for k in ("left", "top", "width", "height")},
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
