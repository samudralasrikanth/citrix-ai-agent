"""
Action executor.

Resolves elements by fuzzy-matching target_text against element labels,
executes the action via PyAutoGUI, and validates the screen changed.
Retries up to config.MAX_ACTION_RETRIES times on no-change failures.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pyautogui

import config
from utils.image_utils import pixel_diff_ratio
from utils.logger import get_logger
from vision.similarity import best_match

log = get_logger(__name__)

pyautogui.FAILSAFE = True   # Move mouse → top-left corner to abort
pyautogui.PAUSE    = 0.25


class ActionExecutor:
    """
    Executes Action dicts against the live desktop.

    Supported actions:
        click    — left-click the centre of the best-matching element.
        type     — click into a field then typewrite a value.
        wait_for — wait until target_text appears on screen (up to timeout).
    """

    def execute(
        self,
        action: dict[str, Any],
        elements: list[dict],
        capture_fn,                       # callable() → np.ndarray
    ) -> dict[str, Any]:
        """
        Execute one action with retry logic on no-change failures.

        Args:
            action:     Action dict from Planner.
            elements:   Current screen elements.
            capture_fn: Zero-arg callable that returns a fresh BGR frame.

        Returns:
            Result dict:
              success      (bool)
              screen_changed (bool)
              diff_ratio   (float)
              attempts     (int)
              error        (str | None)
              coordinates  (tuple[int,int] | None)
        """
        result: dict[str, Any] = {
            "action":         action,
            "success":        False,
            "screen_changed": False,
            "diff_ratio":     0.0,
            "attempts":       0,
            "error":          None,
            "coordinates":    None,
        }

        atype       = action.get("action", "").lower()
        target_text = action.get("target_text", "")
        value       = action.get("value", "")

        for attempt in range(1, config.MAX_ACTION_RETRIES + 1):
            result["attempts"] = attempt
            log.info("Attempt %d/%d | %s '%s'", attempt, config.MAX_ACTION_RETRIES, atype, target_text)

            try:
                before = capture_fn()

                if atype == "click":
                    coords = self._click(target_text, elements)
                elif atype == "type":
                    coords = self._type(target_text, value, elements)
                elif atype == "wait_for":
                    success = self._wait_for(target_text, capture_fn)
                    result["success"] = success
                    result["screen_changed"] = success
                    return result
                else:
                    raise ValueError(f"Unknown action type: {atype!r}")

                result["coordinates"] = coords

                # Wait for screen to settle
                time.sleep(config.STEP_DELAY_SEC)
                after = capture_fn()

                diff = pixel_diff_ratio(before, after)
                result["diff_ratio"]     = diff
                result["screen_changed"] = diff >= config.PIXEL_DIFF_THRESHOLD

                if result["screen_changed"]:
                    result["success"] = True
                    log.info("Action succeeded on attempt %d (diff=%.4f).", attempt, diff)
                    return result

                log.warning(
                    "No screen change after attempt %d (diff=%.4f) — retrying …",
                    attempt, diff,
                )

            except Exception as exc:
                log.error("Attempt %d failed: %s", attempt, exc)
                result["error"] = str(exc)

        log.error("All %d attempts exhausted for action '%s'.", config.MAX_ACTION_RETRIES, atype)
        return result

    # ── Action implementations ────────────────────────────────────────────────

    def _click(self, target_text: str, elements: list[dict]) -> tuple[int, int]:
        """
        Find the best-matching element and left-click its centre.

        Args:
            target_text: Label to look up.
            elements:    Current element list.

        Returns:
            (cx, cy) coordinates of the click.

        Raises:
            RuntimeError: If no matching element is found.
        """
        elem = self._find_element(target_text, elements)
        cx, cy = elem["cx"], elem["cy"]
        log.info("Clicking '%s' at (%d, %d).", target_text, cx, cy)
        pyautogui.click(cx, cy)
        return cx, cy

    def _type(
        self,
        target_text: str,
        value: str,
        elements: list[dict],
    ) -> tuple[int, int]:
        """
        Click a field identified by target_text, then type value.

        Args:
            target_text: Field label.
            value:       Text to type.
            elements:    Current element list.

        Returns:
            (cx, cy) of the field click.

        Raises:
            RuntimeError: If the field is not found.
        """
        elem = self._find_element(target_text, elements)
        cx, cy = elem["cx"], elem["cy"]
        log.info("Typing '%s' into '%s' at (%d, %d).", value, target_text, cx, cy)
        pyautogui.click(cx, cy)
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "a")   # Select-all before typing
        pyautogui.typewrite(value, interval=0.05)
        return cx, cy

    def _wait_for(
        self,
        target_text: str,
        capture_fn,
        timeout: float = 10.0,
        poll: float = 1.0,
    ) -> bool:
        """
        Poll the screen until target_text appears or timeout elapses.

        Args:
            target_text: Text to wait for.
            capture_fn:  Zero-arg callable returning a BGR frame.
            timeout:     Maximum seconds to wait.
            poll:        Polling interval in seconds.

        Returns:
            True if text appeared within timeout, False otherwise.
        """
        from vision.ocr_engine import OcrEngine  # late import avoids circular dep
        ocr    = OcrEngine()
        deadline = time.time() + timeout

        while time.time() < deadline:
            frame   = capture_fn()
            results = ocr.extract(frame)
            texts   = [r["text"] for r in results]
            match   = best_match(target_text, texts, threshold=80.0)
            if match:
                log.info("wait_for: '%s' appeared (match='%s').", target_text, match[0])
                return True
            log.debug("wait_for: '%s' not yet visible — polling …", target_text)
            time.sleep(poll)

        log.warning("wait_for: '%s' not found within %.1fs.", target_text, timeout)
        return False

    # ── Element resolution ────────────────────────────────────────────────────

    def _find_element(self, target_text: str, elements: list[dict]) -> dict:
        """
        Find the element whose label best fuzzy-matches target_text.

        Args:
            target_text: Search string.
            elements:    Element list from ElementDetector.

        Returns:
            Matching element dict.

        Raises:
            RuntimeError: If no element matches.
        """
        labels = [e.get("label", "") for e in elements]
        match  = best_match(target_text, labels)

        if match is None:
            raise RuntimeError(
                f"Element '{target_text}' not found on screen. "
                f"Visible labels: {labels[:10]}"
            )

        matched_label, score = match
        # Return the first element with that label
        for elem in elements:
            if elem.get("label", "") == matched_label:
                log.debug(
                    "Resolved '%s' → element label='%s' (score=%.1f) at (%d,%d).",
                    target_text, matched_label, score, elem["cx"], elem["cy"],
                )
                return elem

        raise RuntimeError(f"Label resolved but element not found: {matched_label!r}")
