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

TESTS_DIR = ROOT / "tests"
TESTS_DIR.mkdir(parents=True, exist_ok=True)

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
    TESTS_DIR.mkdir(parents=True, exist_ok=True)
    tests = []
    for d in TESTS_DIR.iterdir():
        if d.is_dir() and (d / "playbook.yaml").exists():
            tests.append({
                "id": d.name,
                "name": d.name.replace("_", " ").title(),
                "path": str(d / "playbook.yaml")
            })
    return jsonify(tests)

@app.route("/api/playbooks/<test_id>")
def get_playbook(test_id):
    path = TESTS_DIR / test_id / "playbook.yaml"
    if not path.exists():
        return jsonify({"error": "Not found"}), 404
    return jsonify({
        "content": path.read_text(),
        "name": test_id
    })

@app.route("/api/playbooks/<test_id>", methods=["POST"])
def save_playbook(test_id):
    filename = request.args.get("file", "playbook.yaml")
    content = request.json.get("content")
    path = TESTS_DIR / test_id / filename
    path.write_text(content)
    return jsonify({"success": True})

@app.route("/api/tests/<test_id>/files")
def list_test_files(test_id):
    folder = TESTS_DIR / test_id
    if not folder.exists():
        return jsonify([])
    files = []
    for f in folder.iterdir():
        if f.is_file():
            files.append(f.name)
    return jsonify(sorted(files, key=lambda x: (not x.endswith(".yaml"), not x.endswith(".json"), x)))

@app.route("/api/tests/<test_id>/image/<filename>")
def get_test_image(test_id, filename):
    from flask import send_from_directory
    return send_from_directory(str(TESTS_DIR / test_id), filename)

@app.route("/api/playbooks/new", methods=["POST"])
def create_playbook():
    name = request.json.get("name", "new_test").lower().replace(" ", "_")
    test_folder = TESTS_DIR / name
    test_folder.mkdir(parents=True, exist_ok=True)
    
    path = test_folder / "playbook.yaml"
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
    return jsonify({"id": name, "name": name})

@app.route("/api/regions")
def list_regions():
    # In the new structure, regions are tied to tests
    regions = []
    for d in TESTS_DIR.iterdir():
        if d.is_dir() and (d / "region.json").exists():
            regions.append({
                "id": d.name,
                "name": f"{d.name.title()} Region",
                "window": "Tracked"
            })
    return jsonify(regions)

@app.route("/api/windows")
def list_windows():
    wins = _get_windows()
    return jsonify(wins)

@app.route("/api/regions/setup", methods=["POST"])
def setup_region():
    data = request.json
    test_id = data.get("name", "test").lower().replace(" ", "_")
    window = data.get("window") 
    
    test_folder = TESTS_DIR / test_id
    test_folder.mkdir(parents=True, exist_ok=True)
    
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
    # 1. Save region.json
    (test_folder / "region.json").write_text(json.dumps(region_data, indent=2))
    
    # 2. Capture and save reference.png
    import cv2
    from capture.screen_capture import ScreenCapture
    cap = ScreenCapture()
    full_img = cap.capture()
    cap.close()
    # Crop the exact window
    top, left = window["top"], window["left"]
    w, h = window["width"], window["height"]
    ref_img = full_img[top:top+h, left:left+w]
    cv2.imwrite(str(test_folder / "reference.png"), ref_img)

    # 3. Create default playbook if it doesn't exist
    pb_path = test_folder / "playbook.yaml"
    if not pb_path.exists():
        template = f"name: {test_id.title()}\ndescription: New scenario for {window['name']}\nsteps:\n  - action: screenshot\n"
        pb_path.write_text(template)
        
    return jsonify({"success": True})

@app.route("/api/run/<test_id>")
def run_playbook(test_id):
    dry_run = request.args.get("dry_run") == "true"
    
    def generate():
        # Pass the test folder path instead of just the file
        test_path = TESTS_DIR / test_id
        cmd = [get_python(), str(ROOT / "run_playbook.py"), str(test_path)]
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
