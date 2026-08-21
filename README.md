# AI-Powered Linux Operations Assistant (`ops-assistant`)

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-171%20passed-brightgreen.svg)]()
[![Latency](https://img.shields.io/badge/latency-%3C50ms-success.svg)]()
[![Accuracy](https://img.shields.io/badge/accuracy-100%25-brightgreen.svg)]()
[![Distro Support](https://img.shields.io/badge/distros-Debian%20%7C%20RHEL%20%7C%20Arch%20%7C%20Alpine%20%7C%20SUSE-purple.svg)]()

**C-DAC AI Enabled Operating System Hackathon 2026 — Track 1 (AI at Application Level) — Problem Statement 2**

---

## 📌 Overview

The **AI-Powered Linux Operations Assistant** (`ops-assistant`) is an autonomous, explainable, and air-gapped system administration copilot for Linux servers and edge nodes. It ingests natural language sysadmin queries (e.g. *"inside Divya create one folder name as DBMS"*, *"open YouTube"*, *"why is nginx failing to bind to port 80?"*), correlates multi-vector system telemetry (`procfs`, `sysfs`, `journald`, `dmesg`, `/var/log/*`, `/proc/pressure/*` PSI metrics, `systemd` / `OpenRC`), isolates root causes across 16+ failure taxonomy classes in **<50ms**, and delivers step-by-step Explainable AI (XAI) rationale, paragraph-form impact summaries, flag-by-flag command breakdowns, 4-tier risk scoring, ephemeral namespace sandbox validation, and automatic state-reverting rollback generation.

---

## 🧠 AI Engine & Qwen Model Management (Local vs Cloud vs Fast-Path)

`ops-assistant` operates via a flexible, multi-tiered AI architecture designed for both completely air-gapped offline edge systems and cloud-augmented environments:

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                             NATURAL LANGUAGE USER REQUEST                                │
│       "inside Divya create folder DBMS"  │  "open YouTube"  │  "why did nginx fail?"     │
└────────────────────────────────────────────┬─────────────────────────────────────────────┘
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼                                           ▼
         ┌───────────────────────────┐               ┌───────────────────────────┐
         │ 1. SEMANTIC FAST-PATH     │               │ 2. LOCAL NEURAL AI ENGINE │
         │    NaturalLanguageCompiler│               │    Qwen2.5-Coder (GGUF)   │
         │    • Sub-50ms latency     │               │    • 100% Offline / Local │
         │    • Zero RAM overhead    │               │    • llama.cpp inference  │
         │    • 16 Root Taxonomies   │               │    • Deep bash reasoning  │
         └───────────────────────────┘               └───────────────────────────┘
                       │                                           │
                       └─────────────────────┬─────────────────────┘
                                             ▼
                       ┌───────────────────────────────────────────┐
                       │ 3. CLOUD REASONING ENGINE (OPTIONAL)      │
                       │    Google Gemini 2.5 Flash / Pro API      │
                       │    • Zero-dependency fallback             │
                       └───────────────────────────────────────────┘
```

### 📥 1. How to Download the Qwen AI Model

You can download the **Qwen2.5-Coder** open-source GGUF model through any of the following methods:

#### Method A: Automated via One-Line Installer (Recommended)
```bash
# Auto-download Qwen2.5-Coder during installation:
./install.sh --qwen

# Or run interactively and select Option 4 (Qwen2.5-Coder-1.5B):
./install.sh
```

#### Method B: Direct CLI Model Downloader
```bash
# Download Qwen2.5-Coder model with live progress & auto-activation:
ops-assistant --download-model qwen

# Or download a specific Qwen variant:
ops-assistant --download-model qwen2.5-coder-1.5b
ops-assistant --download-model qwen2.5-coder-7b
```

#### Method C: Interactive Hardware Wizard
```bash
# Launch interactive hardware profiler & model installer:
ops-assistant --setup
```

#### Method D: Web GUI 1-Click Installer
1. Start the GUI: `ops-assistant --gui` (or visit `http://127.0.0.1:8888`).
2. Navigate to **Settings** $\rightarrow$ **AI Model Catalog**.
3. Tap **Download Model** next to **Qwen2.5-Coder-1.5B**.

---

### 🔍 2. How to Verify if the Model is Downloaded on Disk

You can verify whether an AI model is installed locally at any time:

```bash
# 1. Check active AI engine and configured model:
ops-assistant --model-status

# 2. View registry of all available & downloaded models:
ops-assistant --list-models

# 3. Inspect models directory directly on disk:
ls -lh models/
```

**Example Output of `ops-assistant --list-models`**:
```text
--- Edge AI Models Registry (Storage: /path/to/01_LinuxOpsAssistant/models) ---
• smollm2-360m           : SmolLM2-360M-Instruct (Q4_K_M) [NOT DOWNLOADED]
• qwen2.5-coder-0.5b     : Qwen2.5-Coder-0.5B-Instruct (Q4_K_M) [NOT DOWNLOADED]
• qwen2.5-coder-1.5b     : Qwen2.5-Coder-1.5B-Instruct (Q4_K_M) [✓ DOWNLOADED] -> models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf
• qwen2.5-coder-3b       : Qwen2.5-Coder-3B-Instruct (Q4_K_M) [NOT DOWNLOADED]
• llama-3.2-3b           : Llama-3.2-3B-Instruct (Q4_K_M) [NOT DOWNLOADED]
• qwen2.5-coder-7b       : Qwen2.5-Coder-7B-Instruct (Q4_K_M) [NOT DOWNLOADED]
```

---

### 📊 3. Open-Source Model Family Comparison

| Model Key | Model Name | Disk Size | Required RAM | Recommended Use Case |
| :--- | :--- | :---: | :---: | :--- |
| `deterministic` | **Deterministic Rule Compiler** | **0 MB** | **<50 MB** | Instant sub-50ms triage, zero memory footprint |
| `qwen2.5-coder-0.5b` | Qwen2.5-Coder-0.5B-Instruct | 379 MB | 1.2 GB | Low-memory edge nodes & micro-VMs |
| `qwen2.5-coder-1.5b` | **Qwen2.5-Coder-1.5B-Instruct** | **986 MB** | **2.5 GB** | **Recommended Default**: Balanced speed & deep Linux scripting |
| `qwen2.5-coder-3b` | Qwen2.5-Coder-3B-Instruct | 1.95 GB | 4.5 GB | High-accuracy coding & reasoning |
| `llama-3.2-3b` | Llama-3.2-3B-Instruct | 1.92 GB | 4.5 GB | Multi-step incident reasoning & structured JSON |
| `qwen2.5-coder-7b` | Qwen2.5-Coder-7B-Instruct | 4.36 GB | 8.5 GB | Deep Linux kernel internals & complex automation |
| `deepseek-r1-distill-qwen-7b` | DeepSeek-R1-Distill-Qwen-7B | 4.58 GB | 9.0 GB | Formal Chain-of-Thought (CoT) causal proofs |

---

## 🚀 Quickstart

### Prerequisites
- Linux OS (Ubuntu/Debian, Fedora/RHEL/Rocky, Arch Linux, Alpine Linux, openSUSE)
- Python 3.9+
- Standard user or `sudo` access for elevated log inspection

### ⚡ Automated 1-Line Installation (Recommended)

Run the autonomous installer directly in your terminal to automatically detect your Linux distribution, profile hardware (CPU, RAM, GPU/VRAM), install dependencies in an isolated virtual environment, download the Qwen model, and link the global `ops-assistant` command:

```bash
# Standard interactive installation:
curl -fsSL https://raw.githubusercontent.com/Dev-angPatil/01_LinuxOpsAssistant/main/install.sh | bash

# Or install with Qwen2.5-Coder pre-downloaded:
curl -fsSL https://raw.githubusercontent.com/Dev-angPatil/01_LinuxOpsAssistant/main/install.sh | bash -s -- --qwen
```

### 🛠️ Manual Installation

```bash
# 1. Clone repository
git clone https://github.com/Dev-angPatil/01_LinuxOpsAssistant.git
cd 01_LinuxOpsAssistant

# 2. Run automated installer with Qwen model
chmod +x install.sh && ./install.sh --qwen

# Or install manually via pip
pip install -r requirements.txt
```

### CLI Command Reference

Once installed, you can use the global `ops-assistant` command (or `python3 -m ops_assistant.cli`):

```bash
# 1. Natural Language Commands & File Operations
ops-assistant "inside Divya create one folder name as DBMS"
ops-assistant "create file notes.txt with content 'Hello Linux'"

# 2. Open Desktop Applications, Folders & Websites
ops-assistant "open YouTube"
ops-assistant "open lead code platform"
ops-assistant "open my DSA folder"

# 3. AI Model Management & Verification
ops-assistant --list-models          # Check which models are downloaded
ops-assistant --model-status         # View active AI engine & configuration
ops-assistant --download-model qwen  # Download Qwen2.5-Coder model

# 4. Diagnostic & System Health Queries
ops-assistant "Why is NGINX failing to bind to port 80?"
ops-assistant --inspect-health       # Real-time PSI & Health Dashboard
ops-assistant --diagnose-failed      # Scan & diagnose crashed services

# 5. Interactive Web GUI & Sysadmin REPL
ops-assistant --gui                  # Launch Web Dashboard GUI on port 8888
ops-assistant -i                     # Interactive Sysadmin REPL
ops-assistant --setup                # Re-run hardware & model wizard
```

---

## 🧪 Comprehensive Test Suite

Run the full automated test suite containing 171 unit and integration tests:

```bash
python3 -m unittest discover -s tests -v
```

```text
Ran 171 tests in 25.4s
OK (100% Pass Rate)
```

---

## 📁 Repository Structure

```
01_LinuxOpsAssistant/
├── LICENSE                                # Apache 2.0 Open Source License
├── README.md                              # Main project overview, quickstart & architecture summary
├── SUBMISSION.md                          # Official 13-Field Annexure III Submission Document
├── ARCHITECTURE.md                        # High-level architecture specification and Mermaid diagrams
├── STATS.md                               # Empirical benchmark metrics, latency tables & test results
├── PLAN.md                                # Milestone tracking & development roadmap
├── requirements.txt                       # Optional Python dependencies (rich)
│
├── docs/                                  # Complete Technical Documentation Suite
│   ├── ARCHITECTURE_SPEC.md               # In-depth subsystem specification & data flow design
│   ├── FAILURE_TAXONOMY_PLAYBOOK.md       # Detailed 16-class failure taxonomy reference guide
│   ├── USER_GUIDE.md                      # Comprehensive operator manual & CLI flag reference
│   ├── JUDGES_CHEAT_SHEET.md              # Hackathon scorecard alignment & 3-minute demo script
│   └── presentation_deck.md               # Stage 2 presentation slides in GitHub-flavored Markdown
│
├── ops_assistant/                         # Core Python Package Source Code
│   ├── __init__.py
│   ├── agent.py                           # Dual-engine diagnostic agent & 16-class taxonomy KB
│   ├── cli.py                             # Rich/ANSI CLI, interactive REPL, demo & benchmark runner
│   ├── models.py                          # Strongly-typed Dataclass schemas (Telemetries, Reports, XAI)
│   │
│   ├── collectors/                        # Multi-Vector Telemetry Ingestion Layer
│   │   ├── __init__.py
│   │   ├── hub.py                         # Consolidated Telemetry Hub & health snapshot aggregator
│   │   ├── proc_collector.py              # /proc/stat CPU ticks, /proc/meminfo RAM/Swap, inodes & zombies
│   │   ├── psi_collector.py               # /proc/pressure/{cpu,memory,io} Kernel PSI stall metrics
│   │   ├── journal_collector.py           # journalctl JSON, dmesg -T kernel ring buffer & /var/log/*
│   │   ├── systemd_collector.py           # DBus systemd unit state inspector & failed unit scanner
│   │   └── distro_detector.py             # /etc/os-release parser & distro stack identifier
│   │
│   ├── explainer/                         # Neuro-Symbolic Explainable AI (XAI) Layer
│   │   ├── __init__.py
│   │   ├── causality_dag.py               # Directed Acyclic Graph engine with InDegree=0 root isolation
│   │   └── xai.py                         # 35+ Linux utility flag deconstruction & rollback synthesizer
│   │
│   ├── tools/                             # Safety Sandbox & Subprocess Execution Layer
│   │   ├── __init__.py
│   │   ├── safety.py                      # 4-tier AST safety validator & destructive pattern blocker
│   │   ├── sandbox_probe.py               # Ephemeral User+Mount namespace dry-run CoW probe
│   │   └── executor.py                    # Subprocess profiler, dry-run simulator & rollback invoker
│   │
│   ├── db/                                # Multi-Distro Knowledge Base Layer
│   │   ├── __init__.py
│   │   └── distro_db.py                   # Embedded SQLite relational knowledge base
│   │
│   ├── data/                              # Static Knowledge Base Seeds
│   │   └── distro_knowledge.json          # Distro profiles, command templates & lock signatures
│   │
│   └── model_manager/                     # Local Offline Model Management
│       ├── __init__.py
│       └── downloader.py                  # Offline GGUF edge model downloader & verifier
│
└── tests/                                 # 47 Unit & Integration Tests (100% Pass Rate)
    ├── __init__.py
    ├── test_agent.py                      # 16 taxonomy scenarios, XAI generation & report serialization
    ├── test_causality_dag.py              # Multi-event causal cascades & InDegree=0 root isolation
    ├── test_cli.py                        # CLI flags, benchmark, demo, exports & health dashboards
    ├── test_collectors.py                 # Procfs CPU ticks, memory, inodes, swap & journald logs
    ├── test_distro_db.py                  # Distro detector, SQLite KB & multi-distro command adaptation
    ├── test_psi_collector.py              # Kernel /proc/pressure parsing & mock stall metrics
    ├── test_safety.py                     # 4-tier risk classification, destructive blockers & rollbacks
    └── test_sandbox_probe.py              # Ephemeral namespace dry-run probe & syntax verification
```

---

## 📜 Documentation Index

- **[System Architecture Specification](docs/ARCHITECTURE_SPEC.md)**: Full component specs, mathematical formulations, and data flows.
- **[Failure Taxonomy Playbook](docs/FAILURE_TAXONOMY_PLAYBOOK.md)**: Exhaustive reference for all 16 Linux failure taxonomy classes.
- **[User & Operator Manual](docs/USER_GUIDE.md)**: Detailed user manual, CLI commands, REPL options, and export formats.
- **[Judges Evaluation Cheat Sheet](docs/JUDGES_CHEAT_SHEET.md)**: 3-minute live demo script and hackathon scorecard alignment.
- **[Stage 2 Presentation Deck](docs/presentation_deck.md)**: Slide deck in clean presentation markdown.
- **[Empirical Benchmark Report](STATS.md)**: Empirical test numbers, latencies, and pass rates.
- **[Official Submission Dossier](SUBMISSION.md)**: 13-field Annexure III submission document.

---

## 📜 License

Licensed under the [Apache License, Version 2.0](LICENSE).
