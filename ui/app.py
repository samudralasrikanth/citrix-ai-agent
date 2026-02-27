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
import cv2
import numpy as np
from capture.screen_capture import ScreenCapture
from vision.element_detector import ElementDetector
from utils.coords import to_screen

app = Flask(__name__)
SUITES_DIR = config.SUITES_DIR

# ── Active processes registry (for stop support) ──────────────────────────────
_active_processes: Dict[str, subprocess.Popen] = {}
_registry_lock = threading.Lock()

from utils.logger import get_logger
log = get_logger("ui.app")

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
    """Return all test suites in the suites/ directory."""
    suites = []
    if SUITES_DIR.exists():
        for d in sorted(SUITES_DIR.iterdir()):
            if d.is_dir():
                suites.append({"id": d.name, "name": d.name.replace("_", " ").title()})
    return jsonify(suites)


@app.route("/api/playbooks/<suite_id>")
def get_playbook(suite_id):
    filename = request.args.get("file", "suite_config.json")
    # For sub-files like tests/task.yaml, filename might be 'tests/task.yaml'
    path = SUITES_DIR / _safe(suite_id) / filename
    if not path.exists():
        return jsonify({"error": "Not found"}), 404
    return jsonify({"content": path.read_text(encoding="utf-8"), "name": suite_id})


@app.route("/api/playbooks/<suite_id>", methods=["POST"])
def save_playbook(suite_id):
    filename = request.args.get("file", "suite_config.json")
    content  = (request.json or {}).get("content", "")
    path     = SUITES_DIR / _safe(suite_id) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return jsonify({"success": True})


@app.route("/api/tests/<suite_id>/files")
def list_test_files(suite_id):
    base = SUITES_DIR / _safe(suite_id)
    if not base.exists():
        return jsonify([])
    
    files = []
    # Simplified scan for the dashboard
    for p in base.rglob("*"):
        if p.name.startswith(".") or ".gemini" in str(p) or "venv" in str(p):
             continue
        if p.is_file():
            rel = str(p.relative_to(base))
            files.append({
                "path": rel,
                "name": p.name,
                "size": p.stat().st_size,
                "type": p.suffix.lower().replace(".", "") or "file"
            })
            
    files.sort(key=lambda x: (x["path"].count("/"), x["path"]))
    return jsonify(files)


@app.route("/api/tests/<suite_id>/image/<path:filename>")
def get_test_image(suite_id, filename):
    return send_from_directory(str(SUITES_DIR / _safe(suite_id)), filename)


# ═══════════════════════════════════════════════════════════════════
# ── Window / Region API ─────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/windows")
def list_windows():
    return jsonify(_get_windows())


@app.route("/api/regions/setup", methods=["POST"])
def setup_region():
    try:
        data      = request.json or {}
        suite_id  = _safe(data.get("name", "suite").lower().replace(" ", "_"))
        platform  = data.get("platform", "citrix")
        window    = data.get("window", {})
        cap       = data.get("capabilities", {})
        web_conf  = data.get("web_config", {})

        if not suite_id or suite_id == "suite":
             return jsonify({"success": False, "error": "Invalid suite name"}), 400

        suite_dir = SUITES_DIR / suite_id
        
        # 1. Create subfolder structure
        try:
            suite_dir.mkdir(parents=True, exist_ok=True)
            (suite_dir / "tests").mkdir(exist_ok=True)
            (suite_dir / "memory").mkdir(exist_ok=True)
            (suite_dir / "reports").mkdir(exist_ok=True)
        except Exception as e:
            return jsonify({"success": False, "error": f"Failed to create directories: {str(e)}"}), 500

        # 2. Persist suite configuration
        config_data = {
            "suite_id": suite_id,
            "platform": platform,
            "capabilities": cap,
            "web_config": web_conf if platform == "web" else None,
            "region": {k: window[k] for k in ("top", "left", "width", "height") if k in window} if platform != "web" else None,
            "window_name": window.get("name") if platform != "web" else None,
        }
        try:
            (suite_dir / "suite_config.json").write_text(json.dumps(config_data, indent=2))
        except Exception as e:
             return jsonify({"success": False, "error": f"Failed to write config: {str(e)}"}), 500

        # 3. Handle Visual Alignment & Auto-Scan (for Citrix/Desktop)
        elements = []
        if platform != "web" and window:
            try:
                from capture.screen_capture import ScreenCapture
                from vision.element_detector import ElementDetector
                
                cap_tool = ScreenCapture()
                detector = ElementDetector()
                
                # Capture Reference
                img = cap_tool.capture(region=window)
                cap_tool.close()
                cv2.imwrite(str(suite_dir / "reference.png"), img)
                
                # Auto-Scan UI
                elements = detector.scan(img)
                
                # Save UI Map Metadata
                exported_elements = []
                for i, elem in enumerate(elements):
                    box = elem['box']
                    nx, ny = elem['cx'], elem['cy']
                    sx, sy = to_screen(nx + window.get("left", 0), ny + window.get("top", 0))
                    
                    exported_elements.append({
                        "id": i,
                        "label": elem.get('label', '').strip(),
                        "box": box,
                        "center_native": [nx, ny],
                        "center_screen": [sx, sy],
                        "size": [box[2]-box[0], box[3]-box[1]],
                        "source": elem.get("source", "unknown")
                    })

                mem_dir = suite_dir / "memory"
                mem_dir.mkdir(exist_ok=True)
                
                # Save visual map
                debug_img = detector.annotate(img, elements)
                cv2.imwrite(str(mem_dir / "ui_map.png"), debug_img)
                
                ui_map = {
                    "timestamp": time.time(),
                    "source": f"auto-scan window '{window.get('title')}'",
                    "elements": exported_elements
                }
                (mem_dir / "ui_map.json").write_text(json.dumps(ui_map, indent=2))
                
                # Also save region.json for backward compat
                region_data = {"region": config_data["region"]}
                (suite_dir / "region.json").write_text(json.dumps(region_data, indent=2))
                
            except Exception as exc:
                log.exception("Auto-scan failed during setup")

        # 4. Scaffold first test case
        try:
            test_case = suite_dir / "tests" / "main_flow.yaml"
            
            # Find a meaningful first step from the scan
            first_target = "Button"
            for e in elements:
                if e.get("label"):
                    first_target = e["label"]
                    break
            
            yaml_content = f"""name: {suite_id.replace('_', ' ').title()} Main Flow
description: "Automatically generated test suite for {platform}."

steps:
  - action: pause
    value: "1"
    description: "Wait for interface stabilization"

  - action: click
    target: "{first_target}"
    description: "Click detected element '{first_target}'"

  - action: screenshot
    description: "Capture state after first action"
"""
            test_case.write_text(yaml_content)
        except Exception as e:
             log.warning("Failed to scaffold test case: %s", e)

        return jsonify({"success": True, "id": suite_id})
    except Exception as e:
        log.exception("Global setup failure")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/suites/<suite_id>/scan", methods=["POST"])
def scan_suite_ui(suite_id):
    """
    Observer logic: Capture window OR load image, detect elements + OCR, save map + metadata
    into the suite's memory/ folder.
    """
    suite_id = _safe(suite_id)
    suite_dir = SUITES_DIR / suite_id
    if not suite_dir.exists():
        return jsonify({"success": False, "error": "Suite not found"}), 404

    data      = request.json or {}
    rel_path  = data.get("file") # optional: path relative to suite root
    
    # 1. Load config for region (only if not scanning a file)
    cfg_path = suite_dir / "suite_config.json"
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    region = cfg.get("region") if not rel_path else None
    
    if not rel_path and cfg.get("platform") == "web":
        return jsonify({"success": False, "error": "Scan window not supported for Web. Try scanning a screenshot file."}), 400

    try:
        from vision.element_detector import ElementDetector
        detector = ElementDetector()
        
        # 2. Get Source Image
        if rel_path:
            img_path = suite_dir / rel_path
            if not img_path.exists():
                 return jsonify({"success": False, "error": f"Image not found: {rel_path}"}), 404
            img = cv2.imread(str(img_path))
            if img is None:
                 return jsonify({"success": False, "error": "Failed to decode image"}), 400
            source_info = f"file '{rel_path}'"
        else:
            from capture.screen_capture import ScreenCapture
            capturer = ScreenCapture()
            img = capturer.capture(region)
            capturer.close()
            source_info = f"window '{cfg.get('suite_id')}'"
        
        # 3. Process
        elements = detector.scan(img)
        
        exported_elements = []
        for i, elem in enumerate(elements):
            box = elem['box']
            nx = elem['cx'] + (region.get("left", 0) if region else 0)
            ny = elem['cy'] + (region.get("top", 0) if region else 0)
            sx, sy = to_screen(nx, ny)

            exported_elements.append({
                "id": i,
                "label": elem.get('label', '').strip(),
                "box": box,
                "center_native": [nx, ny],
                "center_screen": [sx, sy],
                "size": [box[2]-box[0], box[3]-box[1]],
                "source": elem.get("source", "unknown")
            })

        # 4. Save results (Map + Metadata)
        mem_dir = suite_dir / "memory"
        mem_dir.mkdir(exist_ok=True)
        
        debug_img = detector.annotate(img, elements)
        cv2.imwrite(str(mem_dir / "ui_map.png"), debug_img)
        
        ui_map = {
            "timestamp": time.time(),
            "source": source_info,
            "elements": exported_elements
        }
        (mem_dir / "ui_map.json").write_text(json.dumps(ui_map, indent=2))

        return jsonify({
            "success": True, 
            "count": len(exported_elements),
            "message": f"Scanned {len(exported_elements)} elements from {source_info}."
        })

    except Exception as e:
        log.exception("Scan failed")
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════
# ── Run / Stop API ──────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/run/<suite_id>")
def run_playbook(suite_id):
    """
    Enterprise SSE runner for suites. 
    Can run specific playbooks within a suite (e.g. tests/main_flow.yaml).
    """
    dry_run = request.args.get("dry_run") == "true"
    rel_file = request.args.get("file", "tests/main_flow.yaml")

    def generate():
        suite_path = SUITES_DIR / _safe(suite_id)
        target_pb  = suite_path / rel_file
        runner     = ROOT / "run_playbook.py"
        
        # If the target file doesn't exist, we fallback or error
        if not target_pb.exists():
             yield _sse("error", f"Target playbook not found: {rel_file}")
             return

        cmd = [sys.executable, "-u", str(runner), str(target_pb)]
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
                _active_processes[suite_id] = proc

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
                _active_processes.pop(suite_id, None)
            yield "data: [DONE]\n\n"

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control":     "no-cache",
        "Transfer-Encoding": "chunked",
        "Connection":        "keep-alive",
        "X-Accel-Buffering": "no",
    })


@app.route("/api/run/<suite_id>/stop", methods=["POST"])
def stop_playbook(suite_id):
    """Gracefully terminate the running playbook process."""
    with _registry_lock:
        proc: Optional[subprocess.Popen] = _active_processes.get(suite_id)

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
    Launch the semantic recorder as a tracked subprocess.
    Streams stdout back as SSE so the UI can show live step captures.
    Also saves the PID in _active_processes so /stop can terminate it.
    """
    test_id  = _safe(test_id)
    reg_key  = f"recorder_{test_id}"

    # Kill any existing recorder for this suite
    with _registry_lock:
        existing = _active_processes.get(reg_key)
    if existing and existing.poll() is None:
        existing.terminate()

    recorder = ROOT / "agent" / "recorder.py"
    env      = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    # Launch the recorder piping its stdout so we can forward to SSE
    proc = subprocess.Popen(
        [sys.executable, "-u", str(recorder), test_id],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        cwd=str(ROOT),
        env=env,
        text=True,
        bufsize=1,
    )

    # ── CRITICAL: Read stdout in a thread so it doesn't block Popen buffer ──
    def _read_recorder_output(p, tid):
        log.info("Started log reader for recorder: %s", tid)
        try:
            for line in iter(p.stdout.readline, ""):
                if not line: break
                # Forward to app logger so we can see what's happening
                print(f"[RECORDER:{tid}] {line.strip()}")
            p.stdout.close()
        except Exception as e:
            log.error("Recorder log reader error: %s", e)

    threading.Thread(target=_read_recorder_output, args=(proc, test_id), daemon=True).start()

    with _registry_lock:
        _active_processes[reg_key] = proc

    return jsonify({
        "success": True,
        "pid":     proc.pid,
        "message": (
            f"Recorder started (PID {proc.pid}) for '{test_id}'. "
            "Hover over Citrix elements and click Capture Step. "
            "Click Stop Recording when done."
        ),
    })


@app.route("/api/record/<test_id>/capture", methods=["POST"])
def recorder_capture(test_id):
    """
    Send an ENTER keystroke to the recorder's stdin — triggers a single
    element capture at the current mouse position. Called by UI 'Capture' button.
    """
    reg_key = f"recorder_{_safe(test_id)}"
    with _registry_lock:
        proc = _active_processes.get(reg_key)

    if not proc or proc.poll() is not None:
        return jsonify({"success": False, "reason": "Recorder not running."}), 400

    try:
        proc.stdin.write("\n")
        proc.stdin.flush()
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"success": False, "reason": str(exc)}), 500


@app.route("/api/record/<test_id>/stop", methods=["POST"])
def stop_recording(test_id):
    """
    Gracefully terminate the recorder — sends 'q\\n' to stdin (clean exit),
    waits 2 s, then SIGTERM, then SIGKILL as final fallback.
    """
    reg_key = f"recorder_{_safe(test_id)}"
    with _registry_lock:
        proc = _active_processes.get(reg_key)

    if not proc or proc.poll() is not None:
        return jsonify({"stopped": False, "reason": "No active recorder."})

    try:
        # 1. Polite exit via stdin
        proc.stdin.write("q\n")
        proc.stdin.flush()
    except Exception:
        pass

    # 2. Wait up to 3 s for clean exit
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

    with _registry_lock:
        _active_processes.pop(reg_key, None)

    return jsonify({"stopped": True, "message": f"Recorder for '{test_id}' stopped."})


@app.route("/api/record/<test_id>/status")
def recorder_status(test_id):
    """Poll whether the recorder is still running — used by the UI for auto-refresh."""
    reg_key = f"recorder_{_safe(test_id)}"
    with _registry_lock:
        proc = _active_processes.get(reg_key)
    running = bool(proc and proc.poll() is None)
    return jsonify({"running": running, "test_id": test_id})


# ═══════════════════════════════════════════════════════════════════
# ── Entry point ────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # use_reloader=False: prevents double-init of heavy OCR models
    app.run(host="127.0.0.1", port=5001, debug=True, use_reloader=False)
