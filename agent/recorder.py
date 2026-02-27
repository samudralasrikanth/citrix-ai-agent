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
import signal
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
from utils.coords import to_native, set_dpi_awareness

set_dpi_awareness()
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
        self._closing      = False
        
        # Load metadata if exists
        self.metadata = {
            "name": self.test_name.replace("_", " ").title(),
            "description": f"Recorded session — {time.strftime('%Y-%m-%d %H:%M')}"
        }

        # Register termination handler
        signal.signal(signal.SIGTERM, self._handle_terminate)
        signal.signal(signal.SIGINT,  self._handle_terminate)

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

        if self.yaml_path.exists():
            try:
                existing_data = yaml.safe_load(self.yaml_path.read_text(encoding="utf-8"))
                if existing_data:
                    if "steps" in existing_data:
                        self.steps = existing_data["steps"]
                        print(f"  {C.YELLOW}ℹ  Loaded {len(self.steps)} existing steps.{C.RESET}")
                    # Preserve existing name/desc
                    if "name" in existing_data:
                        self.metadata["name"] = existing_data["name"]
                    if "description" in existing_data:
                        self.metadata["description"] = existing_data["description"]
            except Exception as e:
                print(f"  {C.RED}⚠  Could not load existing playbook: {e}{C.RESET}")
        else:
            self._save_yaml()

        print(f"{C.GREEN}✓ Ready.{C.RESET}\n")
        self._print_help()

    # ── Region ──────────────────────────────────────────────────────────────────

    def _load_region(self, name: str) -> Dict[str, Any]:
        # 1. Try test-specific region first (scaffolded by UI)
        test_region_path = self.test_path / "region.json"
        if test_region_path.exists():
            data = json.loads(test_region_path.read_text())
            r = data.get("region", data)
            print(f"\n{C.CYAN}📍 Using suite-specific region:{C.RESET} {r['width']}x{r['height']}")
            return r

        # 2. Fallback to global memory dirs
        path = config.MEMORY_DIR / ("region.json" if not name else f"regions/{name}.json")
        if not path.exists():
            print(f"\n{C.RED}✗ No region.json found in {self.test_path} or {config.MEMORY_DIR}")
            print(f"  Run 'New Test Suite' in the dashboard first.{C.RESET}")
            sys.exit(1)
        
        data = json.loads(path.read_text())
        r    = data.get("region", data)
        # Copy for portability
        test_region_path.write_text(path.read_text())
        
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
        # --- FIX: Scale-aware coordinate capture ---
        gx, gy = pyautogui.position()
        nx, ny = to_native(gx, gy)
        
        r = self.region
        
        # Check against native region
        if not (r["left"] <= nx <= r["left"] + r["width"] and
                r["top"]  <= ny <= r["top"]  + r["height"]):
            print(f"\n  {C.YELLOW}⚠  Mouse is OUTSIDE the Citrix region "
                  f"({int(nx)},{int(ny)}).  Move into the window first.{C.RESET}")
            return None

        rx, ry = nx - r["left"], ny - r["top"]
        print(f"  {C.GRAY}🔍 Scanning element at native-relative ({int(rx)},{int(ry)}) …{C.RESET}",
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

    def _handle_terminate(self, signum, frame):
        """Ensure save on external stop signal."""
        if not self._closing:
            self._closing = True
            print(f"\n  {C.YELLOW}⏹  Termination signal received ({signum}). Saving and exiting…{C.RESET}")
            self._save_yaml()
            sys.exit(0)

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
            "name":        self.metadata["name"],
            "description": self.metadata["description"],
            "steps":       clean,
        }
        with open(self.yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, sort_keys=False, allow_unicode=True)

    # ── Main Loop ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """
        Non-blocking loop. Supports both CLI (input) and UI (stdin pipe).
        """
        print(f"  {C.GREEN}Recording active. Hover over any Citrix element → press ENTER.{C.RESET}\n", flush=True)
        print("[RECORDER_READY]", flush=True) # Signal to UI

        import select
        
        try:
            while not self._closing:
                # Use select for non-blocking stdin check (works on Unix, Mac)
                # For Windows fallback, we might need a different approach, but let's try this
                if IS_MAC or not IS_WINDOWS:
                    if sys.stdin in select.select([sys.stdin], [], [], 0.1)[0]:
                        raw = sys.stdin.readline().strip()
                        self._process_command(raw)
                    else:
                        time.sleep(0.05)
                else:
                    # Windows simple fallback (blocking) until we add a listener
                    raw = input(f"  {C.BOLD}[{len(self.steps)+1}]{C.RESET}{C.GRAY}>{C.RESET} ").strip()
                    self._process_command(raw)
                    
        except KeyboardInterrupt:
            pass
        finally:
            self._save_yaml()

    def _process_command(self, raw: str):
        # ── ENTER → Vision capture ────────────────────────────────────
        if not raw:
            result = self._capture_fingerprint()
            if result is None:
                return
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
                    f"{C.WHITE}{desc}{C.RESET}  {C.GRAY}{conf_str}{C.RESET}", flush=True)

        # ── q / quit ──────────────────────────────────────────────────
        elif raw.lower() in ("q", "quit", "exit"):
            self._closing = True

        # ── ls / list ─────────────────────────────────────────────────
        elif raw.lower() in ("ls", "list"):
            _step_table(self.steps)

        # ── u / undo ──────────────────────────────────────────────────
        elif raw.lower() in ("u", "undo"):
            self._undo()

        # ── s / screenshot ────────────────────────────────────────────
        elif raw.lower() in ("s", "screenshot"):
            self._add_step("screenshot", "", description="Capture screenshot")
            print(f"  {C.CYAN}📸 [{len(self.steps)}] screenshot added{C.RESET}", flush=True)

        # ── t <text> → type ───────────────────────────────────────────
        elif raw.lower().startswith("t "):
            value = raw[2:].strip()
            if value:
                self._add_step(
                    "type", "",
                    value=value,
                    description=f'Type "{value}"',
                )
                print(f"  {C.CYAN}⌨  [{len(self.steps)}] type → \"{value}\"{C.RESET}", flush=True)
            else:
                print(f"  {C.RED}Usage: t <text to type>{C.RESET}", flush=True)

        # ── w <text> → wait_for ───────────────────────────────────────
        elif raw.lower().startswith("w "):
            text = raw[2:].strip()
            if text:
                self._add_step(
                    "wait_for", text,
                    description=f'Wait for "{text}" on screen',
                )
                print(f"  {C.CYAN}⏳ [{len(self.steps)}] wait_for → \"{text}\"{C.RESET}", flush=True)
            else:
                print(f"  {C.RED}Usage: w <text to wait for>{C.RESET}", flush=True)

        # ── p <secs> → pause ──────────────────────────────────────────
        elif raw.lower().startswith("p"):
            parts = raw.split()
            secs  = parts[1] if len(parts) > 1 else "1"
            self._add_step("pause", secs, description=f"Pause {secs}s")
            print(f"  {C.CYAN}⏸  [{len(self.steps)}] pause → {secs}s{C.RESET}", flush=True)

        # ── h / help ──────────────────────────────────────────────────
        elif raw.lower() in ("h", "help", "?"):
            self._print_help()

        else:
            print(f"  {C.GRAY}Unknown: '{raw}'. Type 'h' for help.{C.RESET}", flush=True)

        except KeyboardInterrupt:
            pass
        finally:
            # Final explicit save before exit
            self._save_yaml()

        # ── Session summary ────────────────────────────────────────────────────
        elapsed = int(time.time() - self.session_start)
        print(f"\n\n{'─'*64}")
        _box([
            "  Session Complete",
            f"  Steps     : {len(self.steps)}",
            f"  Duration  : {elapsed//60}m {elapsed%60}s",
            f"  File      : {self.yaml_path.relative_to(ROOT)}",
        ], color=C.GREEN)
        _step_table(self.steps)
        print(f"{C.GREEN}  ✓ Saved to: {self.yaml_path}{C.RESET}")
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
