#!/usr/bin/env bash
# Citrix AI Vision Agent — Mac/Linux launcher

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/venv"
VENV_PYTHON="$VENV/bin/python"

# ── Check venv ────────────────────────────────────────────────────
if [[ ! -x "$VENV_PYTHON" ]]; then
    echo ""
    echo "  ❌  Virtual environment not found."
    echo "      Create it: python3 -m venv venv && ./venv/bin/pip install -r requirements.txt"
    echo ""
    exit 1
fi

# ── Run main launcher ─────────────────────────────────────────────
"$VENV_PYTHON" "$SCRIPT_DIR/run.py" "$@"
exit $?
