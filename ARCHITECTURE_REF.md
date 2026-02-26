# Enterprise Multi-Channel Automation Platform (POC)

This project has been refactored into a modular, deterministic orchestrator supporting Vision, Web, and API channels.

## 🏗️ Core Architecture

### 1. Orchestration Layer (`orchestrator/`)
- **Orchestrator**: The central brain. It loads playbooks, determines the execution channel (`vision` | `web` | `api`), and delegates tasks. It is "LLM-Ready" as it returns structured candidates and accepts high-level goals.

### 2. Executor Layer (`executors/`)
- **BaseExecutor**: Abstract interface ensuring all channels provide consistent operations (`click`, `type`, `verify`).
- **VisionExecutor**: The "Hardened Citrix Engine". Uses the 7-point reliability chain, OCR, and visual memory.
- **APIExecutor**: Lightweight `requests`-based engine for integrating backend service calls.
- **WebExecutor**: DOM-based automation provider (Skeleton for Selenium/Playwright).

### 3. Intelligence Engine (`engine/`)
- **RankingEngine**: Replaces simple fuzzy matching. Uses a weighted formula (40% Fuzzy, 20% OCR, 20% Geometry, 20% Memory) to pick the best UI element.
- **MemoryEngine**: Self-healing persistence. Maps `screen_hash` + `target` to known coordinates. 
- **StateEngine**: Identifies UI states via perceptual hashing (downscaled MD5), enabling loop detection and state-aware memory.

### 4. Safety & Analytics (`validation/`, `analytics/`)
- **Playbook Schema**: Pydantic-powered validation. Prevents semantic mismatches (e.g., clicking on an API endpoint) before execution.
- **Execution Analytics**: Structured logging (JSONLines). Tracks rankings, durations, and pixel-diffs for every step.

## 🚀 Key Improvements

- **Deterministic**: Every click is validated via pixel-diff change detection.
- **Self-Healing**: If a detection fails, the system automatically checks Memory for high-confidence historical coordinates.
- **Multi-Channel**: Mixes API, Web, and Citrix automation in a single Playbook.
- **Enterprise Grade**: Structured reporting, flaky target identification, and modularity for SaaS deployment.
