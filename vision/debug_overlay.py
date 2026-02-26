"""
╔══════════════════════════════════════════════════════════════════╗
║  Debug Overlay — Bounding Box Visualiser                        ║
║  When debug mode is enabled, draws and saves annotated frames   ║
║  showing all OCR boxes, fuzzy scores, and the matched element.  ║
╚══════════════════════════════════════════════════════════════════╝

Output: screenshots/debug_<action>_<timestamp>.png

Color coding:
    Green  (thick) — matched element
    Cyan             — short-target candidate (score shown)
    Orange           — general OCR result
    Red              — below-threshold result
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

import config

log = logging.getLogger("DebugOverlay")

# ── Colour palette (BGR) ──────────────────────────────────────────────────────
_CLR_MATCH    = (0,  220,  80)   # green  — winning match
_CLR_CAND     = (0,  200, 200)   # cyan   — candidate
_CLR_GENERAL  = (0,  165, 255)   # orange — ordinary OCR box
_CLR_REJECT   = (60,  60, 180)   # muted  — below threshold
_CLR_TEXT_BG  = (0,    0,   0)   # black  — label background


def draw_debug_overlay(
    frame: np.ndarray,
    ocr_results: List[Dict[str, Any]],
    target: str,
    matched_idx: Optional[int],
    scores: Optional[List[float]] = None,
    action_name: str = "click",
) -> np.ndarray:
    """
    Render an annotated debug image.

    Args:
        frame:        BGR image (already cropped to automation region).
        ocr_results:  List of OCR dicts with 'text', 'box', 'confidence'.
        target:       The label we were searching for.
        matched_idx:  Index into ocr_results of the winning match (or None).
        scores:       Fuzzy scores parallel to ocr_results (optional).
        action_name:  Used in the filename.

    Returns:
        Annotated BGR image (useful for tests / inspection).
    """
    canvas = frame.copy()
    h, w   = canvas.shape[:2]
    is_short = len(target.strip()) <= 3

    for i, res in enumerate(ocr_results):
        box   = res["box"]  # [x1, y1, x2, y2]
        x1, y1, x2, y2 = box
        text  = res.get("text", "")
        conf  = res.get("confidence", 0.0)
        score = scores[i] if scores and i < len(scores) else None

        # Choose colour
        if i == matched_idx:
            color     = _CLR_MATCH
            thickness = 3
        elif is_short and score is not None and score >= 50:
            color     = _CLR_CAND
            thickness = 2
        elif score is not None and score is not None and score >= config.FUZZY_MATCH_THRESHOLD:
            color     = _CLR_GENERAL
            thickness = 1
        else:
            color     = _CLR_REJECT
            thickness = 1

        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness)

        # Label: text + conf + fuzzy score
        label_parts = [f"{text[:18]}  conf={conf:.2f}"]
        if score is not None:
            label_parts.append(f"fz={score:.0f}")
        label = "  ".join(label_parts)

        ty = max(y1 - 5, 14)
        (tw, tlh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
        cv2.rectangle(canvas, (x1, ty - tlh - 3), (x1 + tw + 4, ty + 2), _CLR_TEXT_BG, -1)
        cv2.putText(canvas, label, (x1 + 2, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1,
                    cv2.LINE_AA)

    # Banner at top
    banner = (f"TARGET: '{target}'  |  {'SHORT' if is_short else 'NORMAL'} mode  |  "
              f"match={'#'+str(matched_idx) if matched_idx is not None else 'NONE'}  |  "
              f"action={action_name}")
    cv2.rectangle(canvas, (0, 0), (w, 22), (20, 20, 20), -1)
    cv2.putText(canvas, banner, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (220, 220, 220), 1, cv2.LINE_AA)

    return canvas


def save_debug_frame(
    frame: np.ndarray,
    ocr_results: List[Dict[str, Any]],
    target: str,
    matched_idx: Optional[int],
    scores: Optional[List[float]] = None,
    action_name: str = "click",
) -> Optional[Path]:
    """
    Draw and persist a debug overlay image.
    No-ops unless config.SAVE_DEBUG_FRAMES is True.

    Returns the saved path (or None).
    """
    if not config.SAVE_DEBUG_FRAMES:
        return None

    annotated = draw_debug_overlay(frame, ocr_results, target, matched_idx, scores, action_name)
    ts         = int(time.time())
    fname      = f"debug_{action_name}_{target[:12].replace(' ','_')}_{ts}.png"
    path       = config.SCREENSHOTS_DIR / fname
    cv2.imwrite(str(path), annotated)
    log.debug("Debug overlay saved → %s", path.name)
    return path
