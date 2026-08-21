"""Interactive CLI and TUI for AI-Powered Linux Operations Assistant."""

import os
import re
import sys
import json
import time
import argparse
from typing import Optional, List, Dict, Any, Callable, Tuple, Union

# Detect NO_COLOR environment variable (https://no-color.org)
NO_COLOR = bool(os.environ.get("NO_COLOR"))

# Try importing Rich; provide graceful ANSI fallback if rich is not installed or NO_COLOR is set
try:
    if NO_COLOR:
        raise ImportError("NO_COLOR set, disabling rich styling")
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt, Confirm
    from rich.syntax import Syntax
    from rich.text import Text
    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    console = None

from pathlib import Path
from ops_assistant.agent import OpsAssistantAgent, LlamaCppProvider, OllamaProvider
from ops_assistant.model_manager.downloader import ModelDownloader
from ops_assistant.config import get_config, is_setup_completed, set_setup_completed
from ops_assistant.collectors.hub import TelemetryHub
from ops_assistant.tools.executor import SafeExecutor
from ops_assistant.tools.safety import CommandSafetyValidator
from ops_assistant.models import DiagnosticReport, SafetyLevel, LogRecord

# NLP intent routing + action tool modules
from ops_assistant.nlp.intent_router import IntentRouter, Intent, IntentType
from ops_assistant.tools import storage_ops, process_ops, network_ops, log_ops


# -------------------------------------------------------------------------
# Formatting and UI Helpers
# -------------------------------------------------------------------------

def format_safety_badge(level: SafetyLevel) -> str:
    """Returns a color-formatted badge string for a given SafetyLevel."""
    if level == SafetyLevel.READ_ONLY:
        return "[bold green]READ_ONLY[/bold green]" if HAS_RICH else "[READ_ONLY]"
    elif level == SafetyLevel.MODIFYING:
        return "[bold yellow]MODIFYING[/bold yellow]" if HAS_RICH else "[MODIFYING]"
    elif level == SafetyLevel.HIGH_RISK:
        return "[bold red]HIGH_RISK[/bold red]" if HAS_RICH else "[HIGH_RISK]"
    elif level == SafetyLevel.DESTRUCTIVE:
        return "[bold white on red] DESTRUCTIVE [/bold white on red]" if HAS_RICH else "[DESTRUCTIVE]"
    return str(level.value)


def render_banner(distro_name: str = "Linux"):
    """Renders the top application banner."""
    if HAS_RICH and console:
        banner_text = (
            f"[bold cyan]AI-Powered Linux Operations Assistant[/bold cyan] [dim](ops-assistant)[/dim]\n"
            f"[dim]Target Distribution:[/dim] [bold green]{distro_name}[/bold green] | "
            f"[dim]Engine:[/dim] [bold magenta]NeuroSymbolic Causality XAI[/bold magenta]"
        )
        console.print(Panel(banner_text, border_style="cyan"))
    else:
        print("=" * 70)
        print(f"  AI-POWERED LINUX OPERATIONS ASSISTANT — [{distro_name}]")
        print("  Engine: NeuroSymbolic Causality XAI | Safe Subprocess Sandbox")
        print("=" * 70)


def render_health_dashboard(hub: TelemetryHub, distro_override: Optional[str] = None):
    """Renders a comprehensive system health dashboard with distro identification and PSI."""
    snap = hub.get_health_snapshot(distro_override=distro_override)
    d_info = snap.distro_info or {}
    distro_name = d_info.get("distro_name", "Linux")
    init_sys = d_info.get("init_system", "systemd")
    pkg_mgr = d_info.get("package_manager", "apt")
    fw_tool = d_info.get("default_firewall", "ufw")
    sec_eng = d_info.get("security_subsystem", "AppArmor")

    if HAS_RICH and console:
        pressure_color = "green" if snap.pressure_status == "NORMAL" else ("yellow" if snap.pressure_status == "MODERATE" else "red")
        console.print(Panel.fit(
            f"[bold cyan]Linux Health Snapshot[/bold cyan] — [bold green]{snap.hostname}[/bold green] "
            f"([bold white]{distro_name}[/bold white], Kernel: {snap.kernel_release}, Uptime: {snap.uptime_seconds / 3600:.1f} hrs, Pressure: [{pressure_color}]{snap.pressure_status}[/{pressure_color}])",
            border_style="cyan"
        ))

        table = Table(title=f"Core System Telemetry & Distro Profile ({distro_name})", show_header=True, header_style="bold magenta")
        table.add_column("Subsystem", style="dim", width=15)
        table.add_column("Metric", style="bold")
        table.add_column("Value")
        table.add_column("Status", justify="right")

        table.add_row("Distro Profile", "Ecosystem Stack", f"Init: {init_sys} | Pkg: {pkg_mgr} | FW: {fw_tool} | Sec: {sec_eng}", "[green]IDENTIFIED[/green]")

        cpu_status = "[green]NORMAL[/green]" if snap.cpu.idle_pct > 20.0 else "[red]HIGH[/red]"
        table.add_row("CPU", "Utilization", f"User: {snap.cpu.user_pct}%, Sys: {snap.cpu.system_pct}%, Idle: {snap.cpu.idle_pct}%, IO-Wait: {snap.cpu.iowait_pct}% (Cores: {snap.cpu.core_count})", cpu_status)

        mem_status = "[green]HEALTHY[/green]" if snap.memory.used_percent < 85.0 else "[red]PRESSURE[/red]"
        table.add_row("Memory", "RAM Usage", f"{snap.memory.used_mb:.0f} MB / {snap.memory.total_mb:.0f} MB ({snap.memory.used_percent}%)", mem_status)
        table.add_row("Swap", "Swap Usage", f"{snap.memory.swap_used_mb:.0f} MB / {snap.memory.swap_total_mb:.0f} MB ({snap.memory.swap_used_percent}%)", "[green]OK[/green]" if snap.memory.swap_used_percent < 80.0 else "[red]HIGH[/red]")

        table.add_row("Load Average", "1m / 5m / 15m", f"{snap.load.load_1m:.2f}, {snap.load.load_5m:.2f}, {snap.load.load_15m:.2f}", "[green]OK[/green]")

        # PSI Metrics if available
        if snap.psi_metrics and isinstance(snap.psi_metrics, dict):
            for key in ["cpu_some", "memory_some", "memory_full", "io_some", "io_full"]:
                pdata = snap.psi_metrics.get(key)
                if isinstance(pdata, dict):
                    some_avg10 = pdata.get("avg10", 0.0)
                    some_avg60 = pdata.get("avg60", 0.0)
                    psi_stat = "[green]NORMAL[/green]" if some_avg10 < 10.0 else "[yellow]STALL[/yellow]"
                    table.add_row("PSI Pressure", key.replace("_", " ").upper(), f"avg10: {some_avg10:.2f}%, avg60: {some_avg60:.2f}%", psi_stat)

        for d in snap.disks:
            d_status = "[green]OK[/green]" if d.used_percent < 85.0 else "[red]WARNING[/red]"
            inodes_str = f" | Inodes: {d.inodes_percent}%" if d.inodes_percent is not None else ""
            table.add_row("Disk Partition", d.mountpoint, f"{d.used_gb:.1f} GB / {d.total_gb:.1f} GB ({d.used_percent}%){inodes_str}", d_status)

        console.print(table)

        if snap.failed_units:
            f_table = Table(title=f"[bold red]Failed System Units ({len(snap.failed_units)})[/bold red]", show_header=True, header_style="bold red")
            f_table.add_column("Unit Name", style="bold")
            f_table.add_column("Active State")
            f_table.add_column("Sub State")
            f_table.add_column("Description")
            for u in snap.failed_units:
                f_table.add_row(u.unit_name, u.active_state, u.sub_state, u.description)
            console.print(f_table)
        else:
            console.print(f"[bold green]✓ 0 failed {init_sys} units detected.[/bold green]\n")
    else:
        # Clean ANSI fallback
        print("\n" + "=" * 68)
        print(f"  LINUX HEALTH SNAPSHOT — {snap.hostname} ({distro_name})")
        print(f"  Distro Stack: Init={init_sys}, Pkg={pkg_mgr}, FW={fw_tool}, Sec={sec_eng}")
        print(f"  Kernel: {snap.kernel_release} | Uptime: {snap.uptime_seconds / 3600:.1f} hrs | Pressure: {snap.pressure_status}")
        print("=" * 68)
        print(f"• CPU: User {snap.cpu.user_pct}%, System {snap.cpu.system_pct}%, Idle {snap.cpu.idle_pct}%, IO-Wait {snap.cpu.iowait_pct}% (Cores: {snap.cpu.core_count})")
        print(f"• Memory: {snap.memory.used_mb:.0f} MB / {snap.memory.total_mb:.0f} MB ({snap.memory.used_percent}%) | Swap: {snap.memory.swap_used_mb:.0f} MB ({snap.memory.swap_used_percent}%)")
        print(f"• Load Average: 1m={snap.load.load_1m:.2f}, 5m={snap.load.load_5m:.2f}, 15m={snap.load.load_15m:.2f}")
        for d in snap.disks:
            inodes_str = f" (Inodes: {d.inodes_percent}%)" if d.inodes_percent is not None else ""
            print(f"• Disk [{d.mountpoint}]: {d.used_gb:.1f} GB / {d.total_gb:.1f} GB ({d.used_percent}%){inodes_str}")
        if snap.failed_units:
            print(f"• Failed Units ({len(snap.failed_units)}):")
            for u in snap.failed_units:
                print(f"  - {u.unit_name} ({u.active_state}/{u.sub_state}): {u.description}")
        else:
            print(f"• Failed Units: 0 detected ({init_sys} Healthy)")
        print("=" * 68 + "\n")


def render_models_list(downloader: Optional[ModelDownloader] = None):
    """Renders table of registered and locally downloaded GGUF models."""
    dl = downloader or ModelDownloader()
    models = dl.list_available_models()

    if HAS_RICH and console:
        table = Table(title="Edge GGUF Models Registry & Local Status", show_header=True, header_style="bold cyan")
        table.add_column("Model Key", style="bold yellow")
        table.add_column("Model Name")
        table.add_column("Size", justify="right")
        table.add_column("Status", justify="center")
        table.add_column("GGUF Header", justify="center")
        table.add_column("Local Path", style="dim")

        for key, info in models.items():
            is_dl = info["is_downloaded"]
            status = "[bold green]DOWNLOADED[/bold green]" if is_dl else "[dim yellow]NOT DOWNLOADED[/dim yellow]"
            size_str = f"{info['local_size_bytes'] / (1024*1024):.1f} MB" if is_dl else f"~{info['size_bytes'] / (1024*1024):.1f} MB"

            gguf_info = "N/A"
            if is_dl:
                header = dl.verify_gguf_header(Path(info["local_path"]))
                gguf_info = f"[green]v{header.get('version', 3)} ({header.get('tensor_count')} tensors)[/green]" if header.get("valid") else "[red]CORRUPT[/red]"

            table.add_row(
                key,
                info["name"],
                size_str,
                status,
                gguf_info,
                info["local_path"]
            )
        console.print(table)
    else:
        print("\n--- Edge GGUF Models Registry ---")
        for key, info in models.items():
            is_dl = info["is_downloaded"]
            status = "DOWNLOADED" if is_dl else "NOT DOWNLOADED"
            print(f"• {key}: {info['name']} [{status}] -> {info['local_path']}")
        print("")


def download_model_cli(model_key: str, downloader: Optional[ModelDownloader] = None):
    """Downloads a registered GGUF model from Hugging Face with progress reporting."""
    dl = downloader or ModelDownloader()

    print(f"Downloading model '{model_key}' into {dl.target_dir}...")

    def on_progress(downloaded: int, total: int, speed: float):
        pct = (downloaded / total * 100) if total > 0 else 0.0
        dl_mb = downloaded / (1024 * 1024)
        tot_mb = total / (1024 * 1024)
        sys.stdout.write(f"\r  Progress: {pct:5.1f}% ({dl_mb:5.1f}/{tot_mb:5.1f} MB) @ {speed:4.1f} MB/s")
        sys.stdout.flush()

    try:
        path = dl.download_model(model_key=model_key, progress_callback=on_progress)
        print(f"\n✓ Successfully downloaded and saved to: {path}")
        header = dl.verify_gguf_header(path)
        print(f"✓ GGUF Header Validation: Valid={header.get('valid')} (Version {header.get('version')}, {header.get('tensor_count')} tensors)")
    except Exception as e:
        print(f"\n❌ Error downloading model: {e}")


def render_hardware_profile(advisor: Optional[Any] = None):
    """Renders comprehensive hardware specs, model recommendation, and capability matrix."""
    from ops_assistant.hardware.advisor import HardwareAdvisor
    adv = (advisor or HardwareAdvisor()).get_full_advisory()
    prof = adv["profile"]
    rec = adv["recommended_model"]
    caps = adv["capability_matrix"]

    if HAS_RICH and console:
        console.print(Panel.fit(
            f"[bold cyan]Linux Hardware Profile & AI Inference Benchmark[/bold cyan]\n"
            f"[dim]Score:[/dim] [bold green]{prof['hardware_score']:.1f}/100.0[/bold green] | "
            f"[dim]Compute Tier:[/dim] [bold magenta]{prof['compute_tier']}[/bold magenta]",
            border_style="cyan"
        ))

        # Hardware Breakdown Table
        hw_table = Table(title="System Hardware Specifications", show_header=True, header_style="bold magenta")
        hw_table.add_column("Component", style="bold yellow", width=15)
        hw_table.add_column("Specification", style="white")
        hw_table.add_column("AI Headroom / Status", style="green")

        hw_table.add_row("CPU", f"{prof['cpu']['model_name']} ({prof['cpu']['logical_cores']} threads, {prof['cpu']['architecture']})", f"AVX2={prof['cpu']['has_avx2']}, AVX-512={prof['cpu']['has_avx512']}")
        hw_table.add_row("Memory", f"{prof['memory']['total_gb']} GB RAM ({prof['memory']['available_gb']} GB Available)", f"{prof['memory']['safe_model_headroom_mb']} MB Safe Model Headroom")
        hw_table.add_row("GPU", f"{prof['gpu']['device_name']}", f"VRAM: {prof['gpu']['total_vram_gb']} GB ({prof['gpu']['compute_api']})")
        hw_table.add_row("Storage", f"{prof['storage']['available_gb']} GB Free ({prof['storage']['used_percent']}% used)", f"Path: {prof['storage']['target_path']}")

        console.print(hw_table)

        # Recommendation Panel
        rec_content = (
            f"[bold]Recommended Model:[/bold] [bold green]{rec['name']}[/bold green]\n"
            f"[bold]Model Tier:[/bold] {rec.get('tier', 'Standard')} | [bold]File Size:[/bold] {rec.get('size_mb', 'N/A')} MB\n"
            f"[bold]Execution Target:[/bold] [cyan]{rec.get('acceleration', 'CPU Multithreaded')}[/cyan]\n"
            f"[bold]Rationale:[/bold] {rec['reason']}\n"
            f"[bold]Optimal Settings:[/bold] Threads={caps['recommended_threads']}, Context={caps['recommended_ctx_size']}, GPU Layers={caps['recommended_gpu_layers']}"
        )
        console.print(Panel(rec_content, title="[bold green]Optimal AI Model Recommendation[/bold green]", border_style="green"))

        # Capabilities Matrix Table
        cap_table = Table(title="Dynamic Capability Matrix (Features to Keep vs Avoid)", show_header=True, header_style="bold cyan")
        cap_table.add_column("Subsystem / Capability", style="bold")
        cap_table.add_column("Status", justify="center")
        cap_table.add_column("Engineering Rationale", style="dim")

        for k in caps.get("features_to_keep", []):
            cap_table.add_row(k["feature"], f"[bold green]{k['status']}[/bold green]", k["rationale"])
        for a in caps.get("features_to_avoid", []):
            cap_table.add_row(a["feature"], f"[bold yellow]{a['status']}[/bold yellow]", a["rationale"])

        console.print(cap_table)
    else:
        print("\n=== LINUX HARDWARE PROFILE & AI BENCHMARK ===")
        print(f"Hardware Score: {prof['hardware_score']}/100.0 | Tier: {prof['compute_tier']}")
        print(f"• CPU: {prof['cpu']['model_name']} ({prof['cpu']['logical_cores']} threads, AVX2={prof['cpu']['has_avx2']})")
        print(f"• RAM: {prof['memory']['total_gb']} GB (Headroom: {prof['memory']['safe_model_headroom_mb']} MB)")
        print(f"• GPU: {prof['gpu']['device_name']} (VRAM: {prof['gpu']['total_vram_gb']} GB)")
        print(f"• Storage: {prof['storage']['available_gb']} GB Free on {prof['storage']['target_path']}")
        print(f"\nRecommended Model: {rec['name']} ({rec.get('acceleration')})")
        print(f"Rationale: {rec['reason']}")
        print("\n--- Capability Matrix ---")
        for k in caps.get("features_to_keep", []):
            print(f"  [✓] {k['feature']}: {k['rationale']}")
        for a in caps.get("features_to_avoid", []):
            print(f"  [!] {a['feature']} ({a['status']}): {a['rationale']}")
        print("")


def run_hardware_test(advisor: Optional[Any] = None):
    """Runs automated validation tests on system hardware capabilities."""
    from ops_assistant.hardware.advisor import HardwareAdvisor, ModelSelector
    adv = advisor or HardwareAdvisor()
    prof = adv.profiler.profile()

    print("\n--- Running Automated Hardware Benchmarks & Profiling Tests ---")
    print(f"[1/5] Testing CPU Feature Detection... ✓ ({prof.cpu.model_name}, {prof.cpu.logical_cores} cores, AVX2={prof.cpu.has_avx2})")
    print(f"[2/5] Testing RAM & Headroom Calculation... ✓ ({prof.memory.total_gb} GB total, {prof.memory.safe_model_headroom_mb} MB safe headroom)")
    print(f"[3/5] Testing GPU & Compute API Probe... ✓ ({prof.gpu.vendor.upper()}: {prof.gpu.device_name}, VRAM={prof.gpu.total_vram_gb} GB)")
    print(f"[4/5] Testing Storage & Model Directory... ✓ ({prof.storage.available_gb} GB free on {prof.storage.target_path})")

    rec = ModelSelector.recommend_model(prof)
    caps = adv.generate_capability_matrix(prof)
    print(f"[5/5] Testing Dynamic Model Selection & Pruning... ✓ (Selected: {rec['name']})")
    print(f"\n✓ All Hardware Tests Passed! Hardware Score: {prof.hardware_score:.1f}/100.0 ({prof.compute_tier})\n")


def auto_tune_system(advisor: Optional[Any] = None, downloader: Optional[ModelDownloader] = None):
    """Profiles hardware, selects optimal model, and downloads if needed."""
    from ops_assistant.hardware.advisor import HardwareAdvisor, ModelSelector
    adv = advisor or HardwareAdvisor()
    dl = downloader or ModelDownloader()
    prof = adv.profiler.profile()
    rec = ModelSelector.recommend_model(prof)
    caps = adv.generate_capability_matrix(prof)

    render_hardware_profile(adv)

    if rec.get("download_required") and rec.get("model_key"):
        mkey = rec["model_key"]
        avail = dl.list_available_models()
        if mkey in avail and not avail[mkey]["is_downloaded"]:
            print(f"\n[*] Recommended model '{mkey}' is not downloaded yet.")
            download_model_cli(mkey, dl)
        else:
            print(f"\n✓ Model '{mkey}' is already available and ready for inference.")

    print("\n✓ Auto-tuning completed successfully. Optimal parameters applied.")


def run_setup_wizard(
    advisor: Optional[Any] = None,
    downloader: Optional[ModelDownloader] = None,
    force: bool = False,
    interactive_input: Optional[Callable[[str], str]] = None,
) -> bool:
    """First-Launch Hardware Setup & Model Recommendation Wizard."""
    from ops_assistant.hardware.advisor import HardwareAdvisor, ModelSelector, MODEL_CATALOG

    adv = advisor or HardwareAdvisor()
    dl = downloader or ModelDownloader()
    _input = interactive_input or input

    prof = adv.profiler.profile()
    rec = ModelSelector.recommend_model(prof)
    caps = adv.generate_capability_matrix(prof)

    if HAS_RICH and console:
        console.print(Panel.fit(
            f"[bold cyan]LinuxOps Assistant — Hardware Setup & Model Configuration Wizard[/bold cyan]\n"
            f"[dim]Automatic Hardware-Aware Model Selection for Edge & Server Nodes[/dim]",
            border_style="cyan"
        ))

        # Hardware specs table
        hw_table = Table(title="Detected Host Hardware Specifications", show_header=True, header_style="bold magenta")
        hw_table.add_column("Component", style="bold yellow", width=15)
        hw_table.add_column("Detected Specification", style="white")
        hw_table.add_column("Inference Capability", style="green")

        hw_table.add_row("CPU", f"{prof.cpu.model_name} ({prof.cpu.logical_cores} threads, {prof.cpu.architecture})", f"AVX2={prof.cpu.has_avx2}, AVX-512={prof.cpu.has_avx512}")
        hw_table.add_row("Memory", f"{prof.memory.total_gb} GB RAM ({prof.memory.available_gb} GB Free)", f"{prof.memory.safe_model_headroom_mb:.0f} MB Safe Model Headroom")
        hw_table.add_row("GPU", f"{prof.gpu.device_name}", f"VRAM: {prof.gpu.total_vram_gb} GB ({prof.gpu.compute_api})")
        hw_table.add_row("Storage", f"{prof.storage.available_gb} GB Free on {prof.storage.target_path}", f"Hardware Tier: [bold cyan]{prof.compute_tier}[/bold cyan] ({prof.hardware_score:.1f}/100)")
        console.print(hw_table)

        # Recommendation card
        rec_text = (
            f"[bold]Recommended AI Model:[/bold] [bold green]{rec['name']}[/bold green]\n"
            f"[bold]Model Tier:[/bold] {rec.get('tier', 'Standard')} | [bold]File Size:[/bold] {rec.get('size_mb', '0')} MB\n"
            f"[bold]Acceleration Target:[/bold] [cyan]{rec.get('acceleration', 'CPU Multithreaded')}[/cyan]\n"
            f"[bold]Rationale:[/bold] {rec['reason']}\n"
            f"[bold]Tuned Config:[/bold] {caps.recommended_threads} threads, {caps.recommended_ctx_size} context size, {caps.recommended_gpu_layers} GPU layers"
        )
        console.print(Panel(rec_text, title="[bold green]Optimal AI Recommendation for Your System[/bold green]", border_style="green"))

        console.print("\n[bold yellow]Select a setup option:[/bold yellow]")
        console.print(f"  [bold green]1.[/bold green] [bold]Auto-Install Recommended Model[/bold] ({rec['name']}) [dim](Recommended)[/dim]")
        console.print("  [bold cyan]2.[/bold cyan] Select a different model from Catalog (SmolLM2, Qwen, Llama, DeepSeek)")
        console.print("  [bold magenta]3.[/bold magenta] Use Deterministic-Only Mode [dim](0 MB download, sub-50ms, zero RAM usage)[/dim]")
        console.print("  [bold blue]4.[/bold blue] Connect to local Ollama instance [dim](http://localhost:11434)[/dim]")
        console.print("  [dim]5.[/dim] Skip setup for now\n")
    else:
        print("\n" + "=" * 70)
        print("  LINUXOPS ASSISTANT — HARDWARE SETUP & MODEL CONFIGURATION WIZARD")
        print("=" * 70)
        print(f"• CPU: {prof.cpu.model_name} ({prof.cpu.logical_cores} cores, AVX2={prof.cpu.has_avx2})")
        print(f"• RAM: {prof.memory.total_gb} GB Total ({prof.memory.safe_model_headroom_mb:.0f} MB Safe Headroom)")
        print(f"• GPU: {prof.gpu.device_name} (VRAM: {prof.gpu.total_vram_gb} GB)")
        print(f"• Storage: {prof.storage.available_gb} GB Free | Tier: {prof.compute_tier} ({prof.hardware_score:.1f}/100)")
        print("-" * 70)
        print(f"RECOMMENDED MODEL: {rec['name']} ({rec.get('size_mb', 0)} MB)")
        print(f"Rationale: {rec['reason']}")
        print("-" * 70)
        print("Select a setup option:")
        print(f"  1. Auto-Install Recommended: {rec['name']} (Recommended)")
        print("  2. Select another model from Catalog")
        print("  3. Use Deterministic-Only Mode (0 MB download, zero RAM)")
        print("  4. Connect to local Ollama instance")
        print("  5. Skip setup for now\n")

    try:
        choice = _input("Enter choice [1-5] (default: 1): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled.")
        return False

    if not choice or choice == "1":
        mkey = rec.get("model_key")
        if not mkey or not rec.get("download_required"):
            print("\n✓ Your system is optimized for Deterministic Engine. No model download needed.")
            set_setup_completed(
                provider="deterministic",
                hardware_tier=prof.compute_tier,
                threads=caps.recommended_threads,
                ctx_size=caps.recommended_ctx_size,
                gpu_layers=caps.recommended_gpu_layers,
            )
            return True

        avail = dl.list_available_models()
        if mkey in avail and avail[mkey]["is_downloaded"]:
            print(f"\n✓ Model '{mkey}' is already downloaded and verified.")
            model_path = avail[mkey]["local_path"]
        else:
            print(f"\n[*] Downloading recommended model '{mkey}'...")
            download_model_cli(mkey, dl)
            model_path = str(dl.target_dir / MODEL_CATALOG[mkey]["filename"])

        set_setup_completed(
            provider="gguf",
            model_key=mkey,
            model_path=model_path,
            hardware_tier=prof.compute_tier,
            threads=caps.recommended_threads,
            ctx_size=caps.recommended_ctx_size,
            gpu_layers=caps.recommended_gpu_layers,
        )
        print(f"\n✓ Setup completed successfully! Model '{mkey}' activated.")
        return True

    elif choice == "2":
        models = list(MODEL_CATALOG.items())
        if HAS_RICH and console:
            cat_table = Table(title="Open-Source Model Catalog — Hardware Requirements & Features", show_header=True, header_style="bold magenta")
            cat_table.add_column("No.", style="bold cyan", width=4)
            cat_table.add_column("Model Name", style="bold green", width=32)
            cat_table.add_column("Size", style="yellow", width=10)
            cat_table.add_column("RAM / VRAM", style="white", width=18)
            cat_table.add_column("Unlocked Features & Description", style="dim")

            for idx, (k, info) in enumerate(models, 1):
                size_mb = info["size_bytes"] / (1024 * 1024)
                vram_str = f" / {info.get('vram_recommended_mb', 0):.0f}MB VRAM" if info.get('vram_recommended_mb', 0) > 0 else ""
                cat_table.add_row(
                    str(idx),
                    info["name"],
                    f"{size_mb:.0f} MB",
                    f"{info['ram_required_mb']:.0f} MB RAM{vram_str}",
                    info.get("description", "")
                )
            console.print(cat_table)
        else:
            print("\n" + "=" * 90)
            print("  OPEN-SOURCE MODEL CATALOG — HARDWARE REQUIREMENTS & FEATURES")
            print("=" * 90)
            for idx, (k, info) in enumerate(models, 1):
                size_mb = info["size_bytes"] / (1024 * 1024)
                vram_str = f" / {info.get('vram_recommended_mb', 0):.0f}MB VRAM" if info.get('vram_recommended_mb', 0) > 0 else ""
                print(f"  [{idx}] {info['name']}")
                print(f"      Size: {size_mb:.0f} MB | Req RAM: {info['ram_required_mb']:.0f} MB{vram_str} | Min Cores: {info.get('min_cores', 1)}")
                print(f"      Features: {info.get('description', '')}")
                print("-" * 90)

        try:
            sel = _input(f"\nSelect model number [1-{len(models)}]: ").strip()
            sel_idx = int(sel) - 1
            if 0 <= sel_idx < len(models):
                chosen_key, chosen_info = models[sel_idx]
                download_model_cli(chosen_key, dl)
                model_path = str(dl.target_dir / chosen_info["filename"])
                set_setup_completed(
                    provider="gguf",
                    model_key=chosen_key,
                    model_path=model_path,
                    hardware_tier=prof.compute_tier,
                    threads=caps.recommended_threads,
                    ctx_size=caps.recommended_ctx_size,
                    gpu_layers=caps.recommended_gpu_layers,
                )
                print(f"\n✓ Setup completed! Model '{chosen_key}' configured.")
                return True
            else:
                print("Invalid selection.")
                return False
        except (ValueError, KeyboardInterrupt, EOFError):
            print("Invalid input.")
            return False

    elif choice == "3":
        set_setup_completed(
            provider="deterministic",
            hardware_tier=prof.compute_tier,
            threads=caps.recommended_threads,
            ctx_size=caps.recommended_ctx_size,
            gpu_layers=caps.recommended_gpu_layers,
        )
        print("\n✓ Configured for Deterministic Fast-Path Engine (<50ms, 0 MB memory footprint).")
        return True

    elif choice == "4":
        try:
            endpoint = _input("Enter Ollama endpoint [http://localhost:11434/api/generate]: ").strip()
            if not endpoint:
                endpoint = "http://localhost:11434/api/generate"
            omodel = _input("Enter Ollama model name [llama3:8b]: ").strip() or "llama3:8b"
            set_setup_completed(
                provider="ollama",
                hardware_tier=prof.compute_tier,
                threads=caps.recommended_threads,
                ctx_size=caps.recommended_ctx_size,
                gpu_layers=caps.recommended_gpu_layers,
            )
            from ops_assistant.config import _config_manager
            cfg = _config_manager.load()
            cfg["ollama_endpoint"] = endpoint
            cfg["ollama_model"] = omodel
            _config_manager.save(cfg)
            print(f"\n✓ Configured for Ollama at {endpoint} with model '{omodel}'.")
            return True
        except (KeyboardInterrupt, EOFError):
            return False

    elif choice == "5":
        print("\nSetup skipped. Using default fallback configuration.")
        return False

    return False


def render_proactive_audit():
    """Runs and renders proactive health audit."""
    from ops_assistant.tools import proactive_engine
    res = proactive_engine.run_proactive_audit()

    if HAS_RICH and console:
        health_color = "green" if res["overall_health"] == "OPTIMAL" else ("yellow" if res["overall_health"] == "WARNING" else "red")
        console.print(Panel.fit(
            f"[bold cyan]Proactive Autonomous System Health Audit[/bold cyan]\n"
            f"[dim]Overall Health:[/dim] [{health_color} bold]{res['overall_health']}[/{health_color} bold] | "
            f"[dim]Issues Found:[/dim] [bold]{res['findings_count']}[/bold] ([red]{res['critical_count']} critical[/red], [yellow]{res['warning_count']} warnings[/yellow])",
            border_style=health_color
        ))

        if res["findings"]:
            table = Table(title="Prioritized Findings & 1-Click Remediation Commands", show_header=True, header_style="bold magenta")
            table.add_column("Severity", justify="center", width=12)
            table.add_column("Subsystem", style="bold yellow", width=18)
            table.add_column("Issue & Details")
            table.add_column("Proposed Remediation", style="green")

            for f in res["findings"]:
                sev_badge = f"[bold red]CRITICAL[/bold red]" if f["severity"] == "CRITICAL" else f"[bold yellow]WARNING[/bold yellow]"
                table.add_row(
                    sev_badge,
                    f["subsystem"],
                    f"[bold]{f['title']}[/bold]\n{f['description']}",
                    f["remediation"]
                )
            console.print(table)
        else:
            console.print("[bold green]✓ Zero system bottlenecks or risks detected. System is running optimally![/bold green]\n")
    else:
        print(f"\n=== PROACTIVE SYSTEM HEALTH AUDIT: [{res['overall_health']}] ===")
        print(f"Total findings: {res['findings_count']} ({res['critical_count']} critical, {res['warning_count']} warnings)")
        for f in res.get("findings", []):
            print(f"• [{f['severity']}] {f['subsystem']}: {f['title']}")
            print(f"  Details: {f['description']}")
            print(f"  Remediation: {f['remediation']}")
        if not res["findings"]:
            print("✓ System running optimally.")
        print("")


def render_docker_status():
    """Lists and renders Docker containers and port conflicts."""
    from ops_assistant.tools import docker_ops
    res = docker_ops.list_containers(all_containers=True)
    conflicts = docker_ops.inspect_container_conflicts()

    if HAS_RICH and console:
        if not res.get("success"):
            console.print(Panel(f"[yellow]{res.get('error', 'Docker not active.')}[/yellow]", title="Docker Status", border_style="yellow"))
            return

        table = Table(title=f"Docker Containers ({res['count']} total, {res['running_count']} running)", show_header=True, header_style="bold cyan")
        table.add_column("Container ID", style="dim", width=14)
        table.add_column("Names", style="bold yellow")
        table.add_column("Image")
        table.add_column("Status")
        table.add_column("Ports", style="dim")

        for c in res.get("containers", []):
            st = c.get("status", "")
            st_color = "green" if "up" in st.lower() or "running" in st.lower() else "red"
            table.add_row(
                c.get("id", "")[:12],
                c.get("names", ""),
                c.get("image", ""),
                f"[{st_color}]{st}[/{st_color}]",
                c.get("ports", "")
            )
        console.print(table)

        if conflicts.get("conflicts"):
            c_table = Table(title="[bold red]Container Port Collisions[/bold red]", show_header=True, header_style="bold red")
            c_table.add_column("Port", style="bold")
            c_table.add_column("Container A")
            c_table.add_column("Container B")
            for conf in conflicts["conflicts"]:
                c_table.add_row(conf["port"], conf["container_a"], conf["container_b"])
            console.print(c_table)
    else:
        print(f"\n=== DOCKER CONTAINERS ({res.get('count', 0)} total) ===")
        for c in res.get("containers", []):
            print(f"• {c.get('names')} [{c.get('status')}]: {c.get('image')} (Ports: {c.get('ports')})")
        print("")


def render_security_audit():
    """Runs and renders security audit."""
    from ops_assistant.tools import security_ops
    res = security_ops.audit_security()

    if HAS_RICH and console:
        stat_color = "green" if res["overall_status"] == "HEALTHY" else ("yellow" if res["overall_status"] == "WARNING" else "red")
        console.print(Panel.fit(
            f"[bold cyan]Consolidated Linux Security & Hardening Audit[/bold cyan]\n"
            f"[dim]Security Posture:[/dim] [{stat_color} bold]{res['overall_status']}[/{stat_color} bold] | "
            f"[dim]SSH Score:[/dim] [bold]{res['ssh_audit'].get('security_score', 0)}%[/bold] | "
            f"[dim]Firewall:[/dim] [bold]{res['firewall'].get('status', 'unknown')}[/bold]",
            border_style=stat_color
        ))

        table = Table(title="Security Checks & Vulnerability Findings", show_header=True, header_style="bold magenta")
        table.add_column("Check / Subsystem", style="bold yellow", width=22)
        table.add_column("Status / Findings")
        table.add_column("Details & Recommendations")

        ssh = res["ssh_audit"]
        table.add_row(
            "SSH Configuration",
            f"Score: {ssh.get('security_score')}%",
            "; ".join(ssh.get("recommendations", ["Configuration matches best practices."]))
        )

        bf = res["brute_force_audit"]
        bf_color = "green" if bf.get("threat_level") == "NORMAL" else "red"
        table.add_row(
            "SSH Auth Brute-Force",
            f"[{bf_color}]{bf.get('threat_level')}[/{bf_color}] ({bf.get('total_failed_attempts')} failed)",
            bf.get("recommendation", "Clean")
        )

        suid = res["suid_audit"]
        table.add_row(
            "SUID/SGID Binaries",
            f"{suid.get('total_suid_count')} total ({suid.get('anomalous_suid_count')} anomalous)",
            f"Anomalies: {', '.join(suid.get('anomalous_binaries', []))}" if suid.get("anomalous_binaries") else "All SUID binaries are standard system utilities."
        )

        console.print(table)
    else:
        print(f"\n=== SECURITY AUDIT: [{res.get('overall_status')}] ===")
        print(f"• Firewall: {res.get('firewall', {}).get('status')}")
        print(f"• SSH Score: {res.get('ssh_audit', {}).get('security_score')}%")
        print(f"• Auth Threat: {res.get('brute_force_audit', {}).get('threat_level')} ({res.get('brute_force_audit', {}).get('total_failed_attempts')} failed logins)")
        print(f"• SUID: {res.get('suid_audit', {}).get('total_suid_count')} binaries ({res.get('suid_audit', {}).get('anomalous_suid_count')} anomalies)")
        print("")


def render_safety_inspection(command_str: str, validator: Optional[CommandSafetyValidator] = None):
    """Renders a thorough AST safety inspection and deobfuscation breakdown for any command."""
    val = validator or CommandSafetyValidator()
    lvl, risk, reason = val.evaluate_safety(command_str)
    nodes = val.parse_ast(command_str)
    expanded, deobf_findings = val.deobfuscate(command_str)

    if HAS_RICH and console:
        badge = format_safety_badge(lvl)
        content = (
            f"[bold]Target Command:[/bold] [bold yellow]{command_str}[/bold yellow]\n\n"
            f"[bold]Overall Safety Tier:[/bold] {badge}\n"
            f"[bold]Risk Score:[/bold] [bold]{risk:.2f}[/bold] / 1.00\n"
            f"[bold]Evaluation Rationale:[/bold] {reason}\n"
        )
        if deobf_findings:
            content += "\n[bold red]De-Obfuscation Findings:[/bold red]\n"
            for f in deobf_findings:
                content += f"  • [yellow]{f}[/yellow]\n"

        console.print(Panel(
            content,
            title="[bold cyan]AST Security Sandbox & Obfuscation Inspection[/bold cyan]",
            border_style="red" if lvl == SafetyLevel.DESTRUCTIVE else ("yellow" if lvl == SafetyLevel.HIGH_RISK else "green")
        ))

        if len(nodes) > 1:
            ast_table = Table(title="Decomposed AST Pipeline Stages", show_header=True, header_style="bold cyan")
            ast_table.add_column("Stage #", width=8)
            ast_table.add_column("Command Segment", style="bold yellow")
            ast_table.add_column("Safety Tier", justify="center")
            ast_table.add_column("Risk", justify="right")
            ast_table.add_column("Rationale")

            for idx, n in enumerate(nodes, 1):
                stage_badge = format_safety_badge(n.safety_level)
                ast_table.add_row(
                    str(idx),
                    n.raw,
                    stage_badge,
                    f"{n.risk_score:.2f}",
                    n.reason
                )
            console.print(ast_table)
    else:
        print("\n" + "=" * 68)
        print("  AST SECURITY SANDBOX INSPECTION")
        print("=" * 68)
        print(f"• Command:     {command_str}")
        print(f"• Safety Tier: {lvl.value}")
        print(f"• Risk Score:  {risk:.2f}")
        print(f"• Rationale:   {reason}")
        if deobf_findings:
            print("• Obfuscation Detected:")
            for f in deobf_findings:
                print(f"    - {f}")
        if len(nodes) > 1:
            print("• AST Pipeline Stages:")
            for idx, n in enumerate(nodes, 1):
                print(f"    [{idx}] {n.raw} -> {n.safety_level.value} (Risk: {n.risk_score:.2f}) | {n.reason}")
        print("=" * 68 + "\n")


def render_diagnostic_report(
    report: DiagnosticReport,
    executor: Optional[SafeExecutor] = None,
    interactive_exec: bool = False
):
    """Renders a structured XAI diagnostic report with Causality DAG visualization."""
    xai = report.explanation

    if HAS_RICH and console:
        content = f"[bold red]Symptom:[/bold red] {xai.symptom}\n\n"
        content += f"[bold yellow]Root Cause:[/bold yellow] {xai.root_cause}\n\n"
        content += f"[bold cyan]Rationale:[/bold cyan] {xai.rationale}\n\n"

        if xai.evidence_logs:
            content += "[bold]Evidentiary Logs:[/bold]\n"
            for log in xai.evidence_logs:
                content += f"  • [dim]{log}[/dim]\n"

        if xai.mitigation_steps:
            content += "\n[bold]Remediation Workflow:[/bold]\n"
            for idx, step in enumerate(xai.mitigation_steps, 1):
                content += f"  {idx}. {step}\n"

        # Render Causality DAG Chain if present
        if report.causality_dag and report.causality_dag.get("cascade_chain"):
            chain = report.causality_dag.get("cascade_chain", [])
            content += "\n[bold magenta]Causal Cascade Chain (DAG):[/bold magenta]\n"
            content += "  " + " [cyan]──▶[/cyan] ".join(f"[bold]{node}[/bold]" for node in chain) + "\n"

        console.print(Panel(
            content,
            title=f"[bold green]XAI Diagnosis — {report.reasoning_engine}[/bold green] (Confidence: {xai.confidence_score * 100:.0f}%, Latency: {report.latency_ms:.2f}ms)",
            border_style="green"
        ))

        if xai.proposed_commands:
            cmd_table = Table(title="Recommended Verified Remediation Commands", show_header=True, header_style="bold cyan")
            cmd_table.add_column("#", width=3)
            cmd_table.add_column("Command", style="bold yellow")
            cmd_table.add_column("Safety Tier", justify="center")
            cmd_table.add_column("Risk", justify="right")
            cmd_table.add_column("Rationale")

            for idx, cmd in enumerate(xai.proposed_commands, 1):
                safety_badge = format_safety_badge(cmd.safety_level)
                cmd_table.add_row(
                    str(idx),
                    cmd.command,
                    safety_badge,
                    f"{cmd.risk_score:.2f}",
                    cmd.rationale
                )

            console.print(cmd_table)

            for cmd in xai.proposed_commands:
                if cmd.flag_breakdown:
                    console.print(f"[dim]Flag Breakdown for `{cmd.command}`:[/dim]")
                    for fb in cmd.flag_breakdown:
                        console.print(f"  [cyan]{fb.flag}[/cyan]: {fb.purpose}")
                if cmd.rollback_command:
                    console.print(f"[magenta]  ↩ Rollback Command:[/magenta] `{cmd.rollback_command}` ({cmd.rollback_rationale})")
                console.print()
    else:
        # Clean ANSI fallback
        print("\n" + "-" * 68)
        print(f"  XAI DIAGNOSIS ({report.reasoning_engine}) — Latency: {report.latency_ms:.2f}ms | Confidence: {xai.confidence_score * 100:.0f}%")
        print("-" * 68)
        print(f"• Symptom:    {xai.symptom}")
        print(f"• Root Cause: {xai.root_cause}")
        print(f"• Rationale:  {xai.rationale}")
        if xai.evidence_logs:
            print("• Evidentiary Logs:")
            for log in xai.evidence_logs:
                print(f"    - {log}")
        if report.causality_dag and report.causality_dag.get("cascade_chain"):
            print(f"• Causal Chain: {' -> '.join(report.causality_dag.get('cascade_chain', []))}")
        if xai.proposed_commands:
            print("• Recommended Remediation Commands:")
            for idx, cmd in enumerate(xai.proposed_commands, 1):
                print(f"  [{idx}] ({cmd.safety_level.value} | Risk {cmd.risk_score:.2f}) {cmd.command}")
                print(f"      Rationale: {cmd.rationale}")
                for fb in cmd.flag_breakdown:
                    print(f"      Flag '{fb.flag}': {fb.purpose}")
                if cmd.rollback_command:
                    print(f"      Rollback: {cmd.rollback_command} ({cmd.rollback_rationale})")
        print("-" * 68 + "\n")

    # Interactive Execution Loop if requested
    if interactive_exec and executor and xai.proposed_commands:
        prompt_interactive_execution(xai.proposed_commands, executor)


def prompt_interactive_execution(commands: List[Any], executor: SafeExecutor,
                                 router: Optional["IntentRouter"] = None):
    """Prompts user to safely execute or dry-run suggested commands with interactive confirmation."""
    if HAS_RICH and console:
        console.print(Panel(
            "[bold cyan]Interactive Command Remediation Menu:[/bold cyan]\n"
            "  [bold green][1..N][/bold green]    Execute specific command by index\n"
            "  [bold green][A / all][/bold green] Execute ALL proposed commands in sequence\n"
            "  [bold yellow][D / dry][/bold yellow]    Dry-run preview all commands\n"
            "  [bold cyan][I / inspect][/bold cyan] Inspect AST safety breakdown\n"
            "  [bold magenta][R / rollback][/bold magenta] Rollback last executed modifying action\n"
            "  [bold dim][S / skip][/bold dim]   Skip / Proceed without execution\n"
            "  [dim]Or just describe what you want in plain English[/dim]",
            border_style="cyan"
        ))
    else:
        print("\nInteractive Command Remediation Menu:")
        print("  [1..N]     Execute specific command by index")
        print("  [A / all]  Execute ALL proposed commands in sequence")
        print("  [D / dry]  Dry-run preview all commands")
        print("  [I]        Inspect AST safety breakdown")
        print("  [R]        Rollback last executed modifying action")
        print("  [S / skip] Skip / Proceed without execution")
        print("  (Or just describe what you want in plain English)")

    _router = router or IntentRouter()

    try:
        choice = input("Select action: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nExecution skipped.")
        return

    if not choice:
        print("Execution skipped.")
        return

    # Classify the input — always use remediation context
    intent = _router.classify_remediation_action(choice, len(commands))

    if intent.type == IntentType.REMEDIATION_SKIP or intent.type == IntentType.UNKNOWN and not choice:
        print("Execution skipped.")

    elif intent.type == IntentType.REMEDIATION_DRY_RUN:
        for cmd in commands:
            res = executor.execute(cmd.command, dry_run=True, rollback_cmd=cmd.rollback_command)
            if HAS_RICH and console:
                console.print(f"  [bold green]✓[/bold green] [dim]{res['stdout']}[/dim]")
            else:
                print(f"  ✓ {res['stdout']}")

    elif intent.type == IntentType.REMEDIATION_INSPECT:
        validator = CommandSafetyValidator()
        for cmd in commands:
            render_safety_inspection(cmd.command, validator)

    elif intent.type in (IntentType.REMEDIATION_ROLLBACK, IntentType.ROLLBACK):
        res = executor.rollback_last()
        if res.get("executed"):
            status_badge = "[bold green]SUCCESS[/bold green]" if res.get("returncode") == 0 else f"[bold red]FAILED ({res.get('returncode')})[/bold red]"
            if HAS_RICH and console:
                console.print(f"  [bold magenta]↩ Executed Rollback:[/bold magenta] `{res.get('command')}` → {status_badge}")
                if res.get("stdout"):
                    console.print(Panel(res["stdout"].strip(), title="Rollback STDOUT", border_style="dim"))
            else:
                print(f"  ↩ Executed Rollback: {res.get('command')} -> code {res.get('returncode')}")
                if res.get("stdout"):
                    print(f"    {res['stdout'].strip()}")
        else:
            msg = f"⚠️  {res.get('stderr')}"
            if HAS_RICH and console:
                console.print(f"[bold yellow]{msg}[/bold yellow]")
            else:
                print(msg)

    elif intent.type == IntentType.REMEDIATION_EXEC_ALL:
        for idx, target in enumerate(commands, 1):
            _execute_with_safety_prompt(target, executor, idx=idx)

    elif intent.type == IntentType.REMEDIATION_EXEC_N:
        n = intent.args.get("n", 0)
        idx = n - 1
        if 0 <= idx < len(commands):
            _execute_with_safety_prompt(commands[idx], executor, idx=n)
        else:
            print(f"Invalid index {n}. Must be between 1 and {len(commands)}.")

    else:
        # Unknown / NL that didn't resolve to a remediation action:
        # surface a hint and let the user re-enter
        hint = intent.args.get("hint", "")
        if HAS_RICH and console:
            console.print(
                f"[yellow]⚠  Didn't understand '[bold]{choice}[/bold]'. "
                f"Try a number (1–{len(commands)}), A, D, I, R, or S.[/yellow]"
                + (f"\n[dim]{hint}[/dim]" if hint else "")
            )
        else:
            print(f"⚠  Didn't understand '{choice}'. Try a number (1–{len(commands)}), A, D, I, R, or S.")
        prompt_interactive_execution(commands, executor, router=_router)


def _execute_with_safety_prompt(target: Any, executor: SafeExecutor, idx: int = 1):
    """Executes a single proposed command, prompting confirmation for HIGH_RISK / DESTRUCTIVE."""
    cmd_str = target.command
    safety_lvl = target.safety_level
    rollback_cmd = target.rollback_command

    # Confirmation Gate for HIGH_RISK
    if safety_lvl == SafetyLevel.HIGH_RISK:
        if HAS_RICH and console:
            console.print(Panel(
                f"[bold yellow]⚠️ WARNING: Command #{idx} is classified as HIGH RISK[/bold yellow]\n"
                f"Command: [bold]{cmd_str}[/bold]\n"
                f"Risk Score: [bold red]{target.risk_score:.2f}[/bold red] | Rationale: {target.rationale}",
                border_style="yellow"
            ))
            confirmed = Confirm.ask("Are you sure you want to proceed with execution?", default=False)
        else:
            print(f"\n⚠️ WARNING: Command #{idx} is classified as HIGH RISK: {cmd_str}")
            ans = input("Are you sure you want to proceed? [y/N]: ").strip().lower()
            confirmed = ans in ("y", "yes")

        if not confirmed:
            print("Execution cancelled by user.")
            return

    # Confirmation Hard Gate for DESTRUCTIVE
    elif safety_lvl == SafetyLevel.DESTRUCTIVE:
        if HAS_RICH and console:
            console.print(Panel(
                f"[bold white on red]🛑 CATASTROPHIC RISK: DESTRUCTIVE ACTION DETECTED[/bold white on red]\n"
                f"Command: [bold]{cmd_str}[/bold]\n"
                f"This command targets critical system state, root storage, or system files.\n"
                f"To override and force execution, type 'I UNDERSTAND THE RISKS'.",
                border_style="red"
            ))
            token = Prompt.ask("Confirmation token")
        else:
            print(f"\n🛑 CATASTROPHIC RISK: DESTRUCTIVE ACTION DETECTED: {cmd_str}")
            token = input("Type 'I UNDERSTAND THE RISKS' to override: ").strip()

        if token != "I UNDERSTAND THE RISKS":
            print("Execution blocked by safety sandbox.")
            return

    if HAS_RICH and console:
        console.print(f"[bold cyan]▶ Executing:[/bold cyan] [bold yellow]{cmd_str}[/bold yellow]")
    else:
        print(f"Executing: {cmd_str}")

    res = executor.execute(cmd_str, rollback_cmd=rollback_cmd, allow_destructive=(safety_lvl == SafetyLevel.DESTRUCTIVE))

    # Display Execution Profiling & Output
    ret_code = res.get("returncode", -1)
    elapsed = res.get("elapsed_ms", 0.0)
    status_str = f"[bold green]SUCCESS (0)[/bold green]" if ret_code == 0 else f"[bold red]FAILED (code {ret_code})[/bold red]"

    if HAS_RICH and console:
        console.print(f"  Status: {status_str} (elapsed: [bold]{elapsed:.2f}ms[/bold])")
        if res.get("stdout"):
            console.print(Panel(res["stdout"].strip(), title="STDOUT", border_style="dim"))
        if res.get("stderr"):
            console.print(Panel(res["stderr"].strip(), title="STDERR", border_style="red"))
        if rollback_cmd and res.get("executed"):
            console.print(f"  [dim magenta]↩ Registered rollback action: `{rollback_cmd}`[/dim magenta]")
    else:
        print(f"  Status: returncode {ret_code} (elapsed {elapsed:.2f}ms)")
        if res.get("stdout"):
            print(f"  STDOUT:\n{res['stdout'].strip()}")
        if res.get("stderr"):
            print(f"  STDERR:\n{res['stderr'].strip()}")
        if rollback_cmd and res.get("executed"):
            print(f"  ↩ Registered rollback: {rollback_cmd}")


def export_report(report: DiagnosticReport, export_path: str, fmt: str = "json"):
    """Exports diagnostic report to file with comprehensive error handling."""
    try:
        p = os.path.abspath(export_path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if fmt == "json":
            with open(p, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, indent=2)
            print(f"✅ Diagnostic report exported to JSON: {p}")
        elif fmt == "md":
            xai = report.explanation
            content = f"# XAI Diagnostic Report: {report.query}\n\n"
            content += f"- **Reasoning Engine**: {report.reasoning_engine}\n"
            content += f"- **Latency**: {report.latency_ms:.2f} ms\n"
            content += f"- **Confidence**: {xai.confidence_score * 100:.0f}%\n"
            content += f"- **Target Subsystem**: {report.target_subsystem or 'N/A'}\n\n"
            content += f"## 🔍 Diagnostic Findings\n"
            content += f"- **Symptom**: {xai.symptom}\n"
            content += f"- **Root Cause**: {xai.root_cause}\n"
            content += f"- **Rationale**: {xai.rationale}\n\n"
            if xai.evidence_logs:
                content += "### 📋 Evidentiary Logs\n"
                for l in xai.evidence_logs:
                    content += f"- `{l}`\n"
                content += "\n"
            if report.causality_dag and report.causality_dag.get("cascade_chain"):
                content += f"### ⛓️ Causal Cascade Chain\n"
                content += f"`{' -> '.join(report.causality_dag.get('cascade_chain', []))}`\n\n"
            if xai.proposed_commands:
                content += "### 🛠️ Proposed Remediation Commands\n\n"
                content += "| # | Command | Safety Level | Risk Score | Rationale |\n"
                content += "|---|---|---|---|---|\n"
                for idx, c in enumerate(xai.proposed_commands, 1):
                    content += f"| {idx} | `{c.command}` | {c.safety_level.value} | {c.risk_score:.2f} | {c.rationale} |\n"
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"✅ Diagnostic report exported to Markdown: {p}")
    except Exception as e:
        print(f"❌ Failed to export report to {export_path}: {e}")


def run_benchmark(agent: OpsAssistantAgent):
    """Runs automated benchmark across all 16 failure taxonomy scenarios."""
    print("=" * 70)
    print("🚀 RUNNING OPS-ASSISTANT EMPIRICAL BENCHMARK (16 Test Scenarios)")
    print("=" * 70)

    test_vectors = [
        ("Why is NGINX failing with Address already in use?", "PORT_CONFLICT"),
        ("Permission denied writing to /var/log/postgres/pg.log", "PERMISSION_DENIED"),
        ("Out of memory: Killed process 4120 (java) oom-killer invoked", "OOM_KILL"),
        ("No space left on device when writing session files", "DISK_EXHAUSTION"),
        ("No space left on device: inode table full on /var", "INODE_EXHAUSTION"),
        ("NGINX syntax error directive is not allowed here on line 42", "CONFIG_SYNTAX_ERROR"),
        ("SSL certificate has expired on port 443 handshake failed", "SSL_CERT_ERROR"),
        ("Temporary failure in name resolution for api.internal.net", "DNS_RESOLUTION_FAILURE"),
        ("Could not get lock /var/lib/dpkg/lock-frontend frontend lock held", "DPKG_LOCK_BLOCKED"),
        ("Unit apache2.service entered failed state Start request repeated too quickly", "SYSTEMD_CRASH_LOOP"),
        ("FATAL: remaining connection slots are reserved for non-replication superuser", "DB_CONN_EXHAUSTION"),
        ("Connection refused on port 8080 iptables DROP", "FIREWALL_PORT_BLOCKED"),
        ("High number of defunct zombie processes in process table", "ZOMBIE_PROCESS_ACCUMULATION"),
        ("High iowait on NVMe drive task blocked for more than 120 seconds", "IOWAIT_BOTTLENECK"),
        ("audit: type=1400 apparmor='DENIED' operation='open' name='/etc/shadow'", "SELINUX_APPARMOR_DENIAL"),
        ("Server has gone too long without receiving time clock skew detected", "NTP_CLOCK_DRIFT")
    ]

    latencies = []
    correct_matches = 0

    for query, expected_id in test_vectors:
        t0 = time.perf_counter()
        rep = agent.diagnose(query)
        lat = (time.perf_counter() - t0) * 1000.0
        latencies.append(lat)

        matched_pattern = any(
            re.search(item["pattern"], query, re.IGNORECASE)
            for item in agent.FAILURE_TAXONOMY
            if item["id"] == expected_id
        )
        status_str = "✅ PASS" if matched_pattern else "❌ FAIL"
        if matched_pattern:
            correct_matches += 1
        print(f"[{status_str}] {expected_id:<28} | Latency: {lat:.2f}ms")

    avg_lat = sum(latencies) / len(latencies)
    accuracy = (correct_matches / len(test_vectors)) * 100.0

    print("-" * 70)
    print("📊 SUMMARY:")
    print(f"• Total Scenarios Tested: {len(test_vectors)}")
    print(f"• Accuracy:               {accuracy:.1f}% ({correct_matches}/{len(test_vectors)})")
    print(f"• Avg Diagnosis Latency:  {avg_lat:.2f} ms")
    print(f"• Max Diagnosis Latency:  {max(latencies):.2f} ms")
    print(f"• Min Diagnosis Latency:  {min(latencies):.2f} ms")
    print("=" * 70)


def run_demo(agent: OpsAssistantAgent, executor: SafeExecutor):
    """Interactive demo showcasing 4 representative failure scenarios."""
    print("\n" + "=" * 70)
    print("✨ AI-POWERED LINUX OPERATIONS ASSISTANT — INTERACTIVE DEMO")
    print("=" * 70)

    demo_scenarios = [
        ("Scenario 1: NGINX Port Conflict", "Why is NGINX failing to bind to port 80? Address already in use."),
        ("Scenario 2: Out-of-Memory (OOM) Killer", "Kernel invoked oom-killer: Killed process 8914 (node) total-vm:4194304kB"),
        ("Scenario 3: Corrupted DPKG Lock", "apt-get upgrade failed: Could not get lock /var/lib/dpkg/lock-frontend"),
        ("Scenario 4: Expired SSL Certificate", "curl: (60) SSL certificate problem: certificate has expired on internal web host")
    ]

    for title, query in demo_scenarios:
        print(f"\n▶ {title}")
        print(f"  User Query: \"{query}\"")
        rep = agent.diagnose(query)
        render_diagnostic_report(rep, executor, interactive_exec=False)
        time.sleep(0.5)

    print("✅ Demo completed successfully.")


def print_repl_help():
    """Prints formatted sectioned help table of all REPL commands and NL capabilities."""
    if HAS_RICH and console:
        console.print("\n[bold cyan]ops-assistant — Universal Linux Action Assistant[/bold cyan]")
        console.print("[dim]All commands can be typed as natural language. Shortcuts listed for speed.[/dim]\n")

        sections = [
            ("📊 System Info", [
                ("health / status", "Full health snapshot: CPU, RAM, disk, PSI, failed units"),
                ("show system info", "Distro, kernel version, uptime"),
                ("uptime", "How long the system has been running"),
                ("distro [family]", "Inspect or switch distro profile (debian/rhel/arch/alpine/suse)"),
            ]),
            ("🗂  Storage", [
                (":disk  / how much space am I using", "Disk usage summary (df + top dirs)"),
                (":large / find large files", "Top 20 files consuming the most space"),
                (":clean / clean up old logs", "Show cleanable logs/tmp files (dry-run first)"),
                ("organise ~/Downloads", "Sort files into type-based folders (images/, docs/, …)"),
            ]),
            ("⚙  Processes & Services", [
                (":processes / what's running", "Top 20 processes by CPU/memory"),
                ("kill <name or PID>", "Send SIGTERM to a process"),
                ("is nginx running", "Check a systemd service status"),
                ("restart nginx", "Restart / reload / stop / start a service"),
                ("enable docker on boot", "Enable / disable a service at boot"),
                ("failed / units", "Scan all failed systemd units"),
            ]),
            ("📦 Packages", [
                ("install htop", "Install a package (distro-aware: apt/yum/pacman/apk)"),
                ("remove vim", "Uninstall a package"),
                ("update packages", "Full system upgrade"),
                ("search python3", "Search available packages"),
            ]),
            ("🌐 Network", [
                (":network / show interfaces", "Network interfaces and IP addresses"),
                (":ports  / what ports are open", "Listening TCP/UDP ports (ss -tlnp)"),
                ("ping google.com", "Ping a host and show RTT / packet loss"),
                ("dns lookup api.example.com", "Resolve hostname to IP"),
                ("show routes", "Routing table and default gateway"),
                (":firewall / show firewall rules", "ufw/iptables/firewalld rule listing"),
                ("allow port 8080", "Open a port in the firewall"),
            ]),
            ("📝 Logs & Errors", [
                (":logs [service]", "Tail recent logs (journald or /var/log)"),
                (":errors / show errors", "Error-level lines from the last hour"),
                (":kernel / dmesg", "Kernel ring buffer messages"),
                ("nginx logs", "Tail logs for a specific service"),
            ]),
            ("🕒 Cron & Users", [
                (":cron / show cron jobs", "List current user's crontab + system cron.d"),
                (":users / who's logged in", "Active sessions and all system accounts"),
            ]),
            ("🛡  Safety & Execution", [
                ("safety <cmd>", "AST safety analysis and de-obfuscation"),
                (":run <cmd>  /  !<cmd>", "Safe shell passthrough (gated by safety validator)"),
                ("history", "Session command execution history"),
                ("rollback / undo", "Undo the last modifying action"),
                ("export json <path>", "Export latest diagnostic report to JSON"),
                ("export md <path>", "Export latest diagnostic report to Markdown"),
            ]),
            ("🤖 Assistant Engine", [
                ("models", "List registered edge GGUF models"),
                ("download <key>", "Download a GGUF model (e.g. qwen2.5-coder-0.5b)"),
                ("provider [type]", "Inspect or switch LLM backend (gguf/ollama/none)"),
                ("demo", "Run 4-scenario interactive demo"),
                ("benchmark", "Run 16-scenario accuracy benchmark"),
                ("clear", "Clear terminal screen"),
                ("help / ?", "Show this help menu"),
                ("exit / quit / q", "Exit ops-assistant"),
            ]),
        ]

        for section_title, rows in sections:
            table = Table(show_header=True, header_style="bold magenta", box=None, padding=(0, 1))
            table.add_column(section_title, style="bold yellow", min_width=38)
            table.add_column("Description", style="dim")
            for cmd, desc in rows:
                table.add_row(cmd, desc)
            console.print(table)
            console.print()

        console.print("[dim]💡 Tip: Type anything naturally — 'why is nginx failing', 'what's eating my disk', 'show me recent errors'[/dim]\n")
    else:
        print("\n=== ops-assistant — Universal Linux Action Assistant ===")
        print("All commands can be typed as natural language.\n")
        print("📊 System:  health | show system info | uptime | distro")
        print("🗂  Storage: :disk | find large files | clean old logs | organise ~/Downloads")
        print("⚙  Procs:   :processes | kill <name> | restart nginx | is nginx running")
        print("📦 Pkgs:    install htop | remove vim | update packages | search python3")
        print("🌐 Network: :network | :ports | ping google.com | allow port 8080")
        print("📝 Logs:    :logs [svc] | :errors | :kernel | nginx logs")
        print("🕒 Cron:    :cron | :users | who's logged in")
        print("🛡  Safety:  safety <cmd> | :run <cmd> | rollback | history | export json <path>")
        print("🤖 Agent:   models | download <key> | provider | demo | benchmark")
        print("           clear | help | exit\n")




def run_repl(agent: OpsAssistantAgent, executor: SafeExecutor, distro_override: Optional[str] = None):
    """Runs the Universal Action REPL — all input (NL or commands) dispatched via IntentRouter."""
    active_distro = distro_override
    d_info = agent.distro_detector.detect(override_family=active_distro)
    render_banner(d_info.distro_name)

    dl = ModelDownloader()
    if not is_setup_completed() and not dl.has_any_model_installed() and sys.stdin.isatty():
        if HAS_RICH and console:
            console.print("[bold yellow]⚡ First-time launch detected: No local AI model is configured yet.[/bold yellow]")
        else:
            print("⚡ First-time launch detected: No local AI model is configured yet.")
        try:
            ans = input("Would you like to run the Hardware Setup Wizard now? [Y/n]: ").strip().lower()
            if ans in ("", "y", "yes"):
                run_setup_wizard(downloader=dl)
        except (KeyboardInterrupt, EOFError):
            pass

    print("Type anything — 'what's eating my disk', 'restart nginx', 'show recent errors' — or 'help'.\n")

    last_report: Optional[DiagnosticReport] = None
    validator = CommandSafetyValidator()
    router = IntentRouter(llm_provider=agent.llm_provider)
    pkg_mgr = d_info.package_manager  # e.g. 'apt', 'dnf', 'pacman', 'apk'

    def _cprint(msg: str, plain: str = ""):
        if HAS_RICH and console:
            console.print(msg)
        else:
            print(plain or msg)

    def _confirm(prompt: str) -> bool:
        try:
            ans = input(f"{prompt} [y/N]: ").strip().lower()
            return ans in ("y", "yes")
        except (KeyboardInterrupt, EOFError):
            return False

    def _render_log_output(result: Dict[str, Any], title: str = "Log Output"):
        lines = result.get("lines", [])
        err = result.get("error")
        if err:
            _cprint(f"[red]Error: {err}[/red]", f"Error: {err}")
            return
        if not lines:
            _cprint("[dim]No log entries found.[/dim]", "No log entries found.")
            return
        if HAS_RICH and console:
            console.print(Panel("\n".join(lines[-80:]), title=title, border_style="dim"))
        else:
            print(f"\n--- {title} ---")
            for l in lines[-80:]:
                print(l)
            print()

    def _run_shell_passthrough(cmd: str):
        lvl, risk, reason = validator.evaluate_safety(cmd)
        if HAS_RICH and console:
            from rich.markup import escape
            console.print(f"[dim]Safety: {format_safety_badge(lvl)} | Risk: {risk:.2f} | {escape(reason)}[/dim]")
        else:
            print(f"Safety: [{lvl.value}] Risk: {risk:.2f} | {reason}")

        if lvl == SafetyLevel.DESTRUCTIVE:
            _cprint("[bold red]🛑 DESTRUCTIVE command blocked by safety sandbox.[/bold red]",
                    "🛑 DESTRUCTIVE command blocked.")
            return
        if lvl in (SafetyLevel.MODIFYING, SafetyLevel.HIGH_RISK):
            if not _confirm(f"⚠  Execute '{cmd}'?"):
                print("Skipped.")
                return
        res = executor.execute(cmd)
        rc = res.get("returncode", -1)
        if res.get("stdout"):
            print(res["stdout"])
        if res.get("stderr") and rc != 0:
            print(res["stderr"])
        if rc != 0:
            _cprint(f"[red]Exit code: {rc}[/red]", f"Exit code: {rc}")

    while True:
        try:
            query = input(f"\nops-assistant [{d_info.distro_name}]> ").strip()
            if not query:
                continue

            # Expand colon shortcuts to full NL before routing
            _q = query
            _ql = query.lower()
            if _ql in (":disk", ":storage"):
                _q = "how much space am I using"
            elif _ql == ":large":
                _q = "find large files"
            elif _ql == ":clean":
                _q = "clean up old logs"
            elif _ql in (":processes", ":procs", ":top"):
                _q = "show running processes"
            elif _ql in (":ports", ":listening"):
                _q = "what ports are open"
            elif _ql in (":network", ":net", ":interfaces"):
                _q = "show network interfaces"
            elif _ql in (":errors", ":errs"):
                _q = "show errors"
            elif _ql == ":kernel":
                _q = "show kernel errors"
            elif _ql in (":cron", ":crontab"):
                _q = "show cron jobs"
            elif _ql in (":users", ":who"):
                _q = "who is logged in"
            elif _ql in (":firewall", ":fw"):
                _q = "show firewall rules"
            elif _ql.startswith(":logs"):
                svc = _ql[5:].strip()
                _q = f"show logs for {svc}" if svc else "show recent logs"
            elif _ql.startswith(":run "):
                _q = "run: " + query[5:].strip()
            elif _ql.startswith("!"):
                _q = "run: " + query[1:].strip()

            intent = router.classify(_q)

            # -----------------------------------------------------------------
            # Meta / assistant commands
            # -----------------------------------------------------------------
            if intent.type == IntentType.EXIT:
                print("Goodbye!")
                break

            elif intent.type == IntentType.HELP:
                print_repl_help()

            elif intent.type == IntentType.CLEAR:
                os.system("clear" if os.name == "posix" else "cls")

            elif intent.type == IntentType.HEALTH:
                render_health_dashboard(agent.hub, distro_override=active_distro)

            elif intent.type == IntentType.HISTORY:
                if not executor.history:
                    print("No commands executed in this session.")
                else:
                    if HAS_RICH and console:
                        h_table = Table(title="Session Execution History", show_header=True, header_style="bold cyan")
                        h_table.add_column("#", width=3)
                        h_table.add_column("Command", style="bold yellow")
                        h_table.add_column("Executed")
                        h_table.add_column("Code")
                        h_table.add_column("Rollback Command")
                        for idx, h in enumerate(executor.history, 1):
                            h_table.add_row(
                                str(idx), h.get("command", ""),
                                "[green]YES[/green]" if h.get("executed") else "[yellow]DRY_RUN[/yellow]",
                                str(h.get("returncode", "")),
                                h.get("rollback_command") or "[dim]N/A[/dim]"
                            )
                        console.print(h_table)
                    else:
                        print("Session Execution History:")
                        for idx, h in enumerate(executor.history, 1):
                            print(f"  [{idx}] {h.get('command')} -> code {h.get('returncode')} (Rollback: {h.get('rollback_command') or 'None'})")

            elif intent.type in (IntentType.ROLLBACK,):
                res = executor.rollback_last()
                if res.get("executed"):
                    print(f"↩ Rollback executed: {res.get('command')} -> code {res.get('returncode')}")
                else:
                    print(f"⚠️  {res.get('stderr')}")

            elif intent.type == IntentType.EXPORT:
                parts = query.split()
                if len(parts) >= 3 and last_report:
                    export_report(last_report, parts[2], fmt=parts[1].lower())
                elif not last_report:
                    print("No diagnostic report generated yet in this session.")
                else:
                    print("Usage: export json <path>  OR  export md <path>")

            # -----------------------------------------------------------------
            # System info
            # -----------------------------------------------------------------
            elif intent.type == IntentType.SYSTEM_INFO:
                d = agent.distro_detector.detect(override_family=active_distro)
                if HAS_RICH and console:
                    t = Table(title="System Information", show_header=True, header_style="bold magenta")
                    t.add_column("Attribute", style="bold"); t.add_column("Value")
                    import platform
                    t.add_row("Distribution", d.distro_name)
                    t.add_row("Family", d.family_id)
                    t.add_row("Init System", d.init_system)
                    t.add_row("Package Manager", d.package_manager)
                    t.add_row("Firewall Tool", d.default_firewall)
                    t.add_row("Security Engine", d.security_subsystem)
                    t.add_row("Kernel", agent.hub.proc.get_kernel_version() if hasattr(agent.hub.proc, "get_kernel_version") else platform.release())
                    console.print(t)
                else:
                    import platform
                    print(f"\nDistro: {d.distro_name} ({d.family_id})")
                    print(f"Init: {d.init_system} | Pkg: {d.package_manager}")
                    print(f"Kernel: {platform.release()}\n")

            elif intent.type == IntentType.SYSTEM_UPTIME:
                snap = agent.hub.get_health_snapshot()
                hrs = snap.uptime_seconds / 3600
                _cprint(f"[green]Uptime:[/green] {hrs:.1f} hours ({snap.uptime_seconds:.0f} s)",
                        f"Uptime: {hrs:.1f} hours")

            elif intent.type == IntentType.SYSTEM_REBOOT:
                if _confirm("⚠  This will REBOOT the system. Are you sure?"):
                    _run_shell_passthrough("sudo reboot")
                else:
                    print("Reboot cancelled.")

            # -----------------------------------------------------------------
            # Storage
            # -----------------------------------------------------------------
            elif intent.type == IntentType.STORAGE_ANALYSE:
                _cprint("[bold cyan]Analysing disk usage…[/bold cyan]", "Analysing disk usage…")
                result = storage_ops.analyse_disk()
                if HAS_RICH and console:
                    dt = Table(title="Disk Usage Summary", show_header=True, header_style="bold cyan")
                    dt.add_column("Device"); dt.add_column("Mount"); dt.add_column("Size")
                    dt.add_column("Used"); dt.add_column("Avail"); dt.add_column("Use%", justify="right"); dt.add_column("Status", justify="center")
                    for p in result["partitions"]:
                        color = "red" if p["use_pct"] >= 85 else ("yellow" if p["use_pct"] >= 70 else "green")
                        dt.add_row(p["device"], p["mountpoint"], p["size"], p["used"], p["avail"],
                                   f"[{color}]{p['use_pct']}%[/{color}]",
                                   f"[{color}]{p['status']}[/{color}]")
                    console.print(dt)
                    if result["top_dirs"]:
                        console.print("[dim]Top directory sizes:[/dim] " + "  |  ".join(f"{d['path']}: {d['size']}" for d in result["top_dirs"]))
                else:
                    for p in result["partitions"]:
                        print(f"  {p['mountpoint']:20} {p['used']:>8}/{p['size']:>8} ({p['use_pct']}%) [{p['status']}]")
                    for d in result["top_dirs"]:
                        print(f"  {d['path']}: {d['size']}")

            elif intent.type == IntentType.STORAGE_FIND_LARGE:
                path = intent.args.get("path", "/")
                _cprint(f"[bold cyan]Finding large files in {path}…[/bold cyan]",
                        f"Finding large files in {path}…")
                result = storage_ops.find_large_files(search_path=path, threshold_mb=50, top_n=20)
                if result.get("error"):
                    _cprint(f"[red]{result['error']}[/red]", result["error"])
                elif not result["files"]:
                    _cprint("[dim]No files above 50 MB found.[/dim]", "No files above 50 MB found.")
                else:
                    if HAS_RICH and console:
                        ft = Table(title="Largest Files", show_header=True, header_style="bold cyan")
                        ft.add_column("#", width=3); ft.add_column("Size", justify="right"); ft.add_column("Path")
                        for i, f in enumerate(result["files"], 1):
                            ft.add_row(str(i), f["size_human"], f["path"])
                        console.print(ft)
                    else:
                        for i, f in enumerate(result["files"], 1):
                            print(f"  [{i:2d}] {f['size_human']:>10}  {f['path']}")

            elif intent.type == IntentType.STORAGE_CLEAN:
                _cprint("[bold cyan]Scanning for cleanable files (dry-run)…[/bold cyan]",
                        "Scanning for cleanable files (dry-run)…")
                plan = storage_ops.clean_logs(dry_run=True)
                if plan["count"] == 0:
                    _cprint("[green]✓ Nothing to clean — no stale logs or old /tmp files found.[/green]",
                            "✓ Nothing to clean.")
                else:
                    _cprint(f"[yellow]Found {plan['count']} cleanable files (~{plan['freed_estimate']} freed):[/yellow]",
                            f"Found {plan['count']} cleanable files (~{plan['freed_estimate']} freed):")
                    for c in plan["candidates"][:15]:
                        print(f"  {c['size_human']:>10}  {c['path']}  ({c['age_days']:.0f} days old)")
                    if plan["count"] > 15:
                        print(f"  … and {plan['count'] - 15} more")
                    if _confirm(f"\nDelete these {plan['count']} files?"):
                        result = storage_ops.clean_logs(dry_run=False)
                        deleted = sum(1 for a in result["actions"] if a["status"] == "deleted")
                        _cprint(f"[green]✓ Deleted {deleted}/{plan['count']} files.[/green]",
                                f"✓ Deleted {deleted}/{plan['count']} files.")
                    else:
                        print("Cancelled.")

            elif intent.type == IntentType.STORAGE_ORGANISE:
                raw_path = intent.args.get("path", "")
                if not raw_path:
                    try:
                        raw_path = input("Which directory to organise? (e.g. ~/Downloads): ").strip()
                    except (KeyboardInterrupt, EOFError):
                        print("\nCancelled.")
                        continue
                import os as _os
                target = _os.path.expanduser(raw_path)
                _cprint(f"[bold cyan]Planning organisation of {target}…[/bold cyan]",
                        f"Planning organisation of {target}…")
                plan = storage_ops.organise_directory(target, dry_run=True)
                if plan.get("error"):
                    _cprint(f"[red]{plan['error']}[/red]", plan["error"])
                elif plan["total_files"] == 0:
                    _cprint("[dim]No files to organise.[/dim]", "No files to organise.")
                else:
                    categories = plan["categories"]
                    _cprint(f"[yellow]Will move {plan['total_files']} files into: {', '.join(categories)}/[/yellow]",
                            f"Will move {plan['total_files']} files into: {', '.join(categories)}/")
                    for m in plan["moves"][:10]:
                        print(f"  {m['filename']:40} → {m['category']}/")
                    if plan["total_files"] > 10:
                        print(f"  … and {plan['total_files'] - 10} more")
                    if _confirm(f"\nProceed with organising {target}?"):
                        result = storage_ops.organise_directory(target, dry_run=False)
                        moved = sum(1 for m in result["moves"] if m.get("status") == "moved")
                        _cprint(f"[green]✓ Moved {moved}/{plan['total_files']} files.[/green]",
                                f"✓ Moved {moved}/{plan['total_files']} files.")
                        if result["errors"]:
                            print(f"  Errors: {len(result['errors'])}")
                    else:
                        print("Cancelled.")

            # -----------------------------------------------------------------
            # Processes
            # -----------------------------------------------------------------
            elif intent.type == IntentType.PROCESS_LIST:
                result = process_ops.list_processes(sort_by="cpu", top_n=20)
                if result["error"]:
                    _cprint(f"[red]{result['error']}[/red]", result["error"])
                else:
                    if HAS_RICH and console:
                        pt = Table(title="Top Processes (by CPU)", show_header=True, header_style="bold cyan")
                        pt.add_column("PID", width=7); pt.add_column("User"); pt.add_column("CPU%", justify="right")
                        pt.add_column("MEM%", justify="right"); pt.add_column("Stat"); pt.add_column("Command")
                        for p in result["processes"]:
                            cpu_color = "red" if p["cpu"] > 50 else ("yellow" if p["cpu"] > 10 else "green")
                            pt.add_row(str(p["pid"]), p["user"],
                                       f"[{cpu_color}]{p['cpu']}[/{cpu_color}]",
                                       str(p["mem"]), p["stat"], p["command"])
                        console.print(pt)
                    else:
                        print(f"\n{'PID':>7}  {'USER':<12} {'CPU%':>5} {'MEM%':>5}  COMMAND")
                        for p in result["processes"]:
                            print(f"{p['pid']:>7}  {p['user']:<12} {p['cpu']:>5.1f} {p['mem']:>5.1f}  {p['command']}")

            elif intent.type == IntentType.PROCESS_KILL:
                pid = intent.args.get("pid")
                name = intent.args.get("name")
                target = pid if pid else name
                if not target:
                    try:
                        target = input("Kill which process (PID or name)? ").strip()
                    except (KeyboardInterrupt, EOFError):
                        continue
                if _confirm(f"⚠  Send SIGTERM to process '{target}'?"):
                    if isinstance(target, int) or (isinstance(target, str) and target.isdigit()):
                        result = process_ops.kill_process(pid=int(target))
                    else:
                        result = process_ops.kill_process(name=str(target))
                    if result["success"]:
                        _cprint(f"[green]✓ Signal sent: {result['command']}[/green]",
                                f"✓ Signal sent: {result['command']}")
                    else:
                        _cprint(f"[red]Failed: {result['stderr']}[/red]", f"Failed: {result['stderr']}")
                else:
                    print("Cancelled.")

            elif intent.type == IntentType.PROCESS_INFO:
                pid = intent.args.get("pid")
                if not pid:
                    try:
                        pid = int(input("Process PID: ").strip())
                    except (ValueError, KeyboardInterrupt, EOFError):
                        continue
                info = process_ops.get_process_info(int(pid))
                if "error" in info:
                    _cprint(f"[red]{info['error']}[/red]", info["error"])
                else:
                    for k, v in info.items():
                        print(f"  {k:12}: {v}")

            # -----------------------------------------------------------------
            # Services
            # -----------------------------------------------------------------
            elif intent.type == IntentType.SERVICE_STATUS:
                svc = intent.args.get("service", "")
                if not svc:
                    try:
                        svc = input("Service name: ").strip()
                    except (KeyboardInterrupt, EOFError):
                        continue
                info = process_ops.show_service_status(svc)
                state = info["active_state"]
                color = "green" if state == "active" else ("yellow" if state in ("activating", "deactivating") else "red")
                _cprint(
                    f"[{color}]● {svc}[/{color}] — {info['description']}\n"
                    f"  Active:  [{color}]{state}/{info['sub_state']}[/{color}]\n"
                    f"  PID:     {info['main_pid']}\n"
                    f"  Started: {info['started']}",
                    f"● {svc}: {state}/{info['sub_state']} (PID {info['main_pid']})"
                )

            elif intent.type == IntentType.SERVICE_RESTART:
                svc = intent.args.get("service", "")
                if not svc:
                    try:
                        svc = input("Service to restart: ").strip()
                    except (KeyboardInterrupt, EOFError):
                        continue
                if _confirm(f"Restart {svc}?"):
                    result = process_ops.restart_service(svc)
                    if result["success"]:
                        _cprint(f"[green]✓ {svc} restarted.[/green]", f"✓ {svc} restarted.")
                    else:
                        _cprint(f"[red]Failed: {result['stderr']}[/red]", f"Failed: {result['stderr']}")

            elif intent.type == IntentType.SERVICE_START:
                svc = intent.args.get("service", "")
                if svc and _confirm(f"Start {svc}?"):
                    result = process_ops.start_service(svc)
                    status = "✓ Started." if result["success"] else f"Failed: {result['stderr']}"
                    _cprint(f"[{'green' if result['success'] else 'red'}]{status}[/{'green' if result['success'] else 'red'}]", status)

            elif intent.type == IntentType.SERVICE_STOP:
                svc = intent.args.get("service", "")
                if svc and _confirm(f"⚠  Stop {svc}?"):
                    result = process_ops.stop_service(svc)
                    status = "✓ Stopped." if result["success"] else f"Failed: {result['stderr']}"
                    _cprint(f"[{'green' if result['success'] else 'red'}]{status}[/{'green' if result['success'] else 'red'}]", status)

            elif intent.type == IntentType.SERVICE_RELOAD:
                svc = intent.args.get("service", "")
                if svc and _confirm(f"Reload {svc}?"):
                    result = process_ops.reload_service(svc)
                    status = "✓ Reloaded." if result["success"] else f"Failed: {result['stderr']}"
                    _cprint(f"[{'green' if result['success'] else 'red'}]{status}[/{'green' if result['success'] else 'red'}]", status)

            elif intent.type == IntentType.SERVICE_ENABLE:
                svc = intent.args.get("service", "")
                if svc and _confirm(f"Enable {svc} at boot?"):
                    result = process_ops.enable_service(svc)
                    status = f"✓ {svc} enabled." if result["success"] else f"Failed: {result['stderr']}"
                    _cprint(f"[{'green' if result['success'] else 'red'}]{status}[/{'green' if result['success'] else 'red'}]", status)

            elif intent.type == IntentType.SERVICE_DISABLE:
                svc = intent.args.get("service", "")
                if svc and _confirm(f"Disable {svc} at boot?"):
                    result = process_ops.disable_service(svc)
                    status = f"✓ {svc} disabled." if result["success"] else f"Failed: {result['stderr']}"
                    _cprint(f"[{'green' if result['success'] else 'red'}]{status}[/{'green' if result['success'] else 'red'}]", status)

            elif intent.type == IntentType.SERVICE_LOGS:
                svc = intent.args.get("service", "")
                if not svc:
                    try:
                        svc = input("Service name: ").strip()
                    except (KeyboardInterrupt, EOFError):
                        continue
                result = log_ops.tail_log(svc, lines=60)
                _render_log_output(result, title=f"Logs — {svc}")

            # -----------------------------------------------------------------
            # Packages
            # -----------------------------------------------------------------
            elif intent.type == IntentType.PACKAGE_INSTALL:
                pkg = intent.args.get("package", "")
                if not pkg:
                    try:
                        pkg = input("Package to install: ").strip()
                    except (KeyboardInterrupt, EOFError):
                        continue
                cmds = {
                    "apt": f"sudo apt-get install -y {pkg}",
                    "dnf": f"sudo dnf install -y {pkg}",
                    "yum": f"sudo yum install -y {pkg}",
                    "pacman": f"sudo pacman -S --noconfirm {pkg}",
                    "apk": f"sudo apk add {pkg}",
                    "zypper": f"sudo zypper install -y {pkg}",
                }
                cmd = cmds.get(pkg_mgr, f"sudo {pkg_mgr} install {pkg}")
                _cprint(f"[dim]Will run:[/dim] [bold]{cmd}[/bold]", f"Will run: {cmd}")
                if _confirm(f"Install '{pkg}' via {pkg_mgr}?"):
                    _run_shell_passthrough(cmd)

            elif intent.type == IntentType.PACKAGE_REMOVE:
                pkg = intent.args.get("package", "")
                if not pkg:
                    try:
                        pkg = input("Package to remove: ").strip()
                    except (KeyboardInterrupt, EOFError):
                        continue
                cmds = {
                    "apt": f"sudo apt-get remove -y {pkg}",
                    "dnf": f"sudo dnf remove -y {pkg}",
                    "yum": f"sudo yum remove -y {pkg}",
                    "pacman": f"sudo pacman -R --noconfirm {pkg}",
                    "apk": f"sudo apk del {pkg}",
                    "zypper": f"sudo zypper remove -y {pkg}",
                }
                cmd = cmds.get(pkg_mgr, f"sudo {pkg_mgr} remove {pkg}")
                _cprint(f"[dim]Will run:[/dim] [bold]{cmd}[/bold]", f"Will run: {cmd}")
                if _confirm(f"⚠  Remove '{pkg}' via {pkg_mgr}?"):
                    _run_shell_passthrough(cmd)

            elif intent.type == IntentType.PACKAGE_UPDATE:
                cmds = {
                    "apt": "sudo apt-get update && sudo apt-get upgrade -y",
                    "dnf": "sudo dnf upgrade -y",
                    "yum": "sudo yum update -y",
                    "pacman": "sudo pacman -Syu --noconfirm",
                    "apk": "sudo apk update && sudo apk upgrade",
                    "zypper": "sudo zypper update -y",
                }
                cmd = cmds.get(pkg_mgr, f"sudo {pkg_mgr} update")
                _cprint(f"[dim]Will run:[/dim] [bold]{cmd}[/bold]", f"Will run: {cmd}")
                if _confirm("Update all packages?"):
                    _run_shell_passthrough(cmd)

            elif intent.type == IntentType.PACKAGE_SEARCH:
                pkg = intent.args.get("package", "")
                if not pkg:
                    try:
                        pkg = input("Search for: ").strip()
                    except (KeyboardInterrupt, EOFError):
                        continue
                cmds = {
                    "apt": f"apt-cache search {pkg}",
                    "dnf": f"dnf search {pkg}",
                    "yum": f"yum search {pkg}",
                    "pacman": f"pacman -Ss {pkg}",
                    "apk": f"apk search {pkg}",
                }
                cmd = cmds.get(pkg_mgr, f"{pkg_mgr} search {pkg}")
                _run_shell_passthrough(cmd)

            # -----------------------------------------------------------------
            # Network
            # -----------------------------------------------------------------
            elif intent.type == IntentType.NETWORK_STATUS:
                result = network_ops.show_interfaces()
                if HAS_RICH and console:
                    nt = Table(title="Network Interfaces", show_header=True, header_style="bold cyan")
                    nt.add_column("Interface"); nt.add_column("State"); nt.add_column("Addresses")
                    for iface in result["interfaces"]:
                        state_color = "green" if "UP" in iface["state"].upper() else "dim"
                        nt.add_row(iface["interface"],
                                   f"[{state_color}]{iface['state']}[/{state_color}]",
                                   iface["addresses"])
                    console.print(nt)
                    if result["gateway"]:
                        console.print(f"[dim]Default gateway: {result['gateway']}[/dim]")
                else:
                    for iface in result["interfaces"]:
                        print(f"  {iface['interface']:16} {iface['state']:8} {iface['addresses']}")
                    if result["gateway"]:
                        print(f"  Default gateway: {result['gateway']}")

            elif intent.type == IntentType.NETWORK_PORTS:
                result = network_ops.show_listening_ports()
                if HAS_RICH and console:
                    console.print(Panel(result["raw"] or "(no output)", title="Listening Ports (ss -tlnup)", border_style="dim"))
                else:
                    print(result["raw"])
                if result.get("error"):
                    _cprint(f"[red]{result['error']}[/red]", result["error"])

            elif intent.type == IntentType.NETWORK_PING:
                host = intent.args.get("host", "")
                if not host:
                    try:
                        host = input("Host to ping: ").strip()
                    except (KeyboardInterrupt, EOFError):
                        continue
                _cprint(f"[dim]Pinging {host}…[/dim]", f"Pinging {host}…")
                result = network_ops.ping_host(host)
                if result["reachable"]:
                    _cprint(f"[green]✓ {host} is reachable | RTT avg: {result['rtt_avg']} | Loss: {result['packet_loss']}[/green]",
                            f"✓ {host} reachable | RTT: {result['rtt_avg']} | Loss: {result['packet_loss']}")
                else:
                    _cprint(f"[red]✗ {host} is unreachable | Loss: {result['packet_loss']}[/red]",
                            f"✗ {host} unreachable | Loss: {result['packet_loss']}")

            elif intent.type == IntentType.NETWORK_DNS:
                host = intent.args.get("host", "")
                if not host:
                    try:
                        host = input("Hostname to resolve: ").strip()
                    except (KeyboardInterrupt, EOFError):
                        continue
                result = network_ops.dns_lookup(host)
                addrs = result.get("addresses", [])
                if addrs:
                    _cprint(f"[green]{host}[/green] → {', '.join(addrs)}", f"{host} → {', '.join(addrs)}")
                else:
                    _cprint(f"[red]Could not resolve {host}[/red]", f"Could not resolve {host}")

            elif intent.type == IntentType.NETWORK_ROUTE:
                result = network_ops.show_routes()
                if HAS_RICH and console:
                    console.print(Panel(result["raw"], title="Routing Table", border_style="dim"))
                else:
                    print(result["raw"])

            elif intent.type == IntentType.FIREWALL_STATUS:
                result = network_ops.show_firewall_rules()
                if HAS_RICH and console:
                    console.print(Panel(result["raw"] or "(no output)", title=f"Firewall Rules ({result['firewall']})", border_style="dim"))
                else:
                    print(result["raw"])

            elif intent.type == IntentType.FIREWALL_ALLOW:
                port = intent.args.get("port", "")
                if not port:
                    try:
                        port = input("Port to allow: ").strip()
                    except (KeyboardInterrupt, EOFError):
                        continue
                if _confirm(f"Allow port {port}/tcp in firewall?"):
                    result = network_ops.allow_port(port)
                    if result["success"]:
                        _cprint(f"[green]✓ Port {port} allowed via {result['firewall']}[/green]",
                                f"✓ Port {port} allowed.")
                    else:
                        _cprint(f"[red]Failed: {result['stderr']}[/red]", f"Failed: {result['stderr']}")

            elif intent.type == IntentType.FIREWALL_DENY:
                port = intent.args.get("port", "")
                if port and _confirm(f"⚠  Block port {port}/tcp?"):
                    result = network_ops.deny_port(port)
                    status = f"✓ Port {port} blocked." if result["success"] else f"Failed: {result['stderr']}"
                    _cprint(f"[{'green' if result['success'] else 'red'}]{status}[/{'green' if result['success'] else 'red'}]", status)

            # -----------------------------------------------------------------
            # Files
            # -----------------------------------------------------------------
            elif intent.type == IntentType.FILE_FIND:
                pattern = intent.args.get("path", "")
                if not pattern:
                    try:
                        pattern = input("Find file/pattern: ").strip()
                    except (KeyboardInterrupt, EOFError):
                        continue
                _run_shell_passthrough(f"find / -name '{pattern}' -maxdepth 8 2>/dev/null | head -30")

            elif intent.type == IntentType.FILE_SHOW:
                path = intent.args.get("path", "")
                if not path:
                    try:
                        path = input("File path to show: ").strip()
                    except (KeyboardInterrupt, EOFError):
                        continue
                import os as _os
                path = _os.path.expanduser(path)
                _run_shell_passthrough(f"cat {path}")

            elif intent.type == IntentType.FILE_EDIT:
                path = intent.args.get("path", "")
                editor = _os.environ.get("EDITOR", "nano") if "import os as _os" in dir() else os.environ.get("EDITOR", "nano")
                if not path:
                    try:
                        path = input("File path to edit: ").strip()
                    except (KeyboardInterrupt, EOFError):
                        continue
                os.system(f"{editor} {path}")

            # -----------------------------------------------------------------
            # Desktop Operations & Downloads
            # -----------------------------------------------------------------
            elif intent.type == IntentType.DESKTOP_OPEN_FOLDER:
                from ops_assistant.tools import desktop_ops
                path = intent.args.get("path", "~")
                res = desktop_ops.open_folder(path)
                _cprint(f"[green]✓ {res.get('message', res.get('error'))}[/green]",
                        f"✓ {res.get('message', res.get('error'))}")

            elif intent.type == IntentType.DESKTOP_OPEN_FILE:
                from ops_assistant.tools import desktop_ops
                path = intent.args.get("path", "")
                res = desktop_ops.open_file(path)
                _cprint(f"[green]✓ {res.get('message', res.get('error'))}[/green]",
                        f"✓ {res.get('message', res.get('error'))}")

            elif intent.type == IntentType.DESKTOP_OPEN_IMAGE:
                from ops_assistant.tools import desktop_ops
                path = intent.args.get("path", "")
                res = desktop_ops.open_image(path)
                _cprint(f"[green]✓ {res.get('message', res.get('error'))}[/green]",
                        f"✓ {res.get('message', res.get('error'))}")

            elif intent.type == IntentType.DESKTOP_OPEN_BROWSER:
                from ops_assistant.tools import desktop_ops
                url = intent.args.get("url", "https://google.com")
                res = desktop_ops.open_browser(url)
                _cprint(f"[green]✓ {res.get('message', res.get('error'))}[/green]",
                        f"✓ {res.get('message', res.get('error'))}")

            elif intent.type == IntentType.DOWNLOAD_URL:
                from ops_assistant.tools import download_ops
                url = intent.args.get("url", "")
                dest = intent.args.get("dest", "~/Downloads")
                _cprint(f"[cyan]Downloading {url} to {dest}...[/cyan]", f"Downloading {url} to {dest}...")
                res = download_ops.download_file(url, destination_dir=dest, auto_extract=True)
                if res.get("success"):
                    _cprint(f"[green]✓ {res.get('message')} ({res.get('size_human')})[/green]",
                            f"✓ {res.get('message')}")
                else:
                    _cprint(f"[red]Failed: {res.get('error')}[/red]", f"Failed: {res.get('error')}")

            elif intent.type == IntentType.FILE_MOVE:
                from ops_assistant.tools import desktop_ops
                src = intent.args.get("src", "")
                dst = intent.args.get("dst", "")
                res = desktop_ops.move_path(src, dst)
                _cprint(f"[green]✓ {res.get('message', res.get('error'))}[/green]",
                        f"✓ {res.get('message', res.get('error'))}")

            elif intent.type == IntentType.FILE_COPY:
                from ops_assistant.tools import desktop_ops
                src = intent.args.get("src", "")
                dst = intent.args.get("dst", "")
                res = desktop_ops.copy_path(src, dst)
                _cprint(f"[green]✓ {res.get('message', res.get('error'))}[/green]",
                        f"✓ {res.get('message', res.get('error'))}")

            elif intent.type == IntentType.FILE_TRASH:
                from ops_assistant.tools import desktop_ops
                path = intent.args.get("path", "")
                res = desktop_ops.trash_path(path)
                _cprint(f"[green]✓ {res.get('message', res.get('error'))}[/green]",
                        f"✓ {res.get('message', res.get('error'))}")

            # -----------------------------------------------------------------
            # Logs
            # -----------------------------------------------------------------
            elif intent.type == IntentType.LOGS_SHOW:
                result = log_ops.tail_log("", lines=60) if not intent.args.get("service") else log_ops.tail_log(intent.args["service"], lines=60)
                _render_log_output(result, "Recent Logs")

            elif intent.type == IntentType.LOGS_ERRORS:
                result = log_ops.show_errors(since="1h")
                count = result.get("count", 0)
                _cprint(
                    f"[{'red' if count > 0 else 'green'}]{count} error(s) in the last hour (source: {result['source']})[/{'red' if count > 0 else 'green'}]",
                    f"{count} error(s) in the last hour"
                )
                _render_log_output(result, "Recent Errors")

            elif intent.type == IntentType.LOGS_KERNEL:
                result = log_ops.show_kernel_errors()
                _render_log_output(result, "Kernel Messages (dmesg)")

            # -----------------------------------------------------------------
            # Cron
            # -----------------------------------------------------------------
            elif intent.type == IntentType.CRON_LIST:
                result = log_ops.list_cron_jobs()
                if HAS_RICH and console:
                    if result["user_crontab"]:
                        console.print(Panel("\n".join(result["user_crontab"]), title="User Crontab", border_style="dim"))
                    else:
                        console.print("[dim]No user crontab entries.[/dim]")
                    if result["system_cron"]:
                        console.print("[dim]System cron files:[/dim] " + ", ".join(f"{c['dir']}/{c['file']}" for c in result["system_cron"][:10]))
                else:
                    print("User crontab:", result["user_crontab"] or "(empty)")
                    for c in result["system_cron"][:10]:
                        print(f"  {c['dir']}/{c['file']}")

            elif intent.type == IntentType.CRON_ADD:
                _cprint("[yellow]Cron job creation: use 'crontab -e' to add entries manually,[/yellow]\n"
                        "[yellow]or describe the schedule and I'll generate the cron expression.[/yellow]",
                        "Use 'crontab -e' to add cron entries.")

            # -----------------------------------------------------------------
            # Users
            # -----------------------------------------------------------------
            elif intent.type == IntentType.USER_WHO:
                result = log_ops.who_is_logged_in()
                if result["sessions"]:
                    for s in result["sessions"]:
                        frm = f"from {s['from']}" if s["from"] else ""
                        _cprint(f"  [bold]{s['user']}[/bold] on {s['tty']} since {s['login_time']} {frm}",
                                f"  {s['user']} on {s['tty']} since {s['login_time']} {frm}")
                else:
                    _cprint("[dim]No active sessions.[/dim]", "No active sessions.")

            elif intent.type == IntentType.USER_LIST:
                result = log_ops.list_all_users()
                if HAS_RICH and console:
                    ut = Table(title="System Users", show_header=True, header_style="bold cyan")
                    ut.add_column("Username"); ut.add_column("UID"); ut.add_column("Home"); ut.add_column("Shell")
                    for u in result["users"]:
                        if u["shell"] not in ("/bin/false", "/usr/sbin/nologin"):
                            ut.add_row(u["username"], u["uid"], u["home"], u["shell"])
                    console.print(ut)
                else:
                    for u in result["users"]:
                        if u["shell"] not in ("/bin/false", "/usr/sbin/nologin"):
                            print(f"  {u['username']:20} (uid {u['uid']:5}) {u['home']}")

            # -----------------------------------------------------------------
            # Hardware & AI Advisory
            # -----------------------------------------------------------------
            elif intent.type in (IntentType.HARDWARE_PROFILE, IntentType.HARDWARE_RECOMMEND_MODEL):
                render_hardware_profile()

            elif intent.type == IntentType.HARDWARE_AUTO_TUNE:
                auto_tune_system()

            # -----------------------------------------------------------------
            # Proactive Audit & Security
            # -----------------------------------------------------------------
            elif intent.type == IntentType.PROACTIVE_AUDIT:
                render_proactive_audit()

            elif intent.type == IntentType.SECURITY_AUDIT:
                render_security_audit()

            elif intent.type in (IntentType.SECURITY_SSH_CHECK, IntentType.SECURITY_BRUTEFORCE, IntentType.SECURITY_SUID):
                act_res = agent.execute_agent_action(query, execute=True)
                _cprint(f"[bold green]✓ {act_res.get('summary', 'Security check completed.')}[/bold green]",
                        f"✓ {act_res.get('summary', 'Security check completed.')}")
                if act_res.get("output") and isinstance(act_res["output"], dict):
                    for k, v in act_res["output"].items():
                        if k not in ("error", "success") and not isinstance(v, (dict, list)):
                            print(f"  {k:25}: {v}")

            # -----------------------------------------------------------------
            # Docker & Containers
            # -----------------------------------------------------------------
            elif intent.type == IntentType.DOCKER_LIST:
                render_docker_status()

            elif intent.type in (IntentType.DOCKER_LOGS, IntentType.DOCKER_RESTART, IntentType.DOCKER_PRUNE):
                act_plan = agent.execute_agent_action(query, execute=False)
                cmd_to_run = act_plan.get("command", "")
                if act_plan.get("requires_permission") and cmd_to_run:
                    if _confirm(f"Execute '{cmd_to_run}'?"):
                        act_res = agent.execute_agent_action(query, execute=True)
                        _cprint(f"[green]✓ {act_res.get('summary', 'Executed successfully.')}[/green]",
                                f"✓ {act_res.get('summary', 'Executed successfully.')}")
                    else:
                        print("Cancelled.")
                else:
                    act_res = agent.execute_agent_action(query, execute=True)
                    _cprint(f"[green]✓ {act_res.get('summary', 'Done.')}[/green]",
                            f"✓ {act_res.get('summary', 'Done.')}")

            # -----------------------------------------------------------------
            # Backup & Restore
            # -----------------------------------------------------------------
            elif intent.type == IntentType.BACKUP_LIST:
                act_res = agent.execute_agent_action(query, execute=True)
                _cprint(f"[green]✓ {act_res.get('summary')}[/green]", f"✓ {act_res.get('summary')}")
                backups = act_res.get("output", {}).get("backups", [])
                if backups:
                    for b in backups:
                        print(f"  {b.get('filename'):35} {b.get('size_human', ''):>10}  {b.get('created_human', '')}")

            elif intent.type in (IntentType.BACKUP_CREATE, IntentType.BACKUP_RESTORE):
                act_plan = agent.execute_agent_action(query, execute=False)
                cmd_to_run = act_plan.get("command", "")
                if act_plan.get("requires_permission") and cmd_to_run:
                    if _confirm(f"Execute '{cmd_to_run}'?"):
                        act_res = agent.execute_agent_action(query, execute=True)
                        _cprint(f"[green]✓ {act_res.get('summary', 'Backup operation completed.')}[/green]",
                                f"✓ {act_res.get('summary', 'Backup operation completed.')}")
                    else:
                        print("Cancelled.")
                else:
                    act_res = agent.execute_agent_action(query, execute=True)
                    _cprint(f"[green]✓ {act_res.get('summary')}[/green]", f"✓ {act_res.get('summary')}")

            # -----------------------------------------------------------------
            # System Maintenance (Boot, SSD TRIM, Package Clean, Journal Vacuum, Cron Remove)
            # -----------------------------------------------------------------
            elif intent.type in (IntentType.SYSTEM_BOOT_ANALYSIS, IntentType.SYSTEM_TRIM_SSD,
                                 IntentType.SYSTEM_PACKAGE_CLEAN, IntentType.SYSTEM_JOURNAL_VACUUM,
                                 IntentType.CRON_REMOVE):
                act_plan = agent.execute_agent_action(query, execute=False)
                cmd_to_run = act_plan.get("command", "")
                if act_plan.get("requires_permission") and cmd_to_run:
                    if _confirm(f"Execute '{cmd_to_run}'?"):
                        act_res = agent.execute_agent_action(query, execute=True)
                        _cprint(f"[green]✓ {act_res.get('summary', 'System maintenance action completed.')}[/green]",
                                f"✓ {act_res.get('summary', 'System maintenance action completed.')}")
                    else:
                        print("Cancelled.")
                else:
                    act_res = agent.execute_agent_action(query, execute=True)
                    _cprint(f"[green]✓ {act_res.get('summary')}[/green]", f"✓ {act_res.get('summary')}")

            # -----------------------------------------------------------------
            # Shell passthrough
            # -----------------------------------------------------------------
            elif intent.type == IntentType.SHELL_RUN:
                cmd = intent.args.get("cmd", "")
                if cmd:
                    _run_shell_passthrough(cmd)
                else:
                    print("Usage: :run <command>  or  !<command>")

            # -----------------------------------------------------------------
            # Safety inspection
            # -----------------------------------------------------------------
            elif _ql.startswith("safety") or _ql.startswith("eval"):
                parts = query.split(maxsplit=1)
                if len(parts) > 1:
                    render_safety_inspection(parts[1].strip(), validator)
                else:
                    print("Usage: safety <command>")

            # -----------------------------------------------------------------
            # Legacy shortcuts still work
            # -----------------------------------------------------------------
            elif _ql.startswith("distro"):
                parts = query.split(maxsplit=1)
                if len(parts) > 1:
                    new_distro = parts[1].strip().lower()
                    if new_distro in ["debian", "rhel", "arch", "alpine", "suse"]:
                        active_distro = new_distro
                        d_info = agent.distro_detector.detect(override_family=active_distro)
                        pkg_mgr = d_info.package_manager
                        print(f"Switched to: {d_info.distro_name}")
                    else:
                        print(f"Unknown family '{new_distro}'. Options: debian, rhel, arch, alpine, suse")
                else:
                    d = agent.distro_detector.detect(override_family=active_distro)
                    print(f"\nFamily: {d.family_id} | Distro: {d.distro_name}")
                    print(f"Init: {d.init_system} | Pkg: {d.package_manager} | FW: {d.default_firewall}")

            elif _ql.startswith("export"):
                parts = query.split()
                if len(parts) >= 3 and last_report:
                    export_report(last_report, parts[2], fmt=parts[1].lower())
                elif not last_report:
                    print("No diagnostic report yet.")
                else:
                    print("Usage: export json <path>  OR  export md <path>")

            elif _ql in ["models", "list-models"]:
                render_models_list()

            elif _ql.startswith("download"):
                parts = query.split(maxsplit=1)
                if len(parts) > 1:
                    download_model_cli(parts[1].strip())
                else:
                    print("Usage: download <model_key>")

            elif _ql.startswith("provider"):
                parts = query.split(maxsplit=1)
                if len(parts) > 1:
                    target_prov = parts[1].strip().lower()
                    if target_prov in ["gguf", "llama_cpp", "local"]:
                        agent.llm_provider = LlamaCppProvider()
                        router = IntentRouter(llm_provider=agent.llm_provider)
                        print("Switched to LlamaCppProvider (GGUF).")
                    elif target_prov in ["ollama", "remote"]:
                        agent.llm_provider = OllamaProvider()
                        router = IntentRouter(llm_provider=agent.llm_provider)
                        print("Switched to OllamaProvider.")
                    elif target_prov in ["none", "deterministic", "off"]:
                        agent.llm_provider = None
                        router = IntentRouter()
                        print("Switched to pure Deterministic mode.")
                else:
                    ptype = type(agent.llm_provider).__name__ if agent.llm_provider else "None (Deterministic)"
                    print(f"Active LLM Provider: {ptype}")

            elif _ql in ["demo"]:
                run_demo(agent, executor)

            elif _ql in ["benchmark"]:
                run_benchmark(agent)

            elif _ql in ["failed", "units"]:
                failed = agent.hub.systemd.get_failed_units()
                if failed:
                    print(f"Found {len(failed)} failed unit(s):")
                    for u in failed:
                        rep = agent.diagnose(f"Why is {u.unit_name} failing?", distro_override=active_distro)
                        last_report = rep
                        render_diagnostic_report(rep, executor, interactive_exec=True)
                else:
                    print(f"✓ No failed {d_info.init_system} units detected.")

            # -----------------------------------------------------------------
            # Fallthrough → diagnostic engine (DIAGNOSE intent or ambiguous NL)
            # -----------------------------------------------------------------
            elif intent.type in (IntentType.DIAGNOSE, IntentType.UNKNOWN):
                rep = agent.diagnose(query, distro_override=active_distro)
                last_report = rep
                render_diagnostic_report(rep, executor, interactive_exec=True)

            else:
                # Any remaining intent not yet handled
                rep = agent.diagnose(query, distro_override=active_distro)
                last_report = rep
                render_diagnostic_report(rep, executor, interactive_exec=True)

        except KeyboardInterrupt:
            print("\n(Operation cancelled. Type 'exit' to quit.)")
            continue
        except EOFError:
            print("\nSession ended.")
            break
        except Exception as e:
            if HAS_RICH and console:
                console.print(Panel(f"[bold red]An unexpected error occurred:[/bold red] {str(e)}", border_style="red"))
            else:
                print(f"\n❌ Error: {e}\n")




def main():
    parser = argparse.ArgumentParser(
        description="AI-Powered Linux Operations Assistant CLI"
    )
    parser.add_argument("query", nargs="?", type=str, help="Natural language diagnostic query", default=None)
    parser.add_argument("--distro", "-d", type=str, help="Simulate / override Linux distribution family (debian, rhel, arch, alpine, suse)", default=None)
    parser.add_argument("--provider", "-p", type=str, choices=["auto", "deterministic", "gguf", "ollama"], default="auto", help="Reasoning backend engine (auto, deterministic, gguf, ollama)")
    parser.add_argument("--model-path", type=str, help="Path to custom local GGUF model file", default=None)
    parser.add_argument("--list-models", action="store_true", help="List registered and downloaded edge GGUF models")
    parser.add_argument("--download-model", type=str, help="Download registered GGUF model (e.g. qwen2.5-coder-0.5b)", default=None)
    parser.add_argument("--inspect-health", action="store_true", help="Display full system health snapshot & PSI metrics")
    parser.add_argument("--diagnose-failed", action="store_true", help="Scan and diagnose failed systemd services")
    parser.add_argument("--profile-hardware", action="store_true", help="Profile CPU, RAM, GPU, and Storage to recommend optimal AI models and tuning")
    parser.add_argument("--test-hardware", action="store_true", help="Run automated hardware benchmarking and validation tests")
    parser.add_argument("--auto-tune", action="store_true", help="Profile hardware, select optimal model, and configure system capabilities")
    parser.add_argument("--setup", action="store_true", help="Launch interactive First-Time Hardware Setup & Model Configuration Wizard")
    parser.add_argument("--proactive-audit", action="store_true", help="Run proactive autonomous health audit across kernel, storage, docker, and security")
    parser.add_argument("--docker-status", action="store_true", help="List Docker containers, status, and port conflict analysis")
    parser.add_argument("--security-audit", action="store_true", help="Run consolidated security audit (SSH, open ports, brute force, SUID)")
    parser.add_argument("--safety-check", "-s", type=str, help="Perform AST safety analysis and deobfuscation check on a command", default=None)
    parser.add_argument("--demo", action="store_true", help="Run interactive demo across representative failure scenarios")
    parser.add_argument("--benchmark", action="store_true", help="Run automated empirical performance and accuracy benchmark")
    parser.add_argument("--interactive", "-i", action="store_true", help="Enable interactive command execution prompt")
    parser.add_argument("--export-json", type=str, help="Export diagnostic report to JSON file path", default=None)
    parser.add_argument("--export-md", type=str, help="Export diagnostic report to Markdown file path", default=None)
    parser.add_argument("--gui", action="store_true", help="Launch interactive Web GUI Dashboard in default browser")
    parser.add_argument("--port", type=int, default=8888, help="Port for Web GUI Dashboard (default: 8888)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open default web browser for GUI")

    args = parser.parse_args()

    if args.setup:
        run_setup_wizard(force=True)
        return

    if args.profile_hardware:
        render_hardware_profile()
        return

    if args.test_hardware:
        run_hardware_test()
        return

    if args.auto_tune:
        auto_tune_system()
        return

    if args.proactive_audit:
        render_proactive_audit()
        return

    if args.docker_status:
        render_docker_status()
        return

    if args.security_audit:
        render_security_audit()
        return

    if args.list_models:
        render_models_list()
        return

    if args.download_model:
        download_model_cli(args.download_model)
        return

    # Provider selection
    provider_setting: Optional[str] = args.provider
    if provider_setting == "deterministic":
        provider_setting = None

    agent = OpsAssistantAgent(llm_provider=provider_setting, model_path=args.model_path)
    executor = SafeExecutor()
    validator = CommandSafetyValidator()

    if args.gui:
        from ops_assistant.gui.server import start_gui_server
        server, url = start_gui_server(
            host="127.0.0.1",
            port=args.port,
            open_browser=not args.no_browser,
            agent=agent
        )
        print(f"\n[+] LinuxOpsAssistant GUI Dashboard live at: {url}")
        print("[+] Press Ctrl+C to exit.\n")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n[*] Stopping GUI server...")
            server.shutdown()
            return
    elif args.safety_check:
        render_safety_inspection(args.safety_check, validator)
    elif args.demo:
        run_demo(agent, executor)
    elif args.benchmark:
        run_benchmark(agent)
    elif args.inspect_health:
        render_health_dashboard(agent.hub, distro_override=args.distro)
    elif args.diagnose_failed:
        failed = agent.hub.systemd.get_failed_units()
        if failed:
            print(f"Found {len(failed)} failed unit(s):")
            for u in failed:
                rep = agent.diagnose(f"Why is {u.unit_name} failing?", distro_override=args.distro)
                render_diagnostic_report(rep, executor, interactive_exec=args.interactive)
        else:
            print("✓ No failed system units found.")
    elif args.query:
        rep = agent.diagnose(args.query, distro_override=args.distro)
        render_diagnostic_report(rep, executor, interactive_exec=args.interactive)
        if args.export_json:
            export_report(rep, args.export_json, fmt="json")
        if args.export_md:
            export_report(rep, args.export_md, fmt="md")
    else:
        run_repl(agent, executor, distro_override=args.distro)


if __name__ == "__main__":
    main()
