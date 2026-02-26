from __future__ import annotations
import os
import sys
from pathlib import Path

# Shared root setup
ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))

import subprocess
import threading
import json
import logging
from flask import Flask, render_template, jsonify, request, Response

from setup_region import _get_windows
import config

app = Flask(__name__)
TESTS_DIR = ROOT / "tests"
TESTS_DIR.mkdir(parents=True, exist_ok=True)

# ── API Endpoints ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/playbooks")
def list_playbooks():
    tests = []
    for d in TESTS_DIR.iterdir():
        if d.is_dir() and (d / "playbook.yaml").exists():
            tests.append({
                "id": d.name,
                "name": d.name.replace("_", " ").title()
            })
    return jsonify(tests)

@app.route("/api/playbooks/<test_id>")
def get_playbook(test_id):
    path = TESTS_DIR / test_id / "playbook.yaml"
    if not path.exists():
        return jsonify({"error": "Not found"}), 404
    return jsonify({"content": path.read_text(), "name": test_id})

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
    if not folder.exists(): return jsonify([])
    files = [f.name for f in folder.iterdir() if f.is_file()]
    return jsonify(sorted(files, key=lambda x: (not x.endswith(".yaml"), not x.endswith(".json"), x)))

@app.route("/api/tests/<test_id>/image/<filename>")
def get_test_image(test_id, filename):
    from flask import send_from_directory
    return send_from_directory(str(TESTS_DIR / test_id), filename)

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
        "region": {"top": window["top"], "left": window["left"], "width": window["width"], "height": window["height"]}
    }
    
    (test_folder / "region.json").write_text(json.dumps(region_data, indent=2))
    
    import cv2
    from capture.screen_capture import ScreenCapture
    cap = ScreenCapture()
    ref_img = cap.capture(region=window)
    cap.close()
    cv2.imwrite(str(test_folder / "reference.png"), ref_img)

    pb_path = test_folder / "playbook.yaml"
    if not pb_path.exists():
        template = f"name: {test_id.title()}\ndescription: New scenario for {window['name']}\nsteps:\n  - action: screenshot\n"
        pb_path.write_text(template)
        
    return jsonify({"success": True})

@app.route("/api/run/<test_id>")
def run_playbook(test_id):
    """
    Bulletproof SSE runner with active heartbeats and crash-safe streaming.
    """
    dry_run = request.args.get("dry_run") == "true"
    
    def generate():
        test_path = TESTS_DIR / test_id
        # Perfect alignment: use the exact same interpreter
        python_bin = sys.executable
        runner_path = ROOT / "run_playbook.py"
        
        cmd = [python_bin, "-u", str(runner_path), str(test_path)]
        if dry_run: cmd.append("--dry-run")
        
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        
        # 1. Connection Header
        yield f"data: {json.dumps({'status': 'init', 'message': 'Booting hardened runner...'})}\n\n"
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(ROOT),
                env=env
            )
            
            # 2. Active monitor loop with heartbeat
            last_activity = time.time()
            
            # Configure non-blocking stdout reading
            import fcntl
            fd = process.stdout.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            while True:
                # Check for output
                try:
                    line = process.stdout.readline()
                    if line:
                        last_activity = time.time()
                        try:
                            json.loads(line)
                            yield f"data: {line}\n\n"
                        except:
                            yield f"data: {json.dumps({'status': 'raw', 'message': line.strip()})}\n\n"
                    elif process.poll() is not None:
                        break
                except (IOError, TypeError):
                    # No data to read yet
                    pass

                # 3. Heartbeat (every 5 seconds)
                if time.time() - last_activity > 5:
                    yield ": ping\n\n"
                    last_activity = time.time()

                time.sleep(0.1)
            
            process.stdout.close()
            rc = process.wait()
            
            if rc == 0:
                yield f"data: {json.dumps({'status': 'finish', 'message': 'Execution successful.'})}\n\n"
            else:
                yield f"data: {json.dumps({'status': 'error', 'message': f'Process stopped with code {rc}'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': f'Launch Failure: {str(e)}'})}\n\n"
            
        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Transfer-Encoding": "chunked",
        "Connection": "keep-alive"
    })

if __name__ == "__main__":
    app.run(port=5001, debug=True)
