# VISION: AI-Powered Linux Operations Assistant (`ops-assistant`)

## 1. Executive Summary & Core Mission
Modern Linux operations are overwhelmed by alert fatigue, cascading failure symptoms, and cryptic kernel/daemon logs. When critical outages strike, operators are forced to sift through thousands of lines in `journalctl`, `dmesg`, `/var/log`, and `/proc/pressure/*` under high stress.

**The Vision:** Provide an autonomous, air-gapped, explainable, and hardware-conscious Linux operations copilot that diagnoses system failures in **<50ms**, isolates the true root cause using causal DAGs (rather than hallucinated symptoms), validates fixes inside ephemeral copy-on-write namespaces, and synthesizes reversible rollback actions.

---

## 2. Core Problem Solved
1. **Symptom Cascade Confusion:** 
   - A single root cause (e.g., Kernel OOM) creates dozens of downstream symptoms (worker process dies $\rightarrow$ socket hangup $\rightarrow$ reverse proxy 502). Traditional LLMs try to fix the 502; `ops-assistant` isolates the in-degree zero root cause.
2. **Blast Radius & Operator Lockout:**
   - Raw shell suggestions can brick remote access (e.g., flushing `iptables` over SSH or running unbounded `chmod -R 777 /`). `ops-assistant` enforces AST-level safety gateways.
3. **Init System & Distro Heterogeneity:**
   - Linux is not just Ubuntu `systemd`. It spans Alpine (`OpenRC`/`apk`), RHEL (`firewalld`/`SELinux`), Arch (`pacman`), and openSUSE (`zypper`). `ops-assistant` provides deterministic cross-distro translation.
4. **Crisis-Time Resource Footprint:**
   - Running massive multi-gigabyte models on an already starving server triggers kernel panics. `ops-assistant` operates with a deterministic-first engine (~20MB RAM, <50ms) with adaptive local open-weight fallback.

---

## 3. Product & Design Philosophy (Anti-Bloat & Core-First)
- **Deterministic-First, AI-Augmented:** Deterministic telemetry collectors and causal graphs handle 95% of operational failures instantly without model hallucination or GPU requirements.
- **Explainable by Design (XAI):** Every single remediation command is accompanied by flag-by-flag plain-English explanations and a guaranteed inverse rollback command.
- **Zero Host Mutation Without Consent:** Diagnostic steps are read-only; execution occurs only after explicit operator authorization or dry-run validation in ephemeral namespaces.
- **Minimalist CLI & TUI:** Fast, sleek, unbloated terminal workflow with zero unnecessary complexity.

---

## 4. Target User Personas
- **Site Reliability Engineers (SREs) & DevOps Engineers:** Fast multi-vector root-cause triage during production outages.
- **Linux System Administrators:** Managing heterogeneous fleets (Debian, RHEL, Arch, Alpine, SUSE) with consistent automated rollback tracking.
- **Edge & Embedded Linux Developers:** Running lightweight, air-gapped diagnostics on constrained single-board computers (Raspberry Pi, industrial gateways) using sub-1GB models or deterministic mode.
- **Junior Developers & Sysadmin Learners:** Understanding *why* a failure occurred and what each flag in a remediation command does.

---

## 5. Key Success Criteria
- **Latency:** Deterministic root-cause isolation in $<50\text{ms}$.
- **Accuracy:** 100% precision on the 16 core Linux failure taxonomy classes.
- **Safety:** 0% destructive command escapes through AST validation.
- **Resource Footprint:** Base engine footprint $<25\text{MB}$ RAM.
- **Portability:** Seamless one-line curl installation across major Linux distributions.
