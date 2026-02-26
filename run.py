"""
Citrix AI Vision Agent — Cross-platform launcher
=================================================
Works on Mac, Linux, and Windows.

Usage:
    python run.py setup                           ← Select window/region
    python run.py new   <name>                    ← Create a new playbook
    python run.py run   <playbook>                ← Run a playbook
    python run.py run   <playbook> --dry-run      ← Preview steps only
    python run.py list                            ← List all playbooks
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
REGION_FILE = ROOT / "memory" / "region.json"

IS_WINDOWS  = platform.system() == "Windows"


# ── Venv Python path ──────────────────────────────────────────────────────────

def _python() -> str:
    """Return the Python executable inside the venv."""
    if IS_WINDOWS:
        candidates = [VENV_DIR / "Scripts" / "python.exe",
                      VENV_DIR / "Scripts" / "python"]
    else:
        candidates = [VENV_DIR / "bin" / "python",
                      VENV_DIR / "bin" / "python3"]

    for c in candidates:
        if c.exists():
            return str(c)

    # Fall back to whatever python is on PATH
    return "python" if IS_WINDOWS else "python3"


def _run(args: list[str]) -> int:
    """Run a command and return its exit code."""
    return subprocess.run(args).returncode


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_setup() -> int:
    return _run([_python(), str(ROOT / "setup_region.py")])


def cmd_new(name: str) -> int:
    return _run([_python(), str(ROOT / "new_playbook.py"), name])


def cmd_run(playbook_arg: str, extra_flags: list[str]) -> int:
    # Resolve playbook path — allow shorthand: citrix_login → playbooks/citrix_login.yaml
    path = Path(playbook_arg)
    if not path.exists():
        path = PLAYBOOKS / f"{playbook_arg.removesuffix('.yaml')}.yaml"

    if not path.exists():
        print(f"\n  ❌  Playbook not found: {playbook_arg}")
        print("      Try: python run.py list\n")
        return 1

    if not REGION_FILE.exists():
        print("\n  ⚠️  No capture region saved.")
        print("      Run first: python run.py setup\n")
        return 1

    return _run([_python(), str(ROOT / "run_playbook.py"), str(path)] + extra_flags)


def cmd_list() -> int:
    yamls = sorted(PLAYBOOKS.glob("*.yaml"))
    print()
    print("  Available playbooks:")
    print("  " + "─" * 40)
    if not yamls:
        print("  (none yet — create one with: python run.py new my_test)")
    for f in yamls:
        # Extract name: field from YAML without importing yaml
        name = f.stem
        for line in f.read_text().splitlines():
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
                break
        print(f"  {f.name:<35} — {name}")
    print()
    return 0


def _usage() -> None:
    print("""
  Citrix AI Vision Agent
  ──────────────────────────────────────────────────────
  python run.py setup                  Select window/area to capture
  python run.py new   <name>           Create a new test playbook
  python run.py run   <name>           Run a playbook (live)
  python run.py run   <name> --dry-run Preview steps, no actions
  python run.py list                   List all playbooks
  ──────────────────────────────────────────────────────
""")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        _usage()
        sys.exit(0)

    cmd = args[0].lower()

    if cmd == "setup":
        sys.exit(cmd_setup())

    elif cmd == "new":
        if len(args) < 2:
            print("  Usage: python run.py new <name>")
            sys.exit(1)
        sys.exit(cmd_new(args[1]))

    elif cmd == "run":
        if len(args) < 2:
            print("  Usage: python run.py run <playbook>")
            sys.exit(1)
        sys.exit(cmd_run(args[1], args[2:]))

    elif cmd == "list":
        sys.exit(cmd_list())

    else:
        print(f"  ❌  Unknown command: {cmd}")
        _usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
