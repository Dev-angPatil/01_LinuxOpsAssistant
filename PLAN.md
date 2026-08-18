# Development Plan — AI-Powered Linux Operations Assistant (`ops-assistant`)

## 🎯 Project Goals
Deliver a fully functional, explainable, and production-ready CLI/TUI assistant that automates Linux troubleshooting, log analysis, and system administration operations with sub-100ms air-gapped performance.

---

## 📅 Roadmap & Milestones

### Phase 1: Core Scaffolding & Collectors (Day 1)
- [x] Create project repository structure, LICENSE (Apache 2.0), requirements, and docs.
- [x] Implement `collectors/proc_collector.py` for direct `/proc` metric parsing (CPU ticks, RAM/Swap, Inodes, Zombies).
- [x] Implement `collectors/journal_collector.py` for structured `journalctl`, `dmesg`, and `/var/log/*` retrieval.
- [x] Implement `collectors/systemd_collector.py` for unit state inspection.
- [x] Implement `collectors/hub.py` for unified telemetry snapshot.

### Phase 2: Agentic Diagnostics & XAI Reasoning (Day 2)
- [x] Build `agent.py` diagnostic loop with multi-log correlation.
- [x] Develop `explainer/xai.py` for structured root-cause explanations and 35+ utility flag-by-flag breakdowns.
- [x] Implement 16-class failure taxonomy covering port conflicts, OOM kills, inode exhaustion, SSL expiry, DPKG locks, NTP drift, etc.
- [x] Implement automatic state-reverting rollback/undo synthesizer.
- [x] Implement pluggable local LLM backend hook (Ollama / Local GGUF).

### Phase 3: Interactive CLI & Safety Sandbox (Day 3)
- [x] Create `cli.py` with `rich` UI: streaming responses, tables, confirmation menus, and ANSI fallback.
- [x] Implement `tools/safety.py` and `tools/executor.py` with 4-tier risk tagging, catastrophic pattern blocking, and dry-run execution.
- [x] Implement `--demo`, `--benchmark`, `--export-json`, and `--export-md` command-line modes.
- [x] Write comprehensive unit & integration test suites in `tests/` (24/24 tests passing).

### Phase 4: Benchmarks, Docs & Submission Deliverables (Day 4)
- [x] Benchmark diagnostic accuracy across 16 failure scenarios in `STATS.md` (100% accuracy, 99.78ms average latency).
- [x] Complete 13-field Annexure III submission dossier in `SUBMISSION.md`.
- [x] Create Stage 2 technical presentation deck in `docs/presentation_deck.md`.
- [x] Verify live execution on Linux kernel (`--inspect-health`, `--benchmark`, `--demo`).

