"""
Region Setup — Citrix AI Vision Agent
======================================
Simple numbered menu — pick a window, optionally trim to sub-area, done.
Works on macOS (AppleScript) and Windows (win32 API).

Usage:
    python setup_region.py          # or: python run.py setup
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path

MEMORY_DIR  = Path(__file__).parent / "memory"
REGIONS_DIR = MEMORY_DIR / "regions"
REGION_FILE = MEMORY_DIR / "region.json"   # default (backward compat)
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
REGIONS_DIR.mkdir(parents=True, exist_ok=True)


IS_WINDOWS = platform.system() == "Windows"
IS_MAC     = platform.system() == "Darwin"


# ── Window list (cross-platform) ─────────────────────────────────────────────

def _get_windows_mac() -> list[dict]:
    """List visible windows via AppleScript (macOS)."""
    script = """
    set output to ""
    tell application "System Events"
        set procs to every process whose visible is true
        repeat with p in procs
            try
                set wins to every window of p
                repeat with w in wins
                    try
                        set pos to position of w
                        set sz  to size of w
                        set x   to item 1 of pos
                        set y   to item 2 of pos
                        set wd  to item 1 of sz
                        set ht  to item 2 of sz
                        if wd > 80 and ht > 80 then
                            set output to output & (name of p) & "|" & x & "|" & y & "|" & wd & "|" & ht & "\\n"
                        end if
                    end try
                end repeat
            end try
        end repeat
    end tell
    return output
    """
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=8)
        wins = []
        seen = set()
        for line in r.stdout.strip().splitlines():
            parts = line.strip().split("|")
            if len(parts) == 5:
                name, x, y, w, h = parts
                key = f"{name}|{x}|{y}"
                if key not in seen:
                    seen.add(key)
                    wins.append({"name": name.strip(),
                                 "left": int(x), "top": int(y),
                                 "width": int(w), "height": int(h)})
        return wins
    except Exception:
        return []


def _get_windows_win() -> list[dict]:
    """List visible windows via Windows ctypes (no extra deps needed)."""
    import ctypes
    import ctypes.wintypes

    EnumWindows        = ctypes.windll.user32.EnumWindows
    GetWindowText      = ctypes.windll.user32.GetWindowTextW
    GetWindowTextLen   = ctypes.windll.user32.GetWindowTextLengthW
    IsWindowVisible    = ctypes.windll.user32.IsWindowVisible
    GetWindowRect      = ctypes.windll.user32.GetWindowRect

    wins = []

    def _cb(hwnd, _):
        if not IsWindowVisible(hwnd):
            return True
        length = GetWindowTextLen(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        GetWindowText(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title:
            return True
        rect = ctypes.wintypes.RECT()
        GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right  - rect.left
        h = rect.bottom - rect.top
        if w > 80 and h > 80:
            wins.append({"name": title, "left": rect.left, "top": rect.top,
                         "width": w, "height": h})
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    EnumWindows(WNDENUMPROC(_cb), 0)
    return wins


def _get_windows() -> list[dict]:
    """Return visible windows using the right API for the current OS."""
    try:
        if IS_WINDOWS:
            return _get_windows_win()
        elif IS_MAC:
            return _get_windows_mac()
        return []
    except Exception:
        return []



# ── Input helpers ─────────────────────────────────────────────────────────────

def _ask_int(prompt: str, default: int) -> int:
    try:
        raw = input(f"  {prompt} [{default}]: ").strip()
        return int(raw) if raw else default
    except (ValueError, EOFError):
        return default


def _ask(prompt: str) -> str:
    try:
        return input(f"  {prompt}: ").strip()
    except EOFError:
        return ""


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print("┌──────────────────────────────────────────────────────┐")
    print("│   Citrix AI Vision Agent — Select Capture Region     │")
    print("└──────────────────────────────────────────────────────┘")

    # ── List windows ──────────────────────────────────────────────────────────
    wins = _get_windows()

    if wins:
        print(f"\n  Detected {len(wins)} open window(s):\n")
        for i, w in enumerate(wins, 1):
            print(f"    [{i:2d}]  {w['name']:<38} {w['width']}×{w['height']}")
        print(f"    [ 0]  Enter coordinates manually\n")
    else:
        if IS_MAC:
            print("\n  No windows detected.")
            print("  Tip: System Settings → Privacy & Security → Accessibility → add Terminal\n")
        else:
            print("\n  No windows detected — enter coordinates manually.\n")

    # ── Pick window ───────────────────────────────────────────────────────────
    base: dict | None = None

    if wins:
        while True:
            try:
                n = int(_ask("Pick window number (0 = manual)"))
                if n == 0:
                    break
                if 1 <= n <= len(wins):
                    base = wins[n - 1]
                    break
            except ValueError:
                pass
            print("  ⚠️  Enter a number from the list.")

    # ── Manual entry if no window selected ───────────────────────────────────
    if base is None:
        print("\n  Enter region coordinates (pixels from top-left of screen):\n")
        left   = _ask_int("Left (x)", 0)
        top    = _ask_int("Top  (y)", 0)
        width  = _ask_int("Width",    800)
        height = _ask_int("Height",   600)
        base   = {"name": "manual", "left": left, "top": top,
                  "width": width, "height": height}

    name   = base["name"]
    left   = base["left"]
    top    = base["top"]
    width  = base["width"]
    height = base["height"]

    print(f"\n  Selected: {name}  ({width}×{height}  @ {left},{top})\n")

    # ── Optional: crop to sub-region inside the window ────────────────────────
    refine = _ask("Capture full window? [Y/n]").lower()

    if refine == "n":
        print("\n  Enter the sub-region offsets within the window:\n")
        off_x  = _ask_int("Left offset inside window", 0)
        off_y  = _ask_int("Top  offset inside window", 0)
        width  = _ask_int("Width  of capture area",    width)
        height = _ask_int("Height of capture area",    height)
        left   = left + off_x
        top    = top  + off_y

    region  = {"top": top, "left": left, "width": width, "height": height}
    win_name = name
    data    = {"window_name": win_name, "region": region}

    # ── Save ──────────────────────────────────────────────────────────────────
    # Accept optional region name from command-line: python run.py setup <name>
    region_name = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    region_slug = region_name.lower().replace(" ", "_") if region_name else ""

    # Always write default region.json (so playbooks work without specifying a name)
    REGION_FILE.write_text(json.dumps(data, indent=2))

    # Also save as named region if a name was given
    if region_slug:
        named_path = REGIONS_DIR / f"{region_slug}.json"
        named_path.write_text(json.dumps(data, indent=2))
        saved_as = f"memory/regions/{region_slug}.json  +  memory/region.json"
    else:
        saved_as = "memory/region.json  (default)"

    print()
    print("  ✅  Saved!")
    print(f"     file    : {saved_as}")
    print(f"     window  : {win_name}")
    print(f"     top={top}, left={left}, width={width}, height={height}")
    print()
    launcher = "run" if IS_WINDOWS else "python run.py"
    print(f"  Next:")
    print(f"    {launcher} regions              ← see all saved regions")
    print(f"    {launcher} new  my_test         ← create a new test")
    print(f"    {launcher} run  my_test         ← run it live")
    print()


if __name__ == "__main__":
    main()
