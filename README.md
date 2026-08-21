# AI-Powered Linux Operations Assistant (`ops-assistant`)

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-47%20passed-brightgreen.svg)]()
[![Latency](https://img.shields.io/badge/latency-%3C50ms-success.svg)]()
[![Accuracy](https://img.shields.io/badge/accuracy-100%25-brightgreen.svg)]()
[![Distro Support](https://img.shields.io/badge/distros-Debian%20%7C%20RHEL%20%7C%20Arch%20%7C%20Alpine%20%7C%20SUSE-purple.svg)]()

**C-DAC AI Enabled Operating System Hackathon 2026 — Track 1 (AI at Application Level) — Problem Statement 2**

---

## 📌 Overview

The **AI-Powered Linux Operations Assistant** (`ops-assistant`) is an autonomous, explainable, and air-gapped system administration copilot for Linux servers and edge nodes. It ingests natural language sysadmin queries, correlates multi-vector system telemetry (`procfs`, `sysfs`, `journald`, `dmesg`, `/var/log/*`, `/proc/pressure/*` PSI metrics, `systemd` / `OpenRC`), isolates root causes across 16+ failure taxonomy classes in **<50ms**, and delivers step-by-step Explainable AI (XAI) rationale, flag-by-flag command breakdowns, 4-tier risk scoring, ephemeral namespace sandbox validation, and automatic state-reverting rollback generation.

---

## ✨ Key Architectural Innovations

1. **Dynamic Causality DAG Engine (`ops_assistant.explainer.causality_dag`)**:
   - Constructs directed causal graphs $G = (V, E)$ to isolate true root causes with topological in-degree minimization ($\text{InDegree}=0$), suppressing symptom cascade noise (e.g. `KERNEL_OOM` $\rightarrow$ `PROCESS_KILLED` $\rightarrow$ `SOCKET_CLOSED` $\rightarrow$ `UPSTREAM_502`).

2. **Kernel Pressure Stall Information (PSI) Ingestion (`ops_assistant.collectors.psi_collector`)**:
   - Directly parses `/proc/pressure/{cpu,memory,io}` 10s/60s/300s stall averages, detecting memory pressure and I/O starvation before unrecoverable kernel panics occur.

3. **Ephemeral Namespace CoW Sandbox Probe (`ops_assistant.tools.sandbox_probe`)**:
   - Empirically dry-runs candidate remediation commands inside isolated User + Mount namespaces (`unshare` + OverlayFS) to verify syntax, arguments, and safety prior to presenting them to the operator.

4. **Multi-Distro Knowledge Base & Dynamic Adaptation (`ops_assistant.db.distro_db`)**:
   - Backed by an embedded SQLite knowledge engine mapping commands, lock paths, and error patterns across Debian/Ubuntu, RHEL/Rocky/Fedora, Arch Linux, Alpine Linux (OpenRC/apk), and openSUSE/SLES (zypper/firewalld).

5. **AST Safety Guardrails & 4-Tier Risk Matrix (`ops_assistant.tools.safety`)**:
   - Classifies commands into `READ_ONLY` (0.05), `MODIFYING` (0.35), `HIGH_RISK` (0.70), and `DESTRUCTIVE` (1.00).
   - Hard-blocks destructive commands (`rm -rf /`, fork bombs, raw block writes) with zero execution leaks.

6. **Transparent Explainable AI (XAI) & Rollbacks (`ops_assistant.explainer.xai`)**:
   - Provides plain-English flag-by-flag breakdowns across 35+ core Linux utilities and synthesizes inverse rollback commands (`systemctl start <-> stop`, `ufw allow <-> delete allow`).

7. **Deterministic-First Dual-Engine Intelligence (`ops_assistant.agent`)**:
   - Achieves sub-50ms offline deterministic triage across 16 core failure taxonomies, with pluggable local open-weight LLM fallback (Ollama / GGUF) for unclassified edge queries.

---

## 🚀 Quickstart

### Prerequisites
- Linux OS (Ubuntu/Debian, Fedora/RHEL/Rocky, Arch Linux, Alpine Linux, openSUSE)
- Python 3.9+
- Standard user or `sudo` access for elevated log inspection

### ⚡ Automated 1-Line Installation (Recommended)

Run the autonomous installer directly in your terminal to automatically detect your Linux distribution, profile hardware (CPU, RAM, GPU/VRAM), install dependencies in an isolated virtual environment, choose your open-source AI model, and link the global `ops-assistant` command:

```bash
curl -fsSL https://raw.githubusercontent.com/Dev-angPatil/01_LinuxOpsAssistant/main/install.sh | bash
```

### 🛠️ Manual Installation

```bash
# 1. Clone repository
git clone https://github.com/Dev-angPatil/01_LinuxOpsAssistant.git
cd 01_LinuxOpsAssistant

# 2. Run automated installer locally
chmod +x install.sh && ./install.sh

# Or install manually via pip
pip install -r requirements.txt
```

### CLI Command Reference

Once installed, you can use the global `ops-assistant` command (or `python3 -m ops_assistant.cli`):

```bash
# 1. One-Shot Natural Language Diagnostic Query
ops-assistant "Why is NGINX failing to bind to port 80?"

# 2. Interactive Conversational Sysadmin REPL
ops-assistant -i

# 3. Inspect Real-Time Linux Health, Distro Profile & Kernel PSI Pressure
ops-assistant --inspect-health

# 4. Scan and Diagnose Failed System Services
ops-assistant --diagnose-failed

# 5. Run Hardware Setup & Model Configuration Wizard
ops-assistant --setup

# 6. Launch Interactive Web GUI Dashboard
ops-assistant --gui

# 7. Run Automated Benchmark across 16 Failure Scenarios
ops-assistant --benchmark

# 8. Run Interactive Failure Demo Walkthrough
ops-assistant --demo
```

---

## 🧪 Comprehensive Test Suite

Run the full automated test suite containing 47 unit and integration tests:

```bash
python3 -m unittest discover -s tests -v
```

```text
Ran 47 tests in 8.4s
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
