"""
Heuristic planner — fully deterministic, no LLM, no external calls.

Uses RapidFuzz to match goal keywords against visible screen text,
then emits a structured action list.
"""

from __future__ import annotations

import re
from typing import Any

import config
from vision.similarity import best_match, all_matches
from utils.logger import get_logger

log = get_logger(__name__)

Action = dict[str, Any]
# {"action": "click"|"type"|"wait_for", "target_text": str, "value": str (optional)}


class Planner:
    """
    Rule-based, fuzzy-matching planner.

    Goal syntax (informal):
        "click <label>"
        "type <value> in <field>"
        "wait_for <text>"
        Free text → planner extracts nouns and tries to fuzzy-match visible elements.
    """

    # ── Public ────────────────────────────────────────────────────────────────

    def plan(self, goal: str, screen_state: dict) -> list[Action]:
        """
        Convert a goal string into an ordered action list.

        Strategy:
          1. Exact keyword dispatch (click / type / wait_for prefix).
          2. Fuzzy keyword extraction — split goal into tokens, find best
             matching visible text, generate click action.
          3. If nothing matches → emit a single wait_for action.

        Args:
            goal:         Natural-language goal (e.g. "click Submit").
            screen_state: Output of build_screen_state().

        Returns:
            List of Action dicts (never empty — fallback is a wait_for).
        """
        visible: list[str] = screen_state.get("visible_texts", [])
        goal_stripped       = goal.strip()
        goal_lower          = goal_stripped.lower()

        # ── 1. Explicit "click <target>" ─────────────────────────────────────
        if goal_lower.startswith("click"):
            return self._plan_click(goal_stripped, visible)

        # ── 2. Explicit "type <value> in <field>" ────────────────────────────
        if goal_lower.startswith("type") and " in " in goal_lower:
            return self._plan_type(goal_stripped, visible)

        # ── 3. Explicit "wait_for <text>" ────────────────────────────────────
        if goal_lower.startswith("wait_for"):
            target = re.sub(r"(?i)^wait_for\s+", "", goal_stripped).strip()
            return [{"action": "wait_for", "target_text": target}]

        # ── 4. Free-text: fuzzy keyword scan over visible texts ───────────────
        return self._plan_freetext(goal_stripped, visible)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _plan_click(self, goal: str, visible: list[str]) -> list[Action]:
        """Parse 'click <target>' and fuzzy-resolve against visible texts."""
        raw_target = re.sub(r"(?i)^click\s+", "", goal).strip()
        resolved   = self._resolve(raw_target, visible)
        action     = {"action": "click", "target_text": resolved}
        log.info("Planned: %s", action)
        return [action]

    def _plan_type(self, goal: str, visible: list[str]) -> list[Action]:
        """Parse 'type <value> in <field>' and fuzzy-resolve the field."""
        after_type        = re.sub(r"(?i)^type\s+", "", goal).strip()
        value_part, field = after_type.split(" in ", 1)
        resolved_field    = self._resolve(field.strip(), visible)
        action = {
            "action":      "type",
            "target_text": resolved_field,
            "value":       value_part.strip(),
        }
        log.info("Planned: %s", action)
        return [action]

    def _plan_freetext(self, goal: str, visible: list[str]) -> list[Action]:
        """
        Extract meaningful tokens from goal, find the best fuzzy match
        among visible texts, and produce a click action.
        """
        tokens = [t for t in re.split(r"\W+", goal) if len(t) > 2]
        actions: list[Action] = []

        for token in tokens:
            match = best_match(token, visible)
            if match:
                text, score = match
                log.info("Token '%s' → '%s' (score=%.1f)", token, text, score)
                actions.append({"action": "click", "target_text": text})

        if actions:
            return actions

        # Final fallback: wait and re-observe
        log.warning("No fuzzy match for goal '%s' — inserting wait_for.", goal)
        return [{"action": "wait_for", "target_text": goal}]

    def _resolve(self, raw: str, visible: list[str]) -> str:
        """
        Fuzzy-resolve *raw* against visible texts.
        Returns the best match if found, otherwise returns *raw* unchanged.
        """
        match = best_match(raw, visible)
        if match:
            resolved, score = match
            log.debug("Resolved '%s' → '%s' (score=%.1f)", raw, resolved, score)
            return resolved
        log.debug("No visible match for '%s'; using as-is.", raw)
        return raw
