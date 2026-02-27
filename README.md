# Citrix AI Vision Agent (Refined)

A **fully local**, **offline** automation platform for Citrix-hosted desktop applications. Powered by computer vision and a hardened 7-point reliability engine.

---

## 🚀 Key Features

*   **Dashboard-Centric**: Unified web interface for managing test suites, scanning UI landscapes, and running live automations.
*   **Vision First**: Uses OpenCV (Canny/Contours) and PaddleOCR for deterministic UI element detection.
*   **No Cloud / No LLM**: Operates entirely behind your firewall with decentralized intelligence.
*   **Suite-Based Isolation**: Organized test suites with private metadata, UI maps, memory, and reports.
*   **Reliability Chain**: Includes normalization, coordinate memory, and pixel-diff click validation.

---

## 🏗️ Quick Start

### 1 · Setup Environment
```bash
./run.sh setup
```

### 2 · Launch Dashboard
```bash
./run.sh ui
```
*Access at: http://127.0.0.1:5001*

---

## 📂 Project Structure

```text
citrix_ai_agent/
├── suites/                     ← Active Test Suites
│   └── example_suite/
│       ├── tests/              ← Playbooks (YAML)
│       ├── memory/             ← UI Maps and Coordinate History
│       ├── reports/            ← Execution Analytics
│       └── suite_config.json   ← Suite Metadata
│
├── orchestrator/               ← Central Brain (Multi-channel)
├── executors/                  ← Vision, Web, and API Handlers
├── engine/                     ← Ranking, Memory, and States
├── vision/                     ← OCR and Element Detection
└── ui/                         ← Flask Dashboard (HTML/JS)
```

---

## 🛠️ Usage Workflow

1.  **Create Suite**: Use the Dashboard to create a new suite for your application (Citrix, Desktop, or Web).
2.  **Scan UI**: Open the suite and click **Scan UI**. The agent will map all clickable elements and store them in `memory/ui_map.json`.
3.  **Author Playbook**: Create a `.yaml` playbook in the `tests/` folder. You can target elements by **Text** (`"Login"`) or **Index** (`"#5"` from the scan map).
4.  **Run Live**: Execute your playbook and watch the agent navigate, click, and verify in real-time.

---

## 📚 Reference Example

See `suites/reference_example` for a documented sample of:
- OCR-based targeting
- Index-based targeting
- Multi-step automation flows
- Verification and Screen capturing
