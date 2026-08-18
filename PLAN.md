# Development Plan — AI-Powered Linux Operations Assistant (`ops-assistant`)

## 🎯 Project Goals
Deliver a fully functional, explainable, and production-ready CLI/TUI assistant that automates Linux troubleshooting, log analysis, and system administration operations with sub-50ms air-gapped performance, Dynamic Causality DAGs, multi-distro knowledge engine, and namespace sandboxed execution.

---

## 📅 Roadmap & Milestones

### Phase 1: Core Scaffolding & Telemetry Ingestion (Day 1)
- [x] Create project repository structure, LICENSE (Apache 2.0), requirements, and base docs.
- [x] Implement `collectors/proc_collector.py` for direct `/proc` metric parsing (CPU ticks, RAM/Swap, Inodes, Zombies).
- [x] Implement `collectors/psi_collector.py` for `/proc/pressure/{cpu,memory,io}` Kernel PSI stall metrics.
- [x] Implement `collectors/journal_collector.py` for structured `journalctl`, `dmesg -T`, and `/var/log/*` retrieval.
- [x] Implement `collectors/systemd_collector.py` for unit state inspection and failed unit scanning.
- [x] Implement `collectors/distro_detector.py` for OS family detection.
- [x] Implement `collectors/hub.py` for unified health snapshot aggregation.

### Phase 2: Agentic Diagnostics, Causality DAGs & XAI (Day 2)
- [x] Build `agent.py` diagnostic loop with multi-log correlation.
- [x] Implement `explainer/causality_dag.py` for Directed Acyclic Graph generation and $\text{InDegree}=0$ root-cause isolation.
- [x] Develop `explainer/xai.py` for structured root-cause explanations and 35+ utility flag-by-flag breakdowns.
- [x] Implement 16-class failure taxonomy covering port conflicts, OOM kills, inode exhaustion, SSL expiry, DPKG locks, NTP drift, etc.
- [x] Implement automatic state-reverting rollback/undo synthesizer.
- [x] Implement pluggable local LLM backend hook (Ollama / Local GGUF).

### Phase 3: Multi-Distro Engine, Sandbox & Interactive CLI (Day 3)
- [x] Create `db/distro_db.py` embedded SQLite knowledge base supporting Debian/Ubuntu, RHEL/Rocky, Arch, Alpine, and openSUSE.
- [x] Implement `tools/sandbox_probe.py` for ephemeral User+Mount namespace (`unshare` + OverlayFS) dry-runs.
- [x] Implement `tools/safety.py` and `tools/executor.py` with 4-tier risk tagging, catastrophic pattern blocking, and dry-run execution.
- [x] Create `cli.py` with `rich` UI: health snapshots, interactive REPL, `--demo`, `--benchmark`, `--export-json`, and `--export-md` command-line modes.
- [x] Write comprehensive unit & integration test suites in `tests/` (41/41 tests passing).

### Phase 4: Benchmarks, Docs & Submission Deliverables (Day 4)
- [x] Benchmark diagnostic accuracy across 16 failure scenarios in `STATS.md` (100% accuracy, 45.2ms average latency).
- [x] Complete 13-field Annexure III submission dossier in `SUBMISSION.md`.
- [x] Create Stage 2 technical presentation deck in `docs/presentation_deck.md`.
- [x] Author comprehensive subsystem specs in `docs/ARCHITECTURE_SPEC.md` and failure playbook in `docs/FAILURE_TAXONOMY_PLAYBOOK.md`.
- [x] Author operator guide in `docs/USER_GUIDE.md` and evaluation rubric in `docs/JUDGES_CHEAT_SHEET.md`.
- [x] Verify live execution on Linux kernel (`--inspect-health`, `--benchmark`, `--demo`).
