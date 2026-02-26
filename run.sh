#!/usr/bin/env zsh
# ════════════════════════════════════════════════════════════════
#  Citrix AI Vision Agent  —  Command Runner
#  Works like UFT / Tosca: setup → write playbook → run
#
#  COMMANDS:
#    ./run.sh setup              Select app window + capture region
#    ./run.sh new  <name>        Create a new blank playbook
#    ./run.sh run  <playbook>    Execute a playbook  (YAML file)
#    ./run.sh run  <playbook> --dry-run   Preview steps only
#    ./run.sh list               List all available playbooks
# ════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/venv"
PLAYBOOK_DIR="$SCRIPT_DIR/playbooks"

# ── Check venv ────────────────────────────────────────────────────
if [[ ! -d "$VENV" ]]; then
  echo ""
  echo "  ❌  Virtual environment not found."
  echo "      python3 -m venv venv && pip install -r requirements.txt"
  echo ""
  exit 1
fi
source "$VENV/bin/activate"

# ── Helper: print usage ───────────────────────────────────────────
_usage() {
  echo ""
  echo "  Usage:"
  echo "    ./run.sh setup               →  Select window + area to capture"
  echo "    ./run.sh new  <name>         →  Create a new blank playbook"
  echo "    ./run.sh run  <playbook>     →  Run a playbook (yaml file)"
  echo "    ./run.sh run  <playbook> --dry-run  →  Preview steps (no action)"
  echo "    ./run.sh list                →  Show available playbooks"
  echo ""
}

# ── setup ─────────────────────────────────────────────────────────
if [[ "$1" == "setup" ]]; then
  python "$SCRIPT_DIR/setup_region.py"
  exit $?
fi

# ── new <name> ────────────────────────────────────────────────────
if [[ "$1" == "new" ]]; then
  if [[ -z "$2" ]]; then
    echo "  Usage: ./run.sh new <playbook_name>"
    exit 1
  fi
  python "$SCRIPT_DIR/new_playbook.py" "$2"
  exit $?
fi

# ── list ──────────────────────────────────────────────────────────
if [[ "$1" == "list" ]]; then
  echo ""
  echo "  Available playbooks:"
  echo "  ─────────────────────────────────────"
  count=0
  for f in "$PLAYBOOK_DIR"/*.yaml; do
    [[ -f "$f" ]] || continue
    name=$(grep '^name:' "$f" | head -1 | sed 's/name: *//')
    echo "    $(basename $f)  —  ${name:-untitled}"
    count=$((count + 1))
  done
  if [[ $count -eq 0 ]]; then
    echo "    (none yet — create one with: ./run.sh new my_test)"
  fi
  echo ""
  exit 0
fi

# ── run <playbook> [--dry-run] [--no-stop] ────────────────────────
if [[ "$1" == "run" ]]; then
  if [[ -z "$2" ]]; then
    echo "  Usage: ./run.sh run <playbook>"
    echo "  eg:    ./run.sh run playbooks/citrix_login.yaml"
    exit 1
  fi

  PLAYBOOK="$2"
  # allow shorthand: ./run.sh run citrix_login  (no path/ext needed)
  if [[ ! -f "$PLAYBOOK" ]]; then
    PLAYBOOK="$PLAYBOOK_DIR/${2%.yaml}.yaml"
  fi

  if [[ ! -f "$PLAYBOOK" ]]; then
    echo "  ❌  Playbook not found: $2"
    echo "      Try: ./run.sh list"
    exit 1
  fi

  # Check region is saved
  if [[ ! -f "$SCRIPT_DIR/memory/region.json" ]]; then
    echo ""
    echo "  ⚠️  No capture region saved!"
    echo "      Run first:  ./run.sh setup"
    echo ""
    exit 1
  fi

  shift 2   # remove 'run' and playbook name — pass rest as flags
  python "$SCRIPT_DIR/run_playbook.py" "$PLAYBOOK" "$@"
  exit $?
fi

# ── no command / --help ───────────────────────────────────────────
_usage
exit 0
