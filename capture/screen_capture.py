"""
Screen capture module using MSS.
Returns NumPy BGR arrays; optionally persists timestamped screenshots.
"""

from __future__ import annotations

import time
from pathlib import Path

import mss
import numpy as np

import config
from utils.image_utils import save_image
from utils.logger import get_logger

log = get_logger(__name__)


class ScreenCapture:
    """Wraps MSS for full-screen or region capture, returning BGR NumPy arrays."""

    def __init__(self) -> None:
        self._sct = mss.mss()

    # ── Public API ────────────────────────────────────────────────────────────

    def capture(self, region: dict | None = None) -> np.ndarray:
        """
        Capture the screen or a sub-region.

        Args:
            region: Optional dict {top, left, width, height}.
                    Falls back to config.CAPTURE_REGION → full monitor.

        Returns:
            BGR NumPy array.
        """
        target = region or config.CAPTURE_REGION
        monitor = (
            self._sct.monitors[config.CAPTURE_MONITOR_INDEX]
            if target is None
            else target
        )
        raw   = self._sct.grab(monitor)
        frame = np.array(raw)[:, :, :3]   # BGRA → BGR
        log.debug("Captured %dx%d frame.", frame.shape[1], frame.shape[0])
        return frame

    def capture_and_save(self, region: dict | None = None) -> tuple[np.ndarray, str]:
        """
        Capture and persist with a timestamp filename.

        Args:
            region: Optional capture region.

        Returns:
            (BGR array, absolute path to saved PNG).
        """
        frame = self.capture(region)
        ts    = time.strftime("%Y%m%d_%H%M%S")
        path  = config.SCREENSHOTS_DIR / f"screenshot_{ts}.png"
        save_image(frame, str(path))
        log.info("Screenshot → %s", path)
        return frame, str(path)

    def close(self) -> None:
        """Release the MSS context."""
        self._sct.close()

    def __enter__(self) -> "ScreenCapture":
        return self

    def __exit__(self, *_) -> None:
        self.close()
