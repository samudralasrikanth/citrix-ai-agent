"""
Region Setup — Citrix AI Vision Agent
======================================
Simple numbered menu — pick a window, optionally trim to sub-area, done.

Usage:
    python setup_region.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REGION_FILE = Path(__file__).parent / "memory" / "region.json"
REGION_FILE.parent.mkdir(parents=True, exist_ok=True)


# ── Window list via AppleScript ───────────────────────────────────────────────

def _get_windows() -> list[dict]:
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
        print("\n  No windows detected via AppleScript.")
        print("  (Grant Accessibility access: System Settings → Privacy → Accessibility → Terminal)\n")

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

    region = {"top": top, "left": left, "width": width, "height": height}

    # ── Save ──────────────────────────────────────────────────────────────────
    data = {"window_name": name, "region": region}
    REGION_FILE.write_text(json.dumps(data, indent=2))

    print()
    print("  ✅  Saved!")
    print(f"     window  : {name}")
    print(f"     top     : {top}")
    print(f"     left    : {left}")
    print(f"     width   : {width}")
    print(f"     height  : {height}")
    print()
    print("  ─────────────────────────────────────────────────────")
    print("  Next:")
    print("    ./run.sh list                     ← see playbooks")
    print("    ./run.sh new  my_test             ← create a test")
    print("    ./run.sh run  my_test --dry-run   ← preview steps")
    print("    ./run.sh run  my_test             ← run live")
    print()


if __name__ == "__main__":
    main()
