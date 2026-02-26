"""
Scaffold a new blank playbook file.

Usage:
    python new_playbook.py my_test_name
    → creates playbooks/my_test_name.yaml
"""

from __future__ import annotations
import sys
from pathlib import Path

TEMPLATE = """\
# ─────────────────────────────────────────────────────────────────
# Playbook: {name}
# Run:       ./run.sh run playbooks/{slug}.yaml
# Dry-run:   ./run.sh run playbooks/{slug}.yaml --dry-run
# ─────────────────────────────────────────────────────────────────

name: {name}
description: Describe what this test does

steps:
  - action: screenshot
    description: "Baseline screenshot"

  # ── Available actions ─────────────────────────────────────────
  # - action: click
  #   target: "Button or label text"
  #
  # - action: type
  #   target: "Field label"
  #   value:  "Text to type"
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
    description: "TODO: fill in target"
"""

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python new_playbook.py <name>")
        print("   eg: python new_playbook.py citrix_submit_claim")
        sys.exit(1)

    slug = sys.argv[1].lower().replace(" ", "_")
    name = slug.replace("_", " ").title()
    dest = Path(__file__).parent / "playbooks" / f"{slug}.yaml"
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        print(f"⚠️  Already exists: {dest}")
        sys.exit(1)

    dest.write_text(TEMPLATE.format(name=name, slug=slug))
    print(f"\n✅  Created: {dest}")
    print(f"   Edit it, then run:")
    print(f"   ./run.sh run playbooks/{slug}.yaml")
    print()

if __name__ == "__main__":
    main()
