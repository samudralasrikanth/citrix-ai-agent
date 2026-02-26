"""
╔══════════════════════════════════════════════════════════════════════╗
║   Citrix AI Vision Agent — Enterprise Interactive Recorder          ║
║                                                                      ║
║   Semantic recording (Tosca-style):                                  ║
║   • Each click → element type + label + context  (NOT coordinates)  ║
║   • Playbooks replay correctly even if window moves or resizes        ║
║   • Multi-action: click, type, wait_for, screenshot, pause, undo     ║
╚══════════════════════════════════════════════════════════════════════╝

CLI:   python agent/recorder.py <test_name> [region_name]
Shell: ./run.sh record <test_name>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))

import pyautogui
import yaml
import config
from capture.screen_capture import ScreenCapture
from vision.ocr_engine import OcrEngine
from vision.element_fingerprinter import ElementFingerprinter
from utils.logger import get_logger

log = get_logger("Recorder")


# ── ANSI colour helpers ────────────────────────────────────────────────────────
class C:
    RESET   = "\033[0m";  BOLD  = "\033[1m"
    GREEN   = "\033[92m"; YELLOW= "\033[93m"; CYAN= "\033[96m"
    RED     = "\033[91m"; GRAY  = "\033[90m"; WHITE="\033[97m"
    MAGENTA = "\033[95m"

def _box(lines: List[str], color: str = C.CYAN, width: int = 64) -> None:
    bar = "─" * (width - 2)
    print(f"{color}┌{bar}┐{C.RESET}")
    for line in lines:
        padded = f" {line:<{width - 4}} "
        print(f"{color}│{C.WHITE}{padded}{color}│{C.RESET}")
    print(f"{color}└{bar}┘{C.RESET}")

def _step_table(steps: List[Dict[str, Any]]) -> None:
    if not steps:
        print(f"  {C.GRAY}(no steps recorded yet){C.RESET}\n")
        return
    print(f"\n{C.BOLD}{C.GRAY}  {'#':<4}  {'ACTION':<14}  {'TARGET / LABEL':<36}  {'TYPE':<14}  {'CONTEXT'}{C.RESET}")
    print(f"{C.GRAY}  {'─'*4}  {'─'*14}  {'─'*36}  {'─'*14}  {'─'*20}{C.RESET}")
    for i, s in enumerate(steps, 1):
        fp   = s.get("_fingerprint", {})
        typ  = fp.get("type", "")
        ctx  = fp.get("context", "")[:20]
        tgt  = s.get("target", "")[:36]
        act  = C.CYAN if s["action"] == "click" else C.YELLOW
        print(f"  {C.GRAY}{i:<4}{C.RESET}  {act}{s['action']:<14}{C.RESET}  "
              f"{C.WHITE}{tgt:<36}{C.RESET}  {C.MAGENTA}{typ:<14}{C.RESET}  {C.GRAY}{ctx}{C.RESET}")
    print()


class PlaybookRecorder:
    """
    Enterprise vision recorder — semantic, position-independent, Tosca-style.
    """

    def __init__(self, test_name: str, region_name: str = ""):
        self.test_name     = test_name
        self.test_path     = config.TESTS_DIR / test_name
        self.test_path.mkdir(parents=True, exist_ok=True)
        self.yaml_path     = self.test_path / "playbook.yaml"
        self.steps: List[Dict[str, Any]] = []
        self.session_start = time.time()

        _box([
            "  Citrix AI Vision Agent — Enterprise Recorder",
            f"  Suite     : {test_name}",
            f"  Output    : tests/{test_name}/playbook.yaml",
            "  Mode      : Semantic (Tosca-style, label-based)",
        ], color=C.GREEN)

        print(f"\n{C.BOLD}⚙  Initialising Vision Engine …{C.RESET}", flush=True)
        self.capturer     = ScreenCapture()
        self.ocr          = OcrEngine()
        self.fingerprinter= ElementFingerprinter()
        self.region       = self._load_region(region_name)

        # Copy region file to test folder for portability
        src = config.MEMORY_DIR / ("region.json" if not region_name
                                    else f"regions/{region_name}.json")
        (self.test_path / "region.json").write_text(src.read_text())

        if not self.yaml_path.exists():
            self._save_yaml()

        print(f"{C.GREEN}✓ Ready.{C.RESET}\n")
        self._print_help()

    # ── Region ──────────────────────────────────────────────────────────────────

    def _load_region(self, name: str) -> Dict[str, Any]:
        path = config.MEMORY_DIR / ("region.json" if not name else f"regions/{name}.json")
        if not path.exists():
            print(f"\n{C.RED}✗ No region found at {path}")
            print(f"  Run './run.sh setup' first to capture your window.{C.RESET}")
            sys.exit(1)
        data = json.loads(path.read_text())
        r    = data.get("region", data)
        print(f"\n{C.CYAN}📍 Target Region:{C.RESET}  {r['width']}×{r['height']}  "
              f"@ ({r['left']},{r['top']})")
        return r

    # ── Help ─────────────────────────────────────────────────────────────────────

    def _print_help(self) -> None:
        cmds = [
            ("ENTER",        "Capture element under mouse (semantic, label-based)"),
            ("t <text>",     "Type text into focused field  (e.g. t mypassword)"),
            ("w <text>",     "Wait for text to appear on screen"),
            ("s",            "Screenshot step"),
            ("p <secs>",     "Pause step (e.g. p 2)"),
            ("u",            "Undo last step"),
            ("ls",           "Show recorded steps table"),
            ("h",            "Show this help"),
            ("q / Ctrl+C",   "Save and finish session"),
        ]
        print(f"{C.BOLD}{'─'*64}\n  Commands{C.RESET}")
        print(f"{'─'*64}")
        for k, v in cmds:
            print(f"  {C.CYAN}{k:<14}{C.RESET} {v}")
        print(f"{'─'*64}\n")

    # ── Vision Capture ─────────────────────────────────────────────────────────

    def _capture_fingerprint(self) -> Optional[Dict[str, Any]]:
        """
        Take a screenshot, run OCR, return a full ElementFingerprint dict.
        Validates that the mouse is within the automation region.
        """
        x, y = pyautogui.position()
        r    = self.region

        if not (r["left"] <= x <= r["left"] + r["width"] and
                r["top"]  <= y <= r["top"]  + r["height"]):
            print(f"\n  {C.YELLOW}⚠  Mouse is OUTSIDE the Citrix region "
                  f"({int(x)},{int(y)}).  Move into the window first.{C.RESET}")
            return None

        rx, ry = x - r["left"], y - r["top"]
        print(f"  {C.GRAY}🔍 Scanning element at region-relative ({int(rx)},{int(ry)}) …{C.RESET}",
              end="\r", flush=True)

        frame       = self.capturer.capture(region=r)
        ocr_results = self.ocr.extract(frame)

        fp  = self.fingerprinter.fingerprint_at(frame, ocr_results, rx, ry)
        return fp.to_dict(), fp.to_playbook_target()

    # ── Step Management ────────────────────────────────────────────────────────

    def _add_step(
        self,
        action:      str,
        target:      str,
        value:       str        = "",
        description: str        = "",
        fingerprint: Optional[Dict] = None,
    ) -> None:
        step: Dict[str, Any] = {
            "action":       action,
            "target":       target,
            "_time":        time.strftime("%H:%M:%S"),
            "_fingerprint": fingerprint or {},
        }
        if value:
            step["value"] = value
        if description:
            step["description"] = description
        self.steps.append(step)
        self._save_yaml()

    def _undo(self) -> None:
        if self.steps:
            r = self.steps.pop()
            self._save_yaml()
            print(f"  {C.YELLOW}↩  Undone: {r['action']} → {r['target']}{C.RESET}")
        else:
            print(f"  {C.GRAY}Nothing to undo.{C.RESET}")

    # ── Persistence ────────────────────────────────────────────────────────────

    def _save_yaml(self) -> None:
        # Strip runtime metadata before writing
        clean = []
        for s in self.steps:
            cs = {k: v for k, v in s.items() if not k.startswith("_")}
            # Attach fingerprint as YAML comment-friendly info block
            fp = s.get("_fingerprint", {})
            if fp:
                cs["fingerprint"] = {
                    "type":    fp.get("type", ""),
                    "context": fp.get("context", ""),
                }
            clean.append(cs)

        data = {
            "name":        self.test_name.replace("_", " ").title(),
            "description": f"Recorded session — {time.strftime('%Y-%m-%d %H:%M')}",
            "steps":       clean,
        }
        with open(self.yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, sort_keys=False, allow_unicode=True)

    # ── Main Loop ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        print(f"  {C.GREEN}Recording active. Hover over any Citrix element → press ENTER.{C.RESET}\n")

        try:
            while True:
                try:
                    raw = input(
                        f"  {C.BOLD}[{len(self.steps)+1}]{C.RESET}{C.GRAY}>{C.RESET} "
                    ).strip()
                except (EOFError, KeyboardInterrupt):
                    break

                # ── ENTER → Vision capture ────────────────────────────────────
                if not raw:
                    result = self._capture_fingerprint()
                    if result is None:
                        continue
                    fp_dict, playbook_target = result
                    label    = fp_dict.get("label", "")
                    etype    = fp_dict.get("type",  "element")
                    context  = fp_dict.get("context", "")
                    conf     = fp_dict.get("confidence", 0)

                    if label:
                        desc = f'Click "{label}" ({etype})'
                        if context:
                            desc += f' in "{context}"'
                        color = C.GREEN
                        quality = "✓ Semantic match"
                    elif context:
                        desc  = f'Click {etype} near "{context}"'
                        color = C.YELLOW
                        quality = "⚠ Contextual match"
                    else:
                        desc  = f'Click {etype} at relative ({fp_dict["rel_pos"]["x"]:.2f},{fp_dict["rel_pos"]["y"]:.2f})'
                        color = C.RED
                        quality = "✗ Positional fallback"

                    self._add_step(
                        action="click",
                        target=playbook_target,
                        description=desc,
                        fingerprint=fp_dict,
                    )
                    conf_str = f"{int(conf*100)}%" if conf else ""
                    print(f"  {color}{quality}{C.RESET}  {C.BOLD}[{len(self.steps)}]{C.RESET}  "
                          f"{C.WHITE}{desc}{C.RESET}  {C.GRAY}{conf_str}{C.RESET}")

                # ── q / quit ──────────────────────────────────────────────────
                elif raw.lower() in ("q", "quit", "exit"):
                    break

                # ── ls / list ─────────────────────────────────────────────────
                elif raw.lower() in ("ls", "list"):
                    _step_table(self.steps)

                # ── u / undo ──────────────────────────────────────────────────
                elif raw.lower() in ("u", "undo"):
                    self._undo()

                # ── s / screenshot ────────────────────────────────────────────
                elif raw.lower() in ("s", "screenshot"):
                    self._add_step("screenshot", "", description="Capture screenshot")
                    print(f"  {C.CYAN}📸 [{len(self.steps)}] screenshot added{C.RESET}")

                # ── t <text> → type ───────────────────────────────────────────
                elif raw.lower().startswith("t "):
                    value = raw[2:].strip()
                    if value:
                        self._add_step(
                            "type", "",
                            value=value,
                            description=f'Type "{value}"',
                        )
                        print(f"  {C.CYAN}⌨  [{len(self.steps)}] type → \"{value}\"{C.RESET}")
                    else:
                        print(f"  {C.RED}Usage: t <text to type>{C.RESET}")

                # ── w <text> → wait_for ───────────────────────────────────────
                elif raw.lower().startswith("w "):
                    text = raw[2:].strip()
                    if text:
                        self._add_step(
                            "wait_for", text,
                            description=f'Wait for "{text}" on screen',
                        )
                        print(f"  {C.CYAN}⏳ [{len(self.steps)}] wait_for → \"{text}\"{C.RESET}")
                    else:
                        print(f"  {C.RED}Usage: w <text to wait for>{C.RESET}")

                # ── p <secs> → pause ──────────────────────────────────────────
                elif raw.lower().startswith("p"):
                    parts = raw.split()
                    secs  = parts[1] if len(parts) > 1 else "1"
                    self._add_step("pause", secs, description=f"Pause {secs}s")
                    print(f"  {C.CYAN}⏸  [{len(self.steps)}] pause → {secs}s{C.RESET}")

                # ── h / help ──────────────────────────────────────────────────
                elif raw.lower() in ("h", "help", "?"):
                    self._print_help()

                else:
                    print(f"  {C.GRAY}Unknown: '{raw}'. Type 'h' for help.{C.RESET}")

        except KeyboardInterrupt:
            pass

        # ── Session summary ────────────────────────────────────────────────────
        elapsed = int(time.time() - self.session_start)
        print(f"\n\n{'─'*64}")
        _box([
            "  Session Complete",
            f"  Steps     : {len(self.steps)}",
            f"  Duration  : {elapsed//60}m {elapsed%60}s",
            f"  File      : tests/{self.test_name}/playbook.yaml",
        ], color=C.GREEN)
        _step_table(self.steps)
        print(f"{C.GREEN}  ✓ Run it:  ./run.sh run {self.test_name}{C.RESET}\n")
        sys.exit(0)


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"\n  {C.RED}Usage: python agent/recorder.py <test_name> [region_name]{C.RESET}\n")
        sys.exit(1)

    PlaybookRecorder(
        test_name   = sys.argv[1],
        region_name = sys.argv[2] if len(sys.argv) > 2 else "",
    ).start()
