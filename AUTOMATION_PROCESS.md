# Citrix AI Vision Agent — Automation Lifecycle & Reliability Chain

This document details the internal process flow of the Citrix Vision Agent, from initial screen capture to post-click validation.

---

## 1. High-Level Architecture
The agent follows an **Observe → Orient → Plan → Act** (OODA) loop, specifically hardened for the high-latency and visual noise inherent in Citrix environments.

1.  **Observe**: Capture the screen region and run the Enhanced OCR pipeline.
2.  **Orient**: Build a `ScreenState` (perceptual hash ID + visible tags).
3.  **Plan**: Match the goal keyword (e.g., "click Submit") against the `ScreenState`.
4.  **Act**: Dispatch to the **7-Point Reliability Match Engine**.

---

## 2. The 7-Point Reliability Chain
When an action is requested (e.g., `click "Login"`), the `MatchEngine` executes the following fallback logic in order:

### ① Text Normalization
OCR often misreads Citrix fonts (e.g., `0K` for `OK`, `Ye5` for `Yes`).
*   **Process**: All OCR output and the target string are normalized (lowercase, punctuation stripped, specific character substitutions).
*   **Benefit**: Eliminates "False Misses" caused by standard OCR noise.

### ② Dynamic Short-Target Handling
Small targets (≤ 3 chars like `OK`, `Go`, `X`) are the most likely to fail standard fuzzy matching.
*   **Logic**: If target length ≤ 3, the fuzzy threshold is lowered from **75** to **60**, and `partial_ratio` is given higher weight.
*   **Benefit**: Prevents the system from giving up on small buttons that have low OCR confidence.

### ③ Coordinate Memory (Context-Aware)
*   **Logic**: If the same label was successfully clicked previously *in the same window layout* (verified via region hash), the agent uses the cached coordinates immediately.
*   **Benefit**: Zero-latency execution for repeated tasks.

### ④ Multiscale Template Matching
If OCR fails to find the text (e.g., if the button is purely an icon or uses a non-standard font).
*   **Process**: OpenCV searches for a previously saved reference crop of the button at multiple scales (0.85x to 1.15x).
*   **Benefit**: Provides a purely visual "Plan B" when text-based vision fails.

### ⑤ Automatic Region Expansion
If the target is located but its bounding box is partially cut off by the capture region.
*   **Process**: The system expands the capture area by 40px, re-captures, and re-resolves.
*   **Benefit**: Ensures the agent clicks the *center* of the button even if it's on the edge of the window.

### ⑥ Platform-Aware Input
*   **Logic**: Uses native macOS `command` or Windows `control` hotkeys to clear fields before typing.
*   **Benefit**: Reliable field entry even if the field isn't empty.

### ⑦ Post-Click Pixel Validation
*   **Process**: After clicking, the agent compares the "Before" and "After" pixels.
*   **Logic**: If the screen hasn't changed by at least 0.5%, the click is considered a "Ghost Click".
*   **Response**: The agent invalidates the coordinate memory, re-scans the screen, and retries the action up to 2 times.

---

## 3. Implementation Workflow (Automation Process)

### Step 1: Learning Phase (Manual/Recorded)
When you record a playbook via the Dashboard:
*   The system performs **Screen Discovery** using Canny edge detection.
*   It merges OCR labels onto those visual regions.
*   It generates a **Tosca-style Fingerprint** (Label + Type + Context + RelPos) for each click.

### Step 2: Automation Execution
The `runner.py` reads the `playbook.yaml`:
1.  **Alignment**: It locates the Citrix window using the `reference.png`.
2.  **Scoping**: It initializes the `MatchEngine` with a `context_id` unique to that test.
3.  **Iteration**: For each step, it runs the **7-Point Chain**.
4.  **Self-Healing**: If a step fails, the `ActionExecutor` retries with backoff, often correcting for temporary network lag or transient UI popups.

---

## 4. Performance Optimizations
*   **Bilateral Filtering**: Replaces heavy denoising for snappy 1080p response times.
*   **Lazy Loading**: The PaddleOCR model is loaded once at startup and kept in memory.
*   **JSON Streaming**: The runner emits structured events for real-time dashboard monitoring.
