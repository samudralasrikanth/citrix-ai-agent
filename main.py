"""
Citrix AI Vision Agent — main entry point.

Fully offline, no LLM, no external APIs.
Demonstrates the complete sense → plan → act → reward → remember loop.

Usage (Windows PowerShell, inside citrix_ai_agent/):
    python main.py
    python main.py --goal "click Submit" --steps 5
    python main.py --goal "type 123 in Policy Number" --steps 3
    python main.py --goal "Submit the form" --steps 10   # free-text fuzzy mode
"""

from __future__ import annotations

import argparse
import sys
import time

import config
from capture.screen_capture import ScreenCapture
from vision.ocr_engine import OcrEngine
from vision.element_detector import ElementDetector
from vision.screen_state import build_screen_state, state_to_json
from agent.planner import Planner
from agent.action_executor import ActionExecutor
from agent.reward_engine import RewardEngine
from agent.memory_manager import MemoryManager
from utils.logger import get_logger

log = get_logger(__name__)

DIVIDER = "═" * 64


def run_agent(goal: str, max_steps: int = 5) -> None:
    """
    Execute the agent loop for a given goal.

    Loop per step:
        1. Capture screen + OCR + element detection → screen state.
        2. Planner (fuzzy heuristic) emits action list.
        3. Executor runs each action with retry + pixel-diff validation.
        4. Re-capture → new screen state.
        5. Reward engine scores the transition.
        6. Memory manager persists outcome + coordinates.
        7. Repeat until max_steps exhausted.

    Args:
        goal:      Natural-language goal string.
        max_steps: Maximum agent steps to run.
    """
    log.info(DIVIDER)
    log.info("Agent starting  goal='%s'  max_steps=%d", goal, max_steps)
    log.info(DIVIDER)

    capturer  = ScreenCapture()
    ocr       = OcrEngine()
    detector  = ElementDetector()
    planner   = Planner()
    executor  = ActionExecutor()
    rewarder  = RewardEngine()
    memory    = MemoryManager()

    total_reward = 0

    for step in range(1, max_steps + 1):
        log.info("─── Step %d / %d ─────────────────────────────────────", step, max_steps)

        # ── 1. Capture + perception ──────────────────────────────────────────
        frame, ss_path = capturer.capture_and_save()
        ocr_results    = ocr.extract(frame)
        elements       = detector.detect_contours(frame)
        elements       = detector.merge_with_ocr(elements, ocr_results)
        state          = build_screen_state(frame, ocr_results, elements, step=step)

        log.info("Screen state:\n%s", state_to_json({
            "screen_id":     state["screen_id"],
            "visible_texts": state["visible_texts"][:10],   # first 10 only
            "element_count": len(state["elements"]),
        }))

        # ── 2. Plan ──────────────────────────────────────────────────────────
        actions = planner.plan(goal, state)
        if not actions:
            log.warning("Planner returned empty action list — skipping step.")
            continue

        # ── 3–6. Execute → reward → memory per action ────────────────────────
        for action in actions:
            log.info("Action: %s", action)

            # Pass a fresh-capture lambda so the executor can re-observe
            exec_result = executor.execute(
                action=action,
                elements=elements,
                capture_fn=capturer.capture,
            )

            # Re-capture for new state
            new_frame, _   = capturer.capture_and_save()
            new_ocr        = ocr.extract(new_frame)
            new_elements   = detector.detect_contours(new_frame)
            new_elements   = detector.merge_with_ocr(new_elements, new_ocr)
            new_state      = build_screen_state(new_frame, new_ocr, new_elements, step=step)

            # Reward
            reward        = rewarder.score(action, exec_result, state, new_state)
            total_reward += reward
            log.info("Reward: %+d  (running total: %+d)", reward, total_reward)

            # Memory
            coords = exec_result.get("coordinates")
            memory.record(
                screen_id   = state["screen_id"],
                target_text = action.get("target_text", ""),
                success     = exec_result["success"],
                reward      = reward,
                coordinates = tuple(coords) if coords else None,
            )

            # Advance baseline
            frame, state = new_frame, new_state
            elements     = new_elements

        log.info("Step %d complete.", step)

    log.info(DIVIDER)
    log.info("Agent finished.  Total reward: %+d", total_reward)
    log.info(memory.summary())
    log.info(DIVIDER)
    capturer.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Citrix AI Vision Agent — fully local, no LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py\n"
            "  python main.py --goal 'click Submit' --steps 5\n"
            "  python main.py --goal 'type POL-001 in Policy Number' --steps 3\n"
            "  python main.py --goal 'Submit the form' --steps 10\n"
        ),
    )
    parser.add_argument(
        "--goal",
        default="click Submit",
        help="Natural-language goal.  Prefix with 'click', 'type … in …', or 'wait_for'.",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=3,
        help="Maximum agent steps (default: 3).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    try:
        run_agent(goal=args.goal, max_steps=args.steps)
    except KeyboardInterrupt:
        log.info("Interrupted by user — exiting cleanly.")
        sys.exit(0)
