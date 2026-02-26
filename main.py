"""
Citrix AI Vision Agent — main entry point.

Fully offline, no LLM, no external APIs.
Run  ./run.sh setup  first to select your Citrix window area.

Usage:
    ./run.sh setup                                  ← FIRST: select region
    ./run.sh --goal "click Login"
    ./run.sh --goal "type admin in Username" --steps 5
    ./run.sh --goal "click Submit" --steps 10
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

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

DIVIDER      = "═" * 64
REGION_FILE  = Path(__file__).parent / "memory" / "region.json"


def _load_region() -> dict | None:
    """Load saved capture region from setup. Returns None if not set up yet."""
    if not REGION_FILE.exists():
        return None
    try:
        return json.loads(REGION_FILE.read_text())
    except Exception:
        return None


def run_agent(goal: str, max_steps: int = 5) -> None:
    """
    Execute the agent loop for a given goal.

    Args:
        goal:      Natural-language goal string.
        max_steps: Maximum agent steps to run.
    """
    # ── Load saved capture region ─────────────────────────────────────────────
    region = _load_region()
    if region is None:
        print("\n" + "─" * 60)
        print("  ⚠️  No capture region configured!")
        print()
        print("  Run setup first to select your Citrix window area:")
        print("      ./run.sh setup")
        print("─" * 60 + "\n")
        sys.exit(1)

    log.info(DIVIDER)
    log.info("Agent starting  goal='%s'  max_steps=%d", goal, max_steps)
    log.info("Capture region  top=%d  left=%d  width=%d  height=%d",
             region["top"], region["left"], region["width"], region["height"])
    log.info(DIVIDER)

    capturer  = ScreenCapture()
    ocr       = OcrEngine()
    planner   = Planner()
    # Initialize executor with region and a default 'main_goal' context_id
    executor  = ActionExecutor(region=region, context_id="main_goal")
    rewarder  = RewardEngine()
    memory    = MemoryManager()

    total_reward = 0

    for step in range(1, max_steps + 1):
        log.info("─── Step %d / %d ─────────────────────────────────────", step, max_steps)

        # ── 1. Capture and Vision ────────────────────────────────────────────
        frame, _ = capturer.capture_and_save(region=region)
        ocr_results = ocr.extract(frame)
        
        # Build state — still using visible_texts for planner
        state = build_screen_state(frame, ocr_results, [], step=step)

        log.info("Screen state:\n%s", state_to_json({
            "screen_id":     state["screen_id"],
            "visible_texts": state["visible_texts"][:10],
            "element_count": len(ocr_results),
        }))

        # ── 2. Plan ──────────────────────────────────────────────────────────
        actions = planner.plan(goal, state)
        if not actions:
            log.warning("Planner returned empty action list — skipping step.")
            continue

        # ── 3. Execute → reward → memory per action ────────────────────────
        for action in actions:
            log.info("Action: %s", action)

            # Reliability chain is now handled inside executor.execute
            exec_result = executor.execute(
                action=action,
                ocr_results=ocr_results,
                frame=frame,
                capture_fn=lambda: capturer.capture(region=region)
            )

            # Re-capture for new state calculation
            new_frame, _   = capturer.capture_and_save(region=region)
            new_ocr        = ocr.extract(new_frame)
            new_state      = build_screen_state(new_frame, new_ocr, [], step=step)

            # Reward
            reward        = rewarder.score(action, exec_result, state, new_state)
            total_reward += reward
            log.info("Reward: %+d  (running total: %+d)", reward, total_reward)

            # Memory persistence
            target_text = action.get("target", action.get("target_text", ""))
            memory.record(
                screen_id   = state["screen_id"],
                target_text = target_text,
                success     = exec_result["success"],
                reward      = reward,
                coordinates = exec_result.get("target_center"),
            )

            # Advance baseline
            frame, state = new_frame, new_state

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
