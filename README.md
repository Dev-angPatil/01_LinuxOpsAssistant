# AI-Powered Linux Operations Assistant (`ops-assistant`)

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-31%20passed-brightgreen.svg)]()
[![Latency](https://img.shields.io/badge/latency-%3C100ms-success.svg)]()
[![Accuracy](https://img.shields.io/badge/accuracy-100%25-brightgreen.svg)]()

**C-DAC AI Enabled Operating System Hackathon 2026 — Track 1 (AI at Application Level) — Problem Statement 2**

---

## 📌 Overview

The **AI-Powered Linux Operations Assistant** (`ops-assistant`) is an autonomous, explainable, and air-gapped system administration copilot for Linux servers and edge nodes. It ingests natural language sysadmin queries, correlates multi-vector system telemetry (`procfs`, `sysfs`, `journald`, `dmesg`, `/var/log/*`, `systemd` cgroups), isolates root causes across 16+ failure taxonomy classes in **<100ms**, and delivers step-by-step Explainable AI (XAI) rationale, flag-by-flag command breakdowns, risk scoring, and automatic rollback plan generation.

---

## ✨ Key Capabilities

1. **Deterministic-First Dual-Engine Intelligence**:
   - **Sub-100ms offline diagnosis** across 16 core Linux failure taxonomy classes with 0 cloud token costs and 100% air-gapped data privacy.
   - Pluggable local LLM hook (Ollama / Local GGUF) for complex unclassified queries.
2. **Autonomous Multi-Source Telemetry Correlation**:
   - Ingests and correlates structured `journald` JSON, kernel ring buffer (`dmesg`), flat files in `/var/log`, `/proc/stat` CPU ticks, `/proc/meminfo` RAM/Swap, `/proc/[pid]/stat` zombies, and `statvfs` inode tables.
3. **Transparent Explainable AI (XAI)**:
   - Every recommendation comes with step-by-step reasoning explaining *why* the diagnosis was reached and *what* every CLI flag does across 35+ standard Linux utilities.
4. **Safety Sandbox & Automatic Rollback Synthesis**:
   - Classifies commands into 4 safety tiers (`READ_ONLY`, `MODIFYING`, `HIGH_RISK`, `DESTRUCTIVE`).
   - Irreversibly blocks catastrophic commands (`rm -rf /`, fork bombs, `/dev/*` overwriting).
   - Generates exact undo/rollback commands for all state modifications.
5. **Interactive Terminal UI & Automated Benchmarks**:
   - Built-in `--demo`, `--benchmark`, `--export-json`, and `--export-md` modes with rich formatting and ANSI fallback.

---

## 🚀 Quickstart

### Prerequisites
- Linux OS (Debian/Ubuntu, RHEL/Fedora, Arch Linux)
- Python 3.10+
- `sudo` access for elevated journal and log inspection

### Installation
```bash
git clone https://github.com/Dev-angPatil/01_LinuxOpsAssistant.git
cd 01_LinuxOpsAssistant
pip install -r requirements.txt
```

### Usage

```bash
# 1. Run Automated Benchmark across 16 Failure Scenarios
python3 -m ops_assistant.cli --benchmark

# 2. Run Interactive Failure Demo Walkthrough
python3 -m ops_assistant.cli --demo

# 3. Inspect Live System Telemetry & Health Pressure
python3 -m ops_assistant.cli --inspect-health

# 4. One-Shot Diagnostic Query with JSON Export
python3 -m ops_assistant.cli "Why is NGINX failing to bind to port 80?" --export-json report.json

# 5. Interactive Conversational Sysadmin REPL
python3 -m ops_assistant.cli
```

---

## 📁 Repository Structure

```
01_LinuxOpsAssistant/
├── SUBMISSION.md            # Complete 13-Field Annexure III Submission Document
├── ARCHITECTURE.md          # Detailed system architecture, data flows & diagrams
├── PLAN.md                  # Milestone tracking & 4-day sprint roadmap
├── STATS.md                 # Empirical benchmark numbers & 16-scenario test results
├── LICENSE                  # Apache 2.0 Open Source License
├── requirements.txt         # Python dependencies (Rich)
├── ops_assistant/           # Core Source Code
│   ├── __init__.py
│   ├── cli.py               # Interactive CLI, TUI, Demo & Benchmark Runner
│   ├── agent.py             # Dual-engine diagnostic loop & 16 failure taxonomy KB
│   ├── models.py            # Dataclass schemas (Telemetries, Reports, XAI, Safety)
│   ├── collectors/          # Telemetry Subsystems
│   │   ├── hub.py           # Consolidated Health Snapshot Hub
│   │   ├── proc_collector.py # Kernel /proc CPU ticks, RAM, Inodes, Zombies
│   │   ├── journal_collector.py # journald, dmesg, and /var/log correlator
│   │   └── systemd_collector.py # Systemd DBus unit state & failed unit scanner
│   ├── explainer/           # Explainable AI (XAI)
│   │   └── xai.py           # 35+ utility flag deconstruction & rollback synthesizer
│   └── tools/               # Safety Sandbox & Execution
│       ├── safety.py        # AST safety validator & destructive pattern blocker
│       └── executor.py      # Subprocess profiler, dry-run simulator & rollback invoker
├── tests/                   # 31 Unit & Integration Tests (100% Pass Rate)
│   ├── test_agent.py        # 16 taxonomy scenarios, XAI & serialization tests
│   ├── test_safety.py       # Destructive patterns, fork bombs & rollback tests
│   ├── test_collectors.py   # Procfs, inodes, swap, and multi-log tests
│   └── test_cli.py          # Benchmark, demo, and export CLI tests
└── docs/                    # Stage 2 presentation assets & diagrams
    └── presentation_deck.md # Complete Stage 2 slide-by-slide deck
```

---

## 📜 License

Licensed under the [Apache License, Version 2.0](LICENSE).

