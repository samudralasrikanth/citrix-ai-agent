# Citrix AI Vision Agent

A **fully local**, **offline** Python agent that automates Citrix-hosted desktop applications
using computer vision, OCR, and fuzzy text matching.  
**No LLM · No external APIs · No cloud.**

---

## Architecture

```
citrix_ai_agent/
├── main.py                     ← Agent loop + CLI
├── config.py                   ← All tunable parameters
├── requirements.txt
│
├── capture/
│   └── screen_capture.py       ← MSS full-screen / region capture
│
├── vision/
│   ├── ocr_engine.py           ← PaddleOCR → [{text, box, confidence}]
│   ├── element_detector.py     ← Canny contours + OCR label merge
│   ├── screen_state.py         ← Builds hashed screen snapshot
│   └── similarity.py           ← RapidFuzz helpers (best_match, all_matches)
│
├── agent/
│   ├── planner.py              ← Heuristic fuzzy planner (NO LLM)
│   ├── action_executor.py      ← click / type / wait_for + retry logic
│   ├── reward_engine.py        ← +10 / -5 / -10 scoring
│   └── memory_manager.py       ← JSON memory (coords, success_rate)
│
├── utils/
│   ├── logger.py               ← Dual stdout + file logger
│   └── image_utils.py          ← image_hash, pixel_diff_ratio, save_image
│
├── logs/                       ← agent.log
├── screenshots/                ← per-step PNGs
└── memory/
    └── action_memory.json      ← persisted action statistics
```

---

## Tech Stack

| Library | Purpose |
|---|---|
| `mss` | Fast cross-platform screen capture |
| `opencv-python` | Canny edges, contour detection, pixel diff |
| `paddleocr` | Local offline OCR — text + bounding boxes |
| `rapidfuzz` | Fuzzy string matching (replaces LLM intent) |
| `pyautogui` | Mouse click + keyboard type automation |

---

## Installation (Windows — Python 3.10+)

### 1 · Create virtual environment

```powershell
python -m venv venv
.\venv\Scripts\activate
```

### 2 · Install dependencies

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

> **First run:** PaddleOCR downloads model weights (~100 MB) automatically. Subsequent runs use the local cache.

> **GPU acceleration:** Replace `paddlepaddle` with `paddlepaddle-gpu` and ensure CUDA 11.x is present.

---

## Configuration (`config.py`)

| Key | Default | Description |
|---|---|---|
| `CAPTURE_MONITOR_INDEX` | `1` | Primary monitor (mss convention) |
| `CAPTURE_REGION` | `None` | `None` = full screen; or `{top,left,width,height}` |
| `OCR_MIN_CONFIDENCE` | `0.55` | Drop OCR results below this score |
| `FUZZY_MATCH_THRESHOLD` | `85.0` | Min RapidFuzz score to accept a text match |
| `PIXEL_DIFF_THRESHOLD` | `0.01` | > 1 % pixels changed = "screen changed" |
| `MAX_ACTION_RETRIES` | `3` | Retry count before giving up on an action |
| `STEP_DELAY_SEC` | `1.2` | Seconds to wait after each action |

---

## Running the Agent

```powershell
cd citrix_ai_agent
python main.py                                              # default goal, 3 steps
python main.py --goal "click Submit" --steps 5
python main.py --goal "type POL-001 in Policy Number" --steps 3
python main.py --goal "wait_for Confirmation" --steps 5
python main.py --goal "Submit the claim form" --steps 10   # free-text fuzzy mode
```

### CLI flags

| Flag | Default | Description |
|---|---|---|
| `--goal` | `"click Submit"` | Action goal string |
| `--steps` | `3` | Max agent loop iterations |

---

## Goal Format

| Pattern | Example | Behaviour |
|---|---|---|
| `click <label>` | `click Submit` | Fuzzy-match label → click centre |
| `type <value> in <field>` | `type POL-001 in Policy Number` | Click field → select-all → type |
| `wait_for <text>` | `wait_for Confirmation` | Poll OCR until text appears |
| Free text | `Submit the claim form` | Token-by-token fuzzy scan → click |

---

## How the Planner Works (No LLM)

```
Goal: "click Submitt"  ← typo intentional
         ↓
RapidFuzz token_set_ratio against visible texts
         ↓
"Submit" scores 97 > threshold (85)
         ↓
Action: {"action": "click", "target_text": "Submit"}
```

Fuzzy threshold is configurable in `config.py → FUZZY_MATCH_THRESHOLD`.

---

## Retry Logic

Each action is attempted up to `MAX_ACTION_RETRIES` (default: 3) times.  
After every attempt the agent takes a fresh screenshot and computes the
pixel diff ratio. If < 1 % pixels changed, it retries with the same action.

```
Attempt 1 → no screen change → retry
Attempt 2 → no screen change → retry
Attempt 3 → screen changed   → success, breaks loop
```

---

## Reward Signal

| Condition | Score |
|---|---|
| Screen changed, no error keyword | **+10** |
| Screen did not change | **-5** |
| Error keyword detected OR execution exception | **-10** |

---

## Memory Schema (`memory/action_memory.json`)

```json
{
  "a3f9c1b2|submit": {
    "last_coordinates": [960, 540],
    "success_count": 3,
    "failure_count": 1,
    "success_rate": 0.75,
    "total_reward": 25
  }
}
```

The executor can use `memory.get_coordinates()` to skip visual search on
previously visited screens (hook point — extend `action_executor.py`).

---

## Screen State Format

```json
{
  "screen_id":     "a3f9c1b2d4e5f617",
  "timestamp":     "2026-02-26T08:58:00",
  "step":          2,
  "visible_texts": ["Policy Number", "Submit", "Cancel"],
  "elements": [
    {"box": [100, 200, 300, 240], "label": "Submit", "cx": 200, "cy": 220, "source": "ocr_only"}
  ]
}
```

`screen_id` is a **perceptual image hash** (8×8 aHash) — visually identical
screens always share the same ID, even with minor OCR variance.

---

## Extending the Agent

| Goal | File to edit |
|---|---|
| Add `scroll` / `hotkey` action | `agent/action_executor.py` |
| Add YOLO element detection | `vision/element_detector.py` |
| Add multi-goal sequence file | new `agent/goal_runner.py` |
| Change reward heuristic | `agent/reward_engine.py` |
| Use SQLite instead of JSON | `agent/memory_manager.py` |
| Capture only part of screen | `config.py → CAPTURE_REGION` |

---

## Safety

- **PyAutoGUI FAILSAFE** is `True` — move mouse to **top-left corner** to abort immediately.
- Press `Ctrl+C` in the terminal at any time to stop cleanly.
- All data (screenshots, logs, memory) stays **100 % local**.
