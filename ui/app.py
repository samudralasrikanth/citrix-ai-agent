from __future__ import annotations
import os
import subprocess
import threading
import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))

from flask import Flask, render_template, jsonify, request, Response
from setup_region import _get_windows

app = Flask(__name__)

ROOT = Path(__file__).parent.parent
PLAYBOOKS_DIR = ROOT / "playbooks"
REGIONS_DIR = ROOT / "memory" / "regions"
DEFAULT_REGION = ROOT / "memory" / "region.json"

# Utility to find venv python
def get_python():
    if os.name == "nt":
        p = ROOT / "venv" / "Scripts" / "python.exe"
    else:
        p = ROOT / "venv" / "bin" / "python"
    return str(p) if p.exists() else "python3"

# --- API Endpoints ---

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/playbooks")
def list_playbooks():
    PLAYBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(PLAYBOOKS_DIR.glob("*.yaml"))
    playbooks = []
    for f in files:
        playbooks.append({
            "id": f.name,
            "name": f.stem.replace("_", " ").title(),
            "path": str(f)
        })
    return jsonify(playbooks)

@app.route("/api/playbooks/<filename>")
def get_playbook(filename):
    path = PLAYBOOKS_DIR / filename
    if not path.exists():
        return jsonify({"error": "Not found"}), 404
    return jsonify({
        "content": path.read_text(),
        "name": filename
    })

@app.route("/api/playbooks/<filename>", methods=["POST"])
def save_playbook(filename):
    content = request.json.get("content")
    path = PLAYBOOKS_DIR / filename
    path.write_text(content)
    return jsonify({"success": True})

@app.route("/api/playbooks/new", methods=["POST"])
def create_playbook():
    name = request.json.get("name", "new_test").lower().replace(" ", "_")
    path = PLAYBOOKS_DIR / f"{name}.yaml"
    if path.exists():
        return jsonify({"error": "Already exists"}), 400
    
    template = f"""name: {name.title()}
description: Describe what this test does
steps:
  - action: screenshot
    description: "Startup"
  - action: click
    target: "Button"
"""
    path.write_text(template)
    return jsonify({"id": f"{name}.yaml", "name": name})

@app.route("/api/regions")
def list_regions():
    REGIONS_DIR.mkdir(parents=True, exist_ok=True)
    regions = []
    
    # Check default
    if DEFAULT_REGION.exists():
        import json
        try:
            d = json.loads(DEFAULT_REGION.read_text())
            regions.append({"id": "default", "name": "Default", "window": d.get("window_name")})
        except: pass
        
    for f in REGIONS_DIR.glob("*.json"):
        import json
        try:
            d = json.loads(f.read_text())
            regions.append({
                "id": f.stem,
                "name": f.stem.replace("_", " ").title(),
                "window": d.get("window_name")
            })
        except: pass
    return jsonify(regions)

@app.route("/api/windows")
def list_windows():
    wins = _get_windows()
    return jsonify(wins)

@app.route("/api/regions/setup", methods=["POST"])
def setup_region():
    data = request.json
    name = data.get("name", "manual").lower().replace(" ", "_")
    window = data.get("window") # The window dict from list_windows
    
    region_data = {
        "window_name": window["name"],
        "region": {
            "top": window["top"],
            "left": window["left"],
            "width": window["width"],
            "height": window["height"]
        }
    }
    
    import json
    # Save as default
    DEFAULT_REGION.write_text(json.dumps(region_data, indent=2))
    
    # Save as named
    if name != "default":
        REGIONS_DIR.mkdir(parents=True, exist_ok=True)
        (REGIONS_DIR / f"{name}.json").write_text(json.dumps(region_data, indent=2))
        
    return jsonify({"success": True})

@app.route("/api/run/<filename>")
def run_playbook(filename):
    dry_run = request.args.get("dry_run") == "true"
    
    def generate():
        cmd = [get_python(), str(ROOT / "run_playbook.py"), str(PLAYBOOKS_DIR / filename)]
        if dry_run:
            cmd.append("--dry-run")
            
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(ROOT)
        )
        
        for line in iter(process.stdout.readline, ""):
            yield f"data: {line}\n\n"
        process.stdout.close()
        process.wait()
        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype="text/event-stream")

if __name__ == "__main__":
    app.run(port=5001, debug=True)
