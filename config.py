import os
from pathlib import Path
from typing import Dict, List, Optional

# ── Environment Tweaks (Speed & Noise reduction) ──────────────────────────────
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
os.environ["PYTHONWARNINGS"] = "ignore"
os.environ["SCREEN_CAPTURE_DEBUG"] = "False"

# ── Project Root ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent

# ── Directory Paths ──────────────────────────────────────────────────────────
LOGS_DIR        = BASE_DIR / "logs"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
MEMORY_DIR      = BASE_DIR / "memory"
TESTS_DIR       = BASE_DIR / "tests"

for _d in (LOGS_DIR, SCREENSHOTS_DIR, MEMORY_DIR, TESTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Subprocess Execution ──────────────────────────────────────────────────────
SUBPROCESS_TIMEOUT_SEC: int = 300   # 5 mins max per sub-test
PYTHON_EXECUTABLE: str      = os.sys.executable

# ── Screen Capture ────────────────────────────────────────────────────────────
# MSS convention starts at 1 (0 is virtual screen summarizing all monitors)
DEFAULT_MONITOR_INDEX: int = 1
# Fallback strategy (MSS_STRICT, MSS_FALLBACK_PRIMARY, MSS_ANY)
MONITOR_STRATEGY: str = "MSS_FALLBACK_PRIMARY"

# ── OCR Initialization ────────────────────────────────────────────────────────
OCR_LANG: str             = "en"
OCR_USE_ANGLE_CLS: bool   = True
OCR_MIN_CONFIDENCE: float = 0.55
OCR_PREWARM: bool         = True    # Load model once at startup

# ── Action Stability ──────────────────────────────────────────────────────────
MAX_ACTION_RETRIES: int     = 3
RETRY_BACKOFF_BASE: float   = 1.5   # 1.5s, 3s, 4.5s retries
STEP_TIMEOUT_SEC: int       = 45    # Max time per individual step
PIXEL_DIFF_THRESHOLD: float = 0.005 # Sensitivity for screen change detection

# ── Debug / Observability ─────────────────────────────────────────────────────
# If True, saves detailed frame visualisations for every step
SAVE_DEBUG_FRAMES: bool     = True
LOG_FORMAT: str             = "json"  # Options: json, text
LOG_LEVEL: str              = "DEBUG"

# ── Error Codes ───────────────────────────────────────────────────────────────
ERROR_CODES = {
    "ERR_OCR_INIT":   1001,
    "ERR_CAPTURE":    1002,
    "ERR_MATCH_FAIL": 1003,
    "ERR_TIMEOUT":    1004,
    "ERR_PERM":       1005,
    "ERR_NO_CHANGE":  1006,
    "ERR_MODEL":      1007,
}
