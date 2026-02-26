"""
Memory manager.

Persists per-(screen_id, target_text) statistics to a JSON file.
Stores last known coordinates, success/failure counts, and success_rate.
The executor can query memory to prefer high-confidence coordinates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import config
from utils.logger import get_logger

log = get_logger(__name__)


class MemoryManager:
    """
    Store and retrieve action outcome history.

    Memory schema:
    {
      "<screen_id>|<target_text_lower>": {
        "last_coordinates": [cx, cy] | null,
        "success_count":    int,
        "failure_count":    int,
        "success_rate":     float,          // success / total
        "total_reward":     int
      },
      ...
    }
    """

    def __init__(self) -> None:
        self._path: Path          = config.MEMORY_FILE
        self._data: dict[str, Any] = self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    def record(
        self,
        screen_id: str,
        target_text: str,
        success: bool,
        reward: int,
        coordinates: tuple[int, int] | None = None,
    ) -> None:
        """
        Record one action outcome and persist to disk.

        Args:
            screen_id:   Perceptual screen hash.
            target_text: Element label that was targeted.
            success:     Whether the action succeeded.
            reward:      Reward value from RewardEngine.
            coordinates: (cx, cy) where the action was performed, if known.
        """
        key   = self._key(screen_id, target_text)
        entry = self._data.setdefault(
            key,
            {
                "last_coordinates": None,
                "success_count":    0,
                "failure_count":    0,
                "success_rate":     0.0,
                "total_reward":     0,
            },
        )

        if success:
            entry["success_count"] += 1
        else:
            entry["failure_count"] += 1

        total = entry["success_count"] + entry["failure_count"]
        entry["success_rate"]  = round(entry["success_count"] / total, 4)
        entry["total_reward"] += reward

        if coordinates is not None:
            entry["last_coordinates"] = list(coordinates)

        log.debug(
            "Memory | key='%s' | success_rate=%.2f | reward_total=%d",
            key, entry["success_rate"], entry["total_reward"],
        )
        self._save()

    def get_coordinates(
        self, screen_id: str, target_text: str
    ) -> tuple[int, int] | None:
        """
        Retrieve the last known click coordinates for a given context.

        Args:
            screen_id:   Screen hash ID.
            target_text: Target element label.

        Returns:
            (cx, cy) if available, else None.
        """
        entry = self._data.get(self._key(screen_id, target_text))
        if entry and entry.get("last_coordinates"):
            coords = entry["last_coordinates"]
            return (coords[0], coords[1])
        return None

    def get_success_rate(self, screen_id: str, target_text: str) -> float:
        """
        Return the historical success rate for an action in context.

        Args:
            screen_id:   Screen hash ID.
            target_text: Target element label.

        Returns:
            Float in [0.0, 1.0]. Returns 0.5 (neutral) for unseen combos.
        """
        entry = self._data.get(self._key(screen_id, target_text))
        return entry["success_rate"] if entry else 0.5

    def all_records(self) -> dict[str, Any]:
        """Return a copy of the full memory dictionary."""
        return dict(self._data)

    def summary(self) -> str:
        """Human-readable summary of stored records."""
        lines = [f"Memory: {len(self._data)} record(s)"]
        for key, rec in self._data.items():
            lines.append(
                f"  {key}: success_rate={rec['success_rate']:.2f} "
                f"({rec['success_count']}✓ / {rec['failure_count']}✗) "
                f"reward={rec['total_reward']:+d} "
                f"coords={rec['last_coordinates']}"
            )
        return "\n".join(lines)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> dict[str, Any]:
        if self._path.exists():
            try:
                with self._path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                log.info(
                    "Memory loaded from %s (%d records).", self._path, len(data)
                )
                return data
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Memory load failed (%s) — starting fresh.", exc)
        return {}

    def _save(self) -> None:
        try:
            with self._path.open("w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except OSError as exc:
            log.error("Memory save failed: %s", exc)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _key(screen_id: str, target_text: str) -> str:
        return f"{screen_id}|{target_text.lower().strip()}"
