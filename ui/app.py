"""
Citrix AI Vision Agent — Enterprise Flask Dashboard Backend
===========================================================
Bulletproof SSE streaming, stop-signal support, structured logs, and
a full REST API for test-suite management.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import Dict, Optional

# ── Project root setup ─────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))

from flask import Flask, Response, jsonify, render_template, request, send_from_directory
from setup_region import _get_windows
import config

app = Flask(__name__)
TESTS_DIR = ROOT / "tests"
TESTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Active processes registry (for stop support) ──────────────────────────────
_active_processes: Dict[str, subprocess.Popen] = {}
_registry_lock = threading.Lock()

# ── Logging ───────────────────────────────────────────────────────────────────
log = logging.getLogger("ui.app")

# ═══════════════════════════════════════════════════════════════════
# ── Page Render ────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


# ═══════════════════════════════════════════════════════════════════
# ── Playbook / Test-Suite API ───────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/playbooks")
def list_playbooks():
    """Return all test suites that have a playbook.yaml."""
    tests = []
    if TESTS_DIR.exists():
        for d in sorted(TESTS_DIR.iterdir()):
            if d.is_dir() and (d / "playbook.yaml").exists():
                tests.append({"id": d.name, "name": d.name.replace("_", " ").title()})
    return jsonify(tests)


@app.route("/api/playbooks/<test_id>")
def get_playbook(test_id):
    filename = request.args.get("file", "playbook.yaml")
    path = TESTS_DIR / _safe(test_id) / _safe(filename)
    if not path.exists():
        return jsonify({"error": "Not found"}), 404
    return jsonify({"content": path.read_text(encoding="utf-8"), "name": test_id})


@app.route("/api/playbooks/<test_id>", methods=["POST"])
def save_playbook(test_id):
    filename = request.args.get("file", "playbook.yaml")
    content  = (request.json or {}).get("content", "")
    path     = TESTS_DIR / _safe(test_id) / _safe(filename)
    path.write_text(content, encoding="utf-8")
    return jsonify({"success": True})


@app.route("/api/tests/<test_id>/files")
def list_test_files(test_id):
    folder = TESTS_DIR / _safe(test_id)
    if not folder.exists():
        return jsonify([])
    files = [f.name for f in folder.iterdir() if f.is_file()]
    # Preferred order: yaml → json → png → rest
    files.sort(key=lambda x: (
        0 if x.endswith(".yaml") else
        1 if x.endswith(".json") else
        2 if x.endswith(".png")  else 3,
        x
    ))
    return jsonify(files)


@app.route("/api/tests/<test_id>/image/<filename>")
def get_test_image(test_id, filename):
    return send_from_directory(str(TESTS_DIR / _safe(test_id)), _safe(filename))


# ═══════════════════════════════════════════════════════════════════
# ── Window / Region API ─────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/windows")
def list_windows():
    return jsonify(_get_windows())


@app.route("/api/regions/setup", methods=["POST"])
def setup_region():
    data      = request.json or {}
    test_id   = _safe(data.get("name", "test").lower().replace(" ", "_"))
    window    = data.get("window", {})
    folder    = TESTS_DIR / test_id
    folder.mkdir(parents=True, exist_ok=True)

    # Persist region metadata
    region_data = {
        "window_name": window.get("name"),
        "region": {k: window[k] for k in ("top", "left", "width", "height") if k in window},
    }
    (folder / "region.json").write_text(json.dumps(region_data, indent=2))

    # Capture reference screenshot
    try:
        import cv2
        from capture.screen_capture import ScreenCapture
        cap = ScreenCapture()
        img = cap.capture(region=window)
        cap.close()
        cv2.imwrite(str(folder / "reference.png"), img)
    except Exception as exc:
        log.warning("Could not save reference screenshot: %s", exc)

    # Scaffold playbook if absent
    pb = folder / "playbook.yaml"
    if not pb.exists():
        pb.write_text(
            f"name: {test_id.replace('_',' ').title()}\n"
            f"description: Automation suite for {window.get('name','')}\n"
            f"steps:\n  - action: screenshot\n    description: Initial state capture\n",
            encoding="utf-8",
        )

    return jsonify({"success": True, "id": test_id})


# ═══════════════════════════════════════════════════════════════════
# ── Run / Stop API ──────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/run/<test_id>")
def run_playbook(test_id):
    """
    Enterprise SSE runner.
    • Bulletproof heartbeat (prevents connection drops during AI init).
    • Non-blocking character queue (cross-platform, no fcntl).
    • Step-progress signals forwarded to the frontend.
    • Process registered for optional stop support.
    """
    dry_run = request.args.get("dry_run") == "true"

    def generate():
        test_path  = TESTS_DIR / _safe(test_id)
        runner     = ROOT / "run_playbook.py"
        cmd        = [sys.executable, "-u", str(runner), str(test_path)]
        if dry_run:
            cmd.append("--dry-run")

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        yield _sse("init", "Booting enterprise runner…")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(ROOT),
                env=env,
            )

            with _registry_lock:
                _active_processes[test_id] = proc

            q: Queue = Queue()

            def _reader(pipe, queue):
                buf = ""
                try:
                    while True:
                        ch = pipe.read(1)
                        if not ch and proc.poll() is not None:
                            break
                        if ch in ("\n", "\r"):
                            if buf.strip():
                                queue.put(buf.strip())
                            buf = ""
                        else:
                            buf += ch
                    pipe.close()
                except Exception:
                    pass

            reader = threading.Thread(target=_reader, args=(proc.stdout, q), daemon=True)
            reader.start()

            last_beat = time.time()

            while True:
                try:
                    line = q.get_nowait()
                    last_beat = time.time()
                    try:
                        parsed = json.loads(line)
                        yield f"data: {json.dumps(parsed)}\n\n"
                    except json.JSONDecodeError:
                        yield _sse("raw", line)
                except Empty:
                    if not reader.is_alive() and q.empty():
                        break

                # Active heartbeat — prevents browser SSE timeout
                if time.time() - last_beat > 3.5:
                    yield _sse("heartbeat", "…")
                    last_beat = time.time()

                time.sleep(0.05)

            rc = proc.wait()
            if rc == 0:
                yield _sse("finish", "✓ Execution completed successfully.")
            elif rc == -15:  # SIGTERM from stop endpoint
                yield _sse("warning", "Execution terminated by user.")
            else:
                yield _sse("error", f"Runner exited with code {rc}.")

        except Exception as exc:
            yield _sse("error", f"Launch failure: {exc}")
        finally:
            with _registry_lock:
                _active_processes.pop(test_id, None)
            yield "data: [DONE]\n\n"

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control":     "no-cache",
        "Transfer-Encoding": "chunked",
        "Connection":        "keep-alive",
        "X-Accel-Buffering": "no",
    })


@app.route("/api/run/<test_id>/stop", methods=["POST"])
def stop_playbook(test_id):
    """Gracefully terminate the running playbook process."""
    with _registry_lock:
        proc: Optional[subprocess.Popen] = _active_processes.get(test_id)

    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        return jsonify({"stopped": True})

    return jsonify({"stopped": False, "reason": "No active process found."})


# ═══════════════════════════════════════════════════════════════════
# ── Helpers ────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════

def _sse(status: str, message: str) -> str:
    return f"data: {json.dumps({'status': status, 'message': message})}\n\n"

def _safe(name: str) -> str:
    """Strip path traversal characters from user-supplied names."""
    return Path(name).name


# ═══════════════════════════════════════════════════════════════════
# ── Entry point ────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/record/<test_id>/start", methods=["POST"])
def start_recording(test_id):
    """
    Launch the recorder as a background subprocess.
    The recorder runs interactively in the user's terminal — this endpoint
    just kicks it off and returns immediately.
    """
    test_id  = _safe(test_id)
    region   = request.json.get("region_name", "") if request.json else ""
    recorder = ROOT / "agent" / "recorder.py"
    cmd      = [sys.executable, str(recorder), test_id]
    if region:
        cmd.append(region)

    # Open a new terminal window with the recorder running inside it
    import platform
    if platform.system() == "Darwin":
        apple_script = (
            f'tell application "Terminal" to do script '
            f'"cd {ROOT} && source venv/bin/activate && python agent/recorder.py {test_id}"'
        )
        subprocess.Popen(["osascript", "-e", apple_script])
    else:
        subprocess.Popen(cmd, cwd=str(ROOT))

    return jsonify({"success": True, "message": f"Recorder launched for '{test_id}'. Check the Terminal window."})


# ═══════════════════════════════════════════════════════════════════
# ── Entry point ────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # use_reloader=False: prevents double-init of heavy OCR models
    app.run(host="127.0.0.1", port=5001, debug=True, use_reloader=False)

