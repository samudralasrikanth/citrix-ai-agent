"""
Reward engine: assigns a scalar signal to each action outcome.
"""

from __future__ import annotations

from typing import Any

import config
from utils.logger import get_logger

log = get_logger(__name__)


class RewardEngine:
    """
    Simple heuristic reward scorer.

    Rules (evaluated in order):
      1. Execution failure / exception        → REWARD_ERROR  (-10)
      2. Error keyword detected on new screen → REWARD_ERROR  (-10)
      3. Screen did not change                → REWARD_NO_CHANGE (-5)
      4. Screen changed (no error found)      → REWARD_SUCCESS (+10)
    """

    def score(
        self,
        action: dict[str, Any],
        exec_result: dict[str, Any],
        prev_state: dict,
        new_state: dict,
    ) -> int:
        """
        Compute the reward for a single (action, transition) pair.

        Args:
            action:      Original Action dict.
            exec_result: Dict returned by ActionExecutor.execute().
            prev_state:  ScreenState before the action.
            new_state:   ScreenState after the action.

        Returns:
            Integer reward value.
        """
        # ── 1. Execution error ────────────────────────────────────────────────
        if not exec_result.get("success") or exec_result.get("error"):
            log.info(
                "Reward %+d | reason=execution_error | error=%s",
                config.REWARD_ERROR, exec_result.get("error"),
            )
            return config.REWARD_ERROR

        new_texts_lower = {t.lower() for t in new_state.get("visible_texts", [])}

        # ── 2. Error keyword on screen ────────────────────────────────────────
        detected_error = next(
            (kw for kw in config.ERROR_KEYWORDS if kw in new_texts_lower), None
        )
        if detected_error:
            log.info(
                "Reward %+d | reason=error_keyword | keyword='%s'",
                config.REWARD_ERROR, detected_error,
            )
            return config.REWARD_ERROR

        # ── 3. No screen change ───────────────────────────────────────────────
        if not exec_result.get("screen_changed"):
            log.info(
                "Reward %+d | reason=no_change | diff=%.4f",
                config.REWARD_NO_CHANGE, exec_result.get("diff_ratio", 0.0),
            )
            return config.REWARD_NO_CHANGE

        # ── 4. Success ────────────────────────────────────────────────────────
        log.info(
            "Reward %+d | reason=screen_changed | diff=%.4f | %s → %s",
            config.REWARD_SUCCESS,
            exec_result.get("diff_ratio", 0.0),
            prev_state.get("screen_id"),
            new_state.get("screen_id"),
        )
        return config.REWARD_SUCCESS
