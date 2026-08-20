# System Design Specification: AI-Powered Linux Operations Assistant & GUI Dashboard

> **Document Version**: 3.0.0  
> **Status**: Production Reference Design  
> **Target Environment**: Linux (Ubuntu, Debian, Fedora, RHEL, Arch, Alpine, openSUSE)  

---

## 1. Executive Summary & Mission

The **AI-Powered Linux Operations Assistant** (`ops-assistant`) is an autonomous, explainable operations dashboard and desktop automation copilot for Linux servers, workstations, and edge appliances.

It converges:
1. **Sub-50ms Deterministic Triage**: 16-class Linux failure taxonomy knowledge base.
2. **Topological Causality DAG Engine**: Root cause isolation with in-degree minimization (InDegree=0).
3. **Explainable AI (XAI)**: Flag-by-flag command breakdowns and state rollbacks.
4. **4-Tier AST Safety & Ephemeral CoW Namespace Sandboxing**: Safe execution guardrails.
5. **Modern Glassmorphic Web GUI Dashboard**: Real-time telemetry visualizers (Chart.js + SSE streaming), service and process managers, storage analyzers, and an AI Agent Home Page for natural language desktop & OS automation.

---

## 2. System Architecture

```mermaid
graph TD
    subgraph GUI Presentation Layer (Linear Monochrome)
        SPA[Linear Dark Mode SPA Dashboard]
        Tab1[AI Ops Agent Home]
        Tab2[Telemetry & PSI Metrics]
        Tab3[Services & Processes]
        Tab4[Storage & Cleanup]
        Tab5[Network & Firewall]
        Tab6[16-Class Taxonomy & DAG]
        Tab7[Multi-Distro Packages]
        Tab8[Desktop & Runner]
        PermGate[Command Execution Permission Modal]
        ToastSystem[Floating Toast Notifications]
        
        SPA --> Tab1 & Tab2 & Tab3 & Tab4 & Tab5 & Tab6 & Tab7 & Tab8
        Tab1 & Tab3 & Tab4 & Tab5 & Tab6 & Tab8 --> PermGate
        PermGate --> ToastSystem
    end

    subgraph Embedded Backend Server (ops_assistant.gui)
        Server[ThreadingHTTPServer REST + SSE]
        APIRouter[REST Endpoint Dispatcher]
        SSEStreamer[1Hz Telemetry / Log Streamer]
        Server --> APIRouter & SSEStreamer
    end

    subgraph Agentic & Automation Engine
        Agent[Dual-Engine Agent KB + GGUF/Ollama LLM]
        IntentRouter[NLP Hybrid Intent Router]
        DesktopOps[Desktop Manager xdg-open, browser, viewer]
        DownloadOps[Stream Downloader & Extractor]
        StorageOps[Storage Analyzer & Auto-Organizer]
        ProcessOps[Process & Service Manager]
        SafetyEngine[AST Safety Matrix & CoW Sandbox]
        
        APIRouter --> Agent
        Agent --> IntentRouter
        IntentRouter --> DesktopOps & DownloadOps & StorageOps & ProcessOps & SafetyEngine
    end

    SPA <==> Server
```

---

## 3. GUI Dashboard Workspaces & Linear Design System

### Design Tokens & Aesthetics
- **Theme**: Linear-inspired high-contrast dark monochrome (`#08090C` canvas, `#0D0E13` subtle surfaces, `#121319` cards, `#181922` elevated cards).
- **Typography**: Inter for UI text and JetBrains Mono for system metrics, commands, and terminal outputs.
- **Accents**: Pure white (`#FFFFFF`) primary action buttons with black labels; razor-thin 1px borders (`rgba(255,255,255,0.08)`).
- **Notifications**: Floating, non-blocking toast notifications replacing crude browser native `alert()` and `confirm()` dialogs.

### Tab 1: AI Agent Command Center (Home)
- **Natural Language Execution Prompt**: Terminal-style input (`$ ...`) executing diagnostics, file ops, service control, and OS tasks.
- **Command Approval Cards**: For any proposed or modifying operation, displays the exact command `$ <command>`, copy button, short description of what it will do, safety badge, risk score, and `[Approve & Execute]` vs `[Dry-Run Sandbox]` buttons.
- **Reasoning Stream**: Collapsible step-by-step agent thinking, stdout/stderr viewer with execution latency, and one-click rollback trigger.

### Tab 2: System Health & PSI Telemetry
- **Kernel Pressure Stall Information (PSI)**: Real-time 10s, 60s, 300s stall averages for `/proc/pressure/{cpu,memory,io}`.
- **Monochrome Telemetry Charts**: Chart.js graphs for CPU delta ticks and RAM/Swap consumption with dark grid lines.
- **Gauges & Tables**: Host profile, kernel release, uptime, load averages (1m, 5m, 15m), zombie process counters, and filesystem partition usage.

### Tab 3: Services & Process Manager
- **Service Controller**: Filterable systemd/OpenRC services table with status badges (Active, Inactive, Failed), permission-gated start/stop/restart actions, and modal journalctl logs viewer.
- **Process Manager**: Real-time process table sorted by CPU/Memory with PID inspection and permission-gated termination dialogs.

### Tab 4: Storage & Cleanup
- **Partition Tree**: Disk mount capacity and inode usage tracker.
- **Large File Scanner**: Scans for files exceeding 100MB with human-readable formatting.
- **Smart Directory Organizer**: Auto-categorizes messy directories into Images, Videos, Audio, Documents, Spreadsheets, Archives, Code with Dry-Run preview and permission-gated execution.
- **System Cleaner**: Purges cached packages, rotated journal logs, and `/tmp` files with permission confirmation.

### Tab 5: Network & Firewall
- **Interfaces & Bandwidth**: Network adapters, IP addresses, MAC, MTU.
- **Listening Sockets**: Open TCP/UDP ports, listening addresses, bound PIDs/processes (`ss`/`netstat`).
- **Firewall Manager**: UFW / Firewalld rule viewer; allow/deny rules with permission gating.

### Tab 6: Diagnostics & 16-Class Taxonomy Engine
- **Failure Taxonomy Simulator**: Interactive runner across 16 core Linux failure modes.
- **Interactive Causality DAG Visualizer**: Renders G=(V, E) causal graphs isolating root causes (InDegree=0).
- **XAI Flag Breakdown & Sandbox Probe**: Explains command flags and dry-runs in ephemeral User+Mount namespaces with permission-gated execution.

### Tab 7: Multi-Distro Package Manager
- **Distro Adaptation**: Auto-detects package ecosystem (`apt`, `dnf`, `pacman`, `apk`, `zypper`).
- **Package Search & Operations**: Search repositories, list installed packages, install/remove packages with safety checks.

### Tab 8: Desktop & Direct CLI Runner
- **Direct CLI Command Runner**: Run arbitrary commands with AST safety validation, preview modal, and permission confirmation.
- **Universal Downloader**: Streaming HTTP/HTTPS file downloader with progress tracking, safe filename resolution, and auto-archive extraction.
- **Quick Desktop Launchers**: Open Home, Downloads, Pictures in native file managers (`xdg-open`), launch URLs in default web browser.

---

## 4. Safety & Security Architecture & Permission Guardrails

1. **Explicit Permission Guardrail**:
   - Every modifying, high-risk, or destructive action requires explicit user permission before execution.
   - The UI presents the exact command line, a human-readable description of its system impact, risk score, and safety category.
2. **4-Tier Risk Matrix**:
   - `READ_ONLY` (Risk: 0.05): Queries and inspection commands.
   - `MODIFYING` (Risk: 0.35): Reversible state alterations.
   - `HIGH_RISK` (Risk: 0.70): Firewall rules, process kills, package removal.
   - `DESTRUCTIVE` (Risk: 1.00): Hard-blocked dangerous commands (`rm -rf /`, `mkfs`, raw block writes).
3. **Ephemeral Namespace CoW Sandbox Probe**:
   - Candidate remediation commands dry-run inside isolated User + Mount namespaces (`unshare` + OverlayFS).
4. **Rollback Synthesizer**:
   - Automatically computes reverse commands (`mv`, `systemctl`, `ufw delete`) for zero-loss recovery.

---

## 5. API Contracts

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | System health snapshot, distro info, and PSI pressure |
| `GET` | `/api/services` | List system services with load/active states |
| `POST` | `/api/services/action` | Start, stop, restart, reload, enable, disable, logs |
| `GET` | `/api/processes` | List active processes sorted by CPU/Memory |
| `POST` | `/api/processes/kill` | Send signal (SIGTERM/SIGKILL) to process PID |
| `GET` | `/api/storage/analysis` | Disk partitions, inode usage, large file discovery |
| `POST` | `/api/storage/organise` | Smart folder organization (dry-run & execute) |
| `POST` | `/api/storage/clean` | Clean temporary files and old logs |
| `GET` | `/api/network/status` | Network adapters, listening ports, firewall status |
| `POST` | `/api/network/firewall` | Add allow/deny firewall rule |
| `POST` | `/api/desktop/action` | Open folder, open file, open image, open browser, move, copy, trash |
| `POST` | `/api/download` | Streaming file download with auto-extraction |
| `POST` | `/api/diagnose` | Run 16-class taxonomy diagnostics, XAI, and DAG |
| `GET` | `/api/taxonomy/scenarios`| List all 16 Linux failure taxonomy scenarios |
| `POST` | `/api/execute` | AST-validated execution with sandbox dry-run and rollback |
| `POST` | `/api/rollback` | Execute state rollback command |
| `POST` | `/api/agent/chat` | AI conversational agent execution loop with `execute: bool` toggle |
| `GET` | `/api/stream/telemetry` | Server-Sent Events (SSE) live telemetry stream |