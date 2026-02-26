"""
╔══════════════════════════════════════════════════════════════════╗
║  Coordinate Memory — Persistent Click Cache                     ║
║  Stores successful click coordinates keyed by normalized label  ║
║  so they can be re-used on the next run without a vision scan.  ║
╚══════════════════════════════════════════════════════════════════╝

Storage schema (memory/click_memory.json):
{
  "ok": {
      "cx": 843, "cy": 412,
      "region_hash": "a3f0...",   # hash of region.json content
      "hits": 7,
      "last_used": "2026-02-26T12:00:00"
  },
  ...
}

The region_hash guards against stale coordinates from a different
window layout.  If the hash differs the entry is ignored.
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
_MAX_ENTRIES = 500  # evict LRU when over limit


class ClickMemory:
    """
    Thread-*safe-enough* (GIL) in-process cache backed by a JSON file.
    Loaded once on first instantiation, written on every successful save.
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
        self._region_hash = _hash_region(region) if region else ""

    # ── Public API ─────────────────────────────────────────────────────────────

    def get(self, label: str) -> Optional[Tuple[int, int]]:
        """
        Return cached (cx, cy) for *label* if it exists and the region matches.
        Returns None if not found, stale, or region mismatch.
        """
        key = normalize(label)
        entry = self._data.get(key)
        if not entry:
            return None
        # Guard against stale coordinates from a different window
        if self._region_hash and entry.get("region_hash") != self._region_hash:
            log.debug("Memory hit for '%s' rejected — region hash mismatch.", label)
            return None
        return int(entry["cx"]), int(entry["cy"])

    def save(self, label: str, cx: int, cy: int) -> None:
        """Persist a successfully clicked coordinate for future use."""
        key = normalize(label)
        existing = self._data.get(key, {})
        self._data[key] = {
            "cx":          cx,
            "cy":          cy,
            "region_hash": self._region_hash,
            "hits":        existing.get("hits", 0) + 1,
            "last_used":   datetime.now().isoformat(timespec="seconds"),
        }
        self._evict()
        self._write()
        log.debug("ClickMemory saved: '%s' → (%d, %d) [hits=%d]",
                  label, cx, cy, self._data[key]["hits"])

    def invalidate(self, label: str) -> None:
        """Remove a cached entry (called when a click did NOT produce a change)."""
        key = normalize(label)
        if key in self._data:
            del self._data[key]
            self._write()
            log.debug("ClickMemory invalidated: '%s'", label)

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
        """Evict oldest entries when the cache grows too large."""
        if len(self._data) <= _MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._data,
            key=lambda k: self._data[k].get("last_used", ""),
        )
        for k in sorted_keys[: len(self._data) - _MAX_ENTRIES]:
            del self._data[k]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_region(region: Dict[str, Any]) -> str:
    """Stable hash of region geometry for stale-entry detection."""
    canonical = json.dumps(
        {k: region.get(k, 0) for k in ("left", "top", "width", "height")},
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
