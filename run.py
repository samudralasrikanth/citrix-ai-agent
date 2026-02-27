"""
Citrix AI Vision Agent — Cross-platform launcher
=================================================
Works on Mac, Linux, and Windows.

Usage:
    python run.py setup                           <- Select window/region (saves with a name)
    python run.py setup  login_screen             <- Save with a specific name
    python run.py regions                         <- List all saved regions
    python run.py new    <name>                   <- Create a new playbook
    python run.py run    <name>                   <- Run a playbook
    python run.py run    <name> --dry-run         <- Preview steps only
    python run.py list                            <- List all playbooks
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT        = Path(__file__).parent
VENV_DIR    = ROOT / "venv"
PLAYBOOKS   = ROOT / "playbooks"
SUITES_DIR  = ROOT / "suites"
MEMORY_DIR  = ROOT / "memory"
REGIONS_DIR = MEMORY_DIR / "regions"
REGION_FILE = MEMORY_DIR / "region.json"   # legacy default region

IS_WINDOWS  = platform.system() == "Windows"

PLAYBOOK_TEMPLATE = """\
# ─────────────────────────────────────────────────────────────────
# Playbook: {name}
# Run:  python run.py run {slug}
# ─────────────────────────────────────────────────────────────────

name: {name}
description: Describe what this test does

# Optional: which saved region to use (from: python run.py regions)
# region: login_screen

steps:
  - action: screenshot
    description: "Baseline screenshot before starting"

  # ── Supported actions ─────────────────────────────────────────
  # - action: click
  #   target: "Button text visible on screen"
  #
  # - action: type
  #   target: "Field label visible on screen"
  #   value:  "Text to type into the field"
  #
  # - action: wait_for
  #   target: "Text to wait for"
  #   timeout: 10
  #
  # - action: pause
  #   seconds: 2.0
  #
  # - action: screenshot
  # ─────────────────────────────────────────────────────────────

  - action: click
    target: ""
    description: "TODO: set target to the text visible on screen"
"""


# ── Venv Python ───────────────────────────────────────────────────────────────

def _python() -> str:
    if IS_WINDOWS:
        p = VENV_DIR / "Scripts" / "python.exe"
    else:
        p = VENV_DIR / "bin" / "python"
    return str(p) if p.exists() else ("python" if IS_WINDOWS else "python3")


def _run(args: list[str]) -> int:
    return subprocess.run(args).returncode


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_setup(region_name: str = "") -> int:
    """Run setup_region.py, passing an optional name to save as."""
    args = [_python(), str(ROOT / "setup_region.py")]
    if region_name:
        args.append(region_name)
    return _run(args)


def cmd_regions() -> int:
    """List all saved regions."""
    REGIONS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(REGIONS_DIR.glob("*.json"))

    print()
    print("  Saved regions:")
    print("  " + "─" * 45)

    # Include legacy default region.json if it exists
    if REGION_FILE.exists():
        import json
        d = json.loads(REGION_FILE.read_text())
        r = d.get("region", d)
        win = d.get("window_name", "?")
        print(f"  {'(default)':<22} → {win}  {r['width']}×{r['height']}")

    if not files and not REGION_FILE.exists():
        print("  (none — run: python run.py setup  <name>)")
    for f in files:
        import json
        d = json.loads(f.read_text())
        r = d.get("region", d)
        win = d.get("window_name", "?")
        print(f"  {f.stem:<22} → {win}  {r['width']}×{r['height']}")

    print()
    return 0


def cmd_new(name: str) -> int:
    """Scaffold a new blank playbook."""
    PLAYBOOKS.mkdir(parents=True, exist_ok=True)
    slug = name.lower().replace(" ", "_")
    display_name = slug.replace("_", " ").title()
    dest = PLAYBOOKS / f"{slug}.yaml"

    if dest.exists():
        print(f"\n  ℹ️   Playbook already exists: {dest.name}")
        print(f"      Open and edit it directly, or use a different name.\n")
        print(f"      To run it:  python run.py run {slug}\n")
        return 0     # not an error — just informational

    dest.write_text(PLAYBOOK_TEMPLATE.format(name=display_name, slug=slug))
    print(f"\n  ✅  Created: playbooks/{slug}.yaml")
    print(f"\n  Open the file and fill in the steps, then:")
    print(f"      python run.py run {slug} --dry-run   ← preview")
    print(f"      python run.py run {slug}              ← run live\n")
    return 0


def cmd_run(playbook_arg: str, extra_flags: list[str]) -> int:
    """Run a named playbook."""
    path = Path(playbook_arg)
    if not path.exists():
        path = PLAYBOOKS / f"{playbook_arg.removesuffix('.yaml')}.yaml"
    
    # Check suites/ directory (new structure)
    if not path.exists():
        suite_path = SUITES_DIR / playbook_arg / "tests" / "main_flow.yaml"
        if suite_path.exists():
            path = suite_path
        else:
            # Maybe they specified a file inside a suite
            # e.g. run my_suite/tests/test1.yaml
            path = SUITES_DIR / playbook_arg
    
    # Check tests/ directory (legacy recorder output)
    if not path.exists():
        test_path = ROOT / "tests" / playbook_arg / "playbook.yaml"
        if test_path.exists():
            path = test_path

    if not path.exists():
        print(f"\n  ❌  Playbook not found: {playbook_arg}")
        print(f"      Run  python run.py list  to see available playbooks.\n")
        return 1

    if not REGION_FILE.exists() and not list(REGIONS_DIR.glob("*.json")):
        print("\n  ⚠️  No capture region saved yet.")
        print("      Run:  python run.py setup\n")
        return 1

    return _run([_python(), str(ROOT / "run_playbook.py"), str(path)] + extra_flags)


def cmd_list() -> int:
    """List all available playbooks and tests."""
    # Manual
    yamls = sorted(PLAYBOOKS.glob("*.yaml"))
    # Suites
    suites = []
    if SUITES_DIR.exists():
        suites = sorted([d for d in SUITES_DIR.iterdir() if d.is_dir()])
    # Recorded (Legacy)
    legacy = []
    if (ROOT / "tests").exists():
        legacy = sorted([d for d in (ROOT / "tests").iterdir() if d.is_dir() and (d / "playbook.yaml").exists()])

    print(f"\n  Available Automation:")
    print("  " + "─" * 45)
    
    for f in yamls:
        print(f"  {f.stem:<25} — (Manual Playbook)")
    for d in suites:
        print(f"  {d.name:<25} — (Test Suite)")
    for d in legacy:
        print(f"  {d.name:<25} — (Legacy Recorded Session)")
        
    print(f"\n  To run:  ./run.sh run <name>\n")
    return 0


def cmd_ui() -> int:
    """Launch the Flask web dashboard."""
    print("\n  🚀 Starting Citrix AI Vision Agent Dashboard...")
    print("     Opening http://127.0.0.1:5001\n")
    
    # Try to open browser
    try:
        import webbrowser
        webbrowser.open("http://127.0.0.1:5001")
    except:
        pass
        
    return _run([_python(), str(ROOT / "ui" / "app.py")])


# ── Help ──────────────────────────────────────────────────────────────────────

# ── Actions ───────────────────────────────────────────────────────────────────

def cmd_record(test_name: str, region_name: str = "") -> int:
    """Launch the vision-assisted recorder."""
    python_bin = sys.executable
    recorder_path = ROOT / "agent" / "recorder.py"
    
    cmd = [python_bin, str(recorder_path), test_name]
    if region_name: cmd.append(region_name)
    
    return subprocess.run(cmd).returncode

def _usage() -> None:
    launcher = "run.bat" if IS_WINDOWS else "./run.sh"
    print(f"""
  Citrix AI Vision Agent — Record & Play
  {"─" * 55}
  {launcher} setup                  Select window → save region (Required first)
  {launcher} record <name>          RECORD your actions live (Creates YAML)
  {launcher} run    <name>          Run a playbook (live)
  {launcher} run    <name> --dry-run   Preview steps, no actions
  
  {launcher} regions                List all saved regions
  {launcher} new    <name>          Create a new blank test playbook
  {launcher} list                   List all playbooks
  {launcher} ui                     Launch the web dashboard
  {"─" * 55}
    """)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        _usage()
        sys.exit(0)

    cmd = args[0].lower()

    if cmd == "setup":
        region_name = args[1] if len(args) > 1 else ""
        sys.exit(cmd_setup(region_name))

    elif cmd == "regions":
        sys.exit(cmd_regions())

    elif cmd == "new":
        if len(args) < 2:
            print("\n  Usage: python run.py new <name>")
            print("  e.g.:  python run.py new citrix_login\n")
            sys.exit(1)
        sys.exit(cmd_new(args[1]))

    elif cmd == "record":
        if len(sys.argv) < 3:
            print("\n  ❌  Usage: run record <test_name> [region_name]")
            sys.exit(1)
        sys.exit(cmd_record(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ""))

    elif cmd == "run":
        if len(args) < 2:
            print("\n  Usage: python run.py run <playbook>")
            print("  e.g.:  python run.py run citrix_login\n")
            sys.exit(1)
        sys.exit(cmd_run(args[1], args[2:]))

    elif cmd == "list":
        sys.exit(cmd_list())

    elif cmd == "ui":
        sys.exit(cmd_ui())

    else:
        print(f"\n  ❌  Unknown command: '{cmd}'")
        _usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
