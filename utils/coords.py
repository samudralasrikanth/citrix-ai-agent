"""
Coordinate & DPI Transformer — Citrix AI Vision Agent
===================================================
Handles coordinate translation across platforms and scaling factors:
- Windows: DPI scaling (125%, 150%, etc.)
- macOS: Retina (2.0x) vs Standard (1.0x)
- Dynamic: Window-relative to Screen-absolute mapping.
"""
import platform
import mss
import pyautogui
from typing import Tuple

IS_WINDOWS = platform.system() == "Windows"
IS_MAC     = platform.system() == "Darwin"

def get_scaling_factors() -> Tuple[float, float]:
    """
    Determine the ratio between Screen pixels (pyautogui) and Native pixels (mss).
    """
    screen_w, screen_h = pyautogui.size()
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        native_w = monitor["width"]
        native_h = monitor["height"]
    
    return native_w / screen_w, native_h / screen_h

def to_native(x: int, y: int) -> Tuple[int, int]:
    """
    Convert Screen-space (GUI) coordinates to Native-space (Screenshot) pixels.
    Used during Recording.
    """
    sx, sy = get_scaling_factors()
    return int(x * sx), int(y * sy)

def to_screen(x: int, y: int) -> Tuple[int, int]:
    """
    Convert Native-space (Screenshot) pixels back to Screen-space (GUI) for Clicking.
    Used during Replay.
    """
    sx, sy = get_scaling_factors()
    return int(x / sx), int(y / sy)

def set_dpi_awareness():
    """Enable DPI awareness on Windows to prevent coordinate drift."""
    if IS_WINDOWS:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1) # PROCESS_SYSTEM_DPI_AWARE
        except Exception:
            pass
