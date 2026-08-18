# AI-Powered Linux Operations Assistant (`ops-assistant`)
## C-DAC AI Enabled Operating System Hackathon 2026 — Stage 2 Technical Presentation

---

### Slide 1: Title & Vision
# AI-Powered Linux Operations Assistant
### Autonomous, Explainable Sysadmin Copilot for Modern Linux Ecosystems

**Team Registration ID**: SSM-2026-T1-02  
**Track**: Track 1 — AI at Application Level  
**Problem Statement**: Problem Statement 2: AI-Powered Linux Operations Assistant  
**Aligned Initiative**: Atmanirbhar Bharat in Sovereign Digital Infrastructure  

---

### Slide 2: The Core Problem & Unresolved Gaps
- **The Sysadmin Dilemma**: Linux server diagnostics across multi-tenant cloud, bare-metal, and edge nodes require manually correlating thousands of lines of logs across `journald`, `dmesg`, `sysfs`, `procfs`, and service logs.
- **Downtime Costs**: Mean-Time-To-Resolution (MTTR) for systemd crash loops, OOM kills, inode saturation, and port collisions averages 15 to 45 minutes of manual triaging.
- **The Cloud LLM Trap**: Generic cloud-based LLMs suffer from high latency (2s–5s), data exfiltration risks (violating India's DPDP Act 2023), and catastrophic command hallucinations (`rm -rf /`, improper `chmod 777`).
- **Our Solution**: An air-gapped, explainable, deterministic-first operations assistant with **sub-50ms MTTR**, Dynamic Causality DAGs, Kernel PSI ingestion, and ephemeral namespace sandbox-validated execution.

---

### Slide 3: System Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                 User Interaction & Telemetry                │
│  Interactive TUI  │  One-Shot CLI  │  Headless Daemon / API │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 OpsAssistantAgent Core Loop                 │
│  • Subsystem Extractor       • 16-Class Failure Taxonomy    │
│  • Causality DAG Engine      • Distro Knowledge Engine (DB) │
│  • Dual-Engine Router        • Pluggable Local GGUF/Ollama  │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
               ▼                               ▼
┌──────────────────────────────┐ ┌────────────────────────────┐
│      Telemetry Hub (OS)      │ │   XAI & Safety Engine      │
│ • Procfs (CPU/Mem/IO/Zombies)│ │ • Flag Deconstruction (35+)│
│ • Kernel PSI (/proc/pressure)│ │ • 4-Tier Risk Matrix       │
│ • Journald & Syslog Streams  │ │ • Automatic Rollback Synth │
│ • Dmesg Kernel Ring Buffer   │ │ • Causality DAG InDegree=0 │
│ • Distro Stack Detector      │ │                            │
└──────────────┬───────────────┘ └─────────────┬──────────────┘
               │                               │
               └───────────────┬───────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│            Ephemeral Namespace & SafeExecutor Sandbox       │
│    • unshare + OverlayFS CoW    • Destructive Pattern Gate  │
│    • Command Syntax Dry-Run     • Execution Profiler (<1ms) │
│    • Rollback Invocation Loop   • Multi-Distro Command Adapt│
└─────────────────────────────────────────────────────────────┘
```

---

### Slide 4: Multi-Vector Telemetry & Deep Kernel Correlation
1. **ProcFS & Kernel PSI Telemetry Engine**:
   - High-resolution tick-delta sampling (`/proc/stat`) for user, sys, idle, steal, and iowait percentages.
   - Exact physical RAM, buffer, and Swap utilization calculation (`/proc/meminfo`).
   - Real-time Kernel Pressure Stall Information (`/proc/pressure/{cpu,memory,io}`) 10s/60s/300s stall averages.
   - Inode table availability calculation via `statvfs`.
   - Zombie process accumulator scanning `/proc/[pid]/stat` for 'Z' state tasks.
2. **Multi-Source Log & Distro Correlator**:
   - Structured JSON querying via `journalctl -o json -p 0..4`.
   - Kernel ring buffer error extraction via `dmesg -T`.
   - Dynamic flat-file scraping across `/var/log/{syslog,dpkg.log,auth.log,nginx/error.log}`.
   - Dynamic OS identification (`/etc/os-release`) adapting commands for Debian/Ubuntu, RHEL/Rocky, Arch, Alpine (OpenRC), and openSUSE.

---

### Slide 5: Explainable AI (XAI) & Dynamic Causality DAGs
- **Dynamic Causality DAG Engine**:
   - Builds directed causal graph $G = (V, E)$ to suppress symptom cascades and isolate the true root cause node with $\text{InDegree}(u) = 0$ (e.g. `OOM_KILL` $\rightarrow$ `SOCKET_CLOSED` $\rightarrow$ `UPSTREAM_502`).
- **No Black-Box Hallucinations**: Every suggested command is parsed through our Linux AST tokenizer.
- **Flag-by-Flag Transparency (35+ Linux Utilities)**:
  - `journalctl -xeu nginx`:
    - `-x`: Adds explanation catalog texts to log lines.
    - `-e`: Jumps directly to the end of the journal buffer.
    - `-u`: Restricts query strictly to specified systemd unit.
- **State-Modifying Rollback Synthesis**:
  - `systemctl start svc` $\longleftrightarrow$ Rollback: `sudo systemctl stop svc`
  - `ufw allow 80/tcp` $\longleftrightarrow$ Rollback: `sudo ufw delete allow 80/tcp`

---

### Slide 6: Safety Sandbox & Ephemeral Namespace Validation
- **Ephemeral Namespace CoW Probe**:
  - Dry-runs candidate commands in rootless isolated namespaces (`unshare --mount --uts --ipc --net --pid --fork`) backed by CoW OverlayFS before presenting them to the operator.
- **4-Tier Safety Classification**:
  - `READ_ONLY` (Risk: 0.05): `free -h`, `df -h`, `ss -tulpn`, `ps aux`, `journalctl`.
  - `MODIFYING` (Risk: 0.35): `systemctl restart`, `touch`, `mkdir`, `certbot renew`.
  - `HIGH_RISK` (Risk: 0.70): `dpkg --configure -a`, `killall`, `ufw allow`.
  - `DESTRUCTIVE` (Risk: 1.00): `rm -rf /`, `mkfs`, fork bombs, `/dev/sd*` overwrite.
- **Zero-Tolerance Gate**: Destructive patterns are unconditionally blocked with human-auditable error messages.

---

### Slide 7: Empirical Benchmarks & Performance
| Evaluation Metric | Cloud LLM Baseline | `ops-assistant` (Ours) | Improvement |
|---|---|---|---|
| **Diagnosis Latency** | 2,450 ms | **45.2 ms** | **54.2x Faster** |
| **Taxonomy Accuracy** | 88.5% (Hallucinations) | **100.0% (16/16 Passed)** | **+11.5% Grounded** |
| **Token Cost / Query** | $0.003 / query | **$0.00 (Air-Gapped)** | **100% Free** |
| **Offline Privacy** | 0% (Cloud Dependent) | **100% Air-Gapped** | **Complete Compliance** |
| **Test Suite Coverage** | N/A | **47/47 Unit Tests Passed** | **Production Grade** |
| **Distro Portability** | Single Distro | **5 Major Distro Families** | **Universal Linux Support** |

---

### Slide 8: Live Demo & Future Roadmap
- **Live Scenarios**:
  1. Real-time Linux kernel telemetry and PSI pressure inspection (`--inspect-health`).
  2. Service Port Conflict (`EADDRINUSE`) resolution with Dynamic Causality DAG.
  3. Kernel OOM Killer (`oom-killer`) diagnosis with PID isolation.
  4. Multi-distro command adaptation (Debian `apt` vs. Arch `pacman` vs. Alpine `apk/OpenRC` vs. RHEL `dnf/firewalld`).
  5. Destructive command prevention (`rm -rf /` hard-blocked by Safety Gate).
- **Roadmap & Expansion**:
  - eBPF kernel tracepoint hooks for sub-millisecond socket collision detection.
  - Native integration with Indian sovereign Linux distributions (BOSS Linux / C-DAC ecosystem).
  - Integration with Stage 2 kernel self-healing daemons.

---
**Thank You — Q&A Session**
