import os
from pathlib import Path
from typing import Dict, List, Optional

# ── Environment Tweaks (Speed & Noise reduction) ──────────────────────────────
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
# Suppress urllib3 and other common warnings
os.environ["PYTHONWARNINGS"] = "ignore"

# ── Project Root ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent

# ── Directory Paths ──────────────────────────────────────────────────────────
LOGS_DIR        = BASE_DIR / "logs"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
MEMORY_DIR      = BASE_DIR / "memory"

for _d in (LOGS_DIR, SCREENSHOTS_DIR, MEMORY_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Screen Capture ────────────────────────────────────────────────────────────
CAPTURE_MONITOR_INDEX: int               = 1       # 1 = primary monitor (mss convention)
CAPTURE_REGION: Optional[Dict]           = None    # None = full screen
                                                   # e.g. {"top":0,"left":0,"width":1920,"height":1080}

# ── OCR ───────────────────────────────────────────────────────────────────────
OCR_LANG: str             = "en"
OCR_USE_ANGLE_CLS: bool   = True
OCR_MIN_CONFIDENCE: float = 0.55           # Drop results below this threshold

# ── Vision / Element Detection ────────────────────────────────────────────────
EDGE_CANNY_LOW: int      = 50
EDGE_CANNY_HIGH: int     = 150
MIN_CONTOUR_AREA: int    = 400             # px² — minimum area to keep a region

# ── Similarity (RapidFuzz) ────────────────────────────────────────────────────
FUZZY_MATCH_THRESHOLD: float = 85.0       # Score in [0,100]; above = match

# ── Action Execution ──────────────────────────────────────────────────────────

STEP_DELAY_SEC: float         = 1.2       # Pause after every action
PIXEL_DIFF_THRESHOLD: float   = 0.01      # > 1 % pixels changed = screen changed
MAX_ACTION_RETRIES: int        = 3        # Retry an action this many times

# ── Reward Engine ─────────────────────────────────────────────────────────────
REWARD_SUCCESS: int   =  10
REWARD_NO_CHANGE: int =  -5
REWARD_ERROR: int     = -10
ERROR_KEYWORDS: List[str] = ["error", "failed", "invalid", "exception", "not found"]

# ── Memory ────────────────────────────────────────────────────────────────────
MEMORY_FILE: Path = MEMORY_DIR / "action_memory.json"

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str  = "DEBUG"
LOG_FILE: Path  = LOGS_DIR / "agent.log"
