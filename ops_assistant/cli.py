"""Interactive CLI and TUI for AI-Powered Linux Operations Assistant."""

import os
import re
import sys
import json
import time
import argparse
from typing import Optional, List, Dict, Any

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
from ops_assistant.collectors.hub import TelemetryHub
from ops_assistant.tools.executor import SafeExecutor
from ops_assistant.tools.safety import CommandSafetyValidator
from ops_assistant.models import DiagnosticReport, SafetyLevel, LogRecord


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


def prompt_interactive_execution(commands: List[Any], executor: SafeExecutor):
    """Prompts user to safely execute or dry-run suggested commands with interactive confirmation."""
    if HAS_RICH and console:
        console.print(Panel(
            "[bold cyan]Interactive Command Remediation Menu:[/bold cyan]\n"
            "  [bold green][1..N][/bold green] Execute specific command by index\n"
            "  [bold green][A][/bold green]    Execute ALL proposed commands in sequence\n"
            "  [bold yellow][D][/bold yellow]    Dry-run preview all commands\n"
            "  [bold cyan][I][/bold cyan]    Inspect AST safety breakdown\n"
            "  [bold magenta][R][/bold magenta]    Rollback last executed modifying action\n"
            "  [bold dim][S][/bold dim]    Skip / Proceed without execution",
            border_style="cyan"
        ))
    else:
        print("Interactive Command Remediation Menu:")
        print("  [1..N] Execute specific command by index")
        print("  [A]    Execute ALL proposed commands in sequence")
        print("  [D]    Dry-run preview all commands")
        print("  [I]    Inspect AST safety breakdown")
        print("  [R]    Rollback last executed modifying action")
        print("  [S]    Skip / Proceed without execution")

    try:
        choice = input("Select action: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nExecution skipped.")
        return

    if not choice or choice in ("s", "skip", "n", "no"):
        print("Execution skipped.")
        return

    if choice in ("d", "dry", "dry-run"):
        for cmd in commands:
            res = executor.execute(cmd.command, dry_run=True, rollback_cmd=cmd.rollback_command)
            if HAS_RICH and console:
                console.print(f"  [bold green]✓[/bold green] [dim]{res['stdout']}[/dim]")
            else:
                print(f"  ✓ {res['stdout']}")

    elif choice in ("i", "inspect"):
        validator = CommandSafetyValidator()
        for cmd in commands:
            render_safety_inspection(cmd.command, validator)

    elif choice in ("r", "rollback", "undo"):
        res = executor.rollback_last()
        if res.get("executed"):
            status_badge = "[bold green]SUCCESS[/bold green]" if res.get("returncode") == 0 else f"[bold red]FAILED ({res.get('returncode')})[/bold red]"
            if HAS_RICH and console:
                console.print(f"  [bold magenta]↩ Executed Rollback:[/bold magenta] `{res.get('command')}` -> {status_badge}")
                if res.get("stdout"):
                    console.print(Panel(res["stdout"].strip(), title="Rollback STDOUT", border_style="dim"))
            else:
                print(f"  ↩ Executed Rollback: {res.get('command')} -> code {res.get('returncode')}")
                if res.get("stdout"):
                    print(f"    {res['stdout'].strip()}")
        else:
            if HAS_RICH and console:
                console.print(f"[bold yellow]⚠️ {res.get('stderr')}[/bold yellow]")
            else:
                print(f"⚠️ {res.get('stderr')}")

    elif choice in ("a", "all"):
        for idx, target in enumerate(commands, 1):
            _execute_with_safety_prompt(target, executor, idx=idx)

    elif choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(commands):
            target = commands[idx]
            _execute_with_safety_prompt(target, executor, idx=idx + 1)
        else:
            print(f"Invalid index {choice}. Must be between 1 and {len(commands)}.")


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
    """Prints formatted help table of REPL commands."""
    if HAS_RICH and console:
        table = Table(title="Interactive Assistant Commands", show_header=True, header_style="bold cyan")
        table.add_column("Command", style="bold yellow", width=22)
        table.add_column("Description")

        table.add_row("<diagnostic query>", "Diagnose issue in natural language (e.g. 'Why is NGINX failing?')")
        table.add_row("health / status", "View full system health snapshot, distro stack & PSI metrics")
        table.add_row("distro [family]", "Inspect or switch active Linux distribution profile")
        table.add_row("failed / units", "Scan failed systemd units and offer interactive remediation")
        table.add_row("safety <command>", "Perform AST safety inspection & de-obfuscation on any shell command")
        table.add_row("history", "View session command execution history and rollback states")
        table.add_row("rollback / undo", "Roll back the most recently executed modifying remediation command")
        table.add_row("export json <path>", "Export the latest diagnostic report to a JSON file")
        table.add_row("export md <path>", "Export the latest diagnostic report to a Markdown file")
        table.add_row("demo", "Run interactive walkthrough of 4 representative failure scenarios")
        table.add_row("benchmark", "Run empirical benchmark across all 16 taxonomy scenarios")
        table.add_row("models", "List edge GGUF models registry and local file status")
        table.add_row("download <key>", "Download an edge GGUF model (e.g. 'qwen2.5-coder-0.5b')")
        table.add_row("provider [type]", "Inspect or switch LLM backend ('gguf', 'ollama', 'none')")
        table.add_row("clear", "Clear terminal screen")
        table.add_row("help / ?", "Display this help menu")
        table.add_row("exit / quit / q", "Exit ops-assistant")

        console.print(table)
    else:
        print("\nInteractive Assistant Commands:")
        print("  <query>             Diagnose issue (e.g. 'Why is NGINX failing?')")
        print("  health / status     View full system health snapshot & PSI metrics")
        print("  distro [family]     Inspect or switch Linux distribution profile")
        print("  models              List edge GGUF models registry and local file status")
        print("  download <key>      Download an edge GGUF model")
        print("  provider [type]     Inspect or switch LLM backend ('gguf', 'ollama', 'none')")
        print("  failed / units      Scan failed systemd units with interactive remediation")
        print("  safety <cmd>        Perform AST safety analysis on shell command")
        print("  history             View session execution history")
        print("  rollback / undo     Roll back last executed modifying action")
        print("  export json <path>  Export latest diagnostic report to JSON")
        print("  export md <path>    Export latest diagnostic report to Markdown")
        print("  demo                Run 4-scenario interactive demo")
        print("  benchmark           Run 16-scenario benchmark")
        print("  clear               Clear screen")
        print("  help / ?", "Display this help menu")
        print("  exit / quit / q     Exit ops-assistant\n")


def run_repl(agent: OpsAssistantAgent, executor: SafeExecutor, distro_override: Optional[str] = None):
    """Runs interactive conversational assistant REPL with error resilience."""
    active_distro = distro_override
    d_info = agent.distro_detector.detect(override_family=active_distro)
    render_banner(d_info.distro_name)
    print("Type a diagnostic query (e.g. 'Why is NGINX failing?'), 'health', 'distro', 'models', 'demo', or 'help'.\n")

    last_report: Optional[DiagnosticReport] = None
    validator = CommandSafetyValidator()

    while True:
        try:
            query = input(f"ops-assistant [{d_info.distro_name}]> ").strip()
            if not query:
                continue

            cmd_lower = query.lower()

            if cmd_lower in ["exit", "quit", "q"]:
                print("Goodbye!")
                break

            elif cmd_lower in ["help", "?"]:
                print_repl_help()

            elif cmd_lower in ["clear", "cls"]:
                os.system("clear" if os.name == "posix" else "cls")

            elif cmd_lower in ["health", "status"]:
                render_health_dashboard(agent.hub, distro_override=active_distro)

            elif cmd_lower in ["models", "list-models"]:
                render_models_list()

            elif cmd_lower.startswith("download"):
                parts = query.split(maxsplit=1)
                if len(parts) > 1:
                    mkey = parts[1].strip()
                    download_model_cli(mkey)
                else:
                    print("Usage: download <model_key> (e.g. 'download qwen2.5-coder-0.5b')")

            elif cmd_lower.startswith("provider"):
                parts = query.split(maxsplit=1)
                if len(parts) > 1:
                    target_prov = parts[1].strip().lower()
                    if target_prov in ["gguf", "llama_cpp", "local"]:
                        agent.llm_provider = LlamaCppProvider()
                        avail, msg = agent.llm_provider.is_available()
                        print(f"Switched LLM provider to LlamaCppProvider (GGUF). Status: {msg}")
                    elif target_prov in ["ollama", "remote"]:
                        agent.llm_provider = OllamaProvider()
                        print("Switched LLM provider to OllamaProvider (http://localhost:11434).")
                    elif target_prov in ["none", "deterministic", "off"]:
                        agent.llm_provider = None
                        print("Switched to pure Deterministic Neuro-Symbolic mode.")
                    else:
                        print(f"Unknown provider '{target_prov}'. Choose from: gguf, ollama, none")
                else:
                    if agent.llm_provider is None:
                        print("Active LLM Provider: None (Pure Deterministic Neuro-Symbolic Engine)")
                    elif isinstance(agent.llm_provider, LlamaCppProvider):
                        avail, msg = agent.llm_provider.is_available()
                        print(f"Active LLM Provider: LlamaCppProvider (GGUF) -> {msg}")
                    elif isinstance(agent.llm_provider, OllamaProvider):
                        print(f"Active LLM Provider: OllamaProvider ({agent.llm_provider.endpoint}, {agent.llm_provider.model})")
                    else:
                        print(f"Active LLM Provider: {type(agent.llm_provider).__name__}")

            elif cmd_lower.startswith("distro"):
                parts = query.split(maxsplit=1)
                if len(parts) > 1:
                    new_distro = parts[1].strip().lower()
                    if new_distro in ["debian", "rhel", "arch", "alpine", "suse"]:
                        active_distro = new_distro
                        d_info = agent.distro_detector.detect(override_family=active_distro)
                        print(f"Switched active distribution profile to: {d_info.distro_name} ({active_distro})")
                    else:
                        print(f"Unknown distro family '{new_distro}'. Supported: debian, rhel, arch, alpine, suse")
                else:
                    d = agent.distro_detector.detect(override_family=active_distro)
                    if HAS_RICH and console:
                        d_table = Table(title="Linux Distribution Profile", show_header=True, header_style="bold magenta")
                        d_table.add_column("Attribute", style="bold")
                        d_table.add_column("Value")
                        d_table.add_row("Family ID", d.family_id)
                        d_table.add_row("Distribution Name", d.distro_name)
                        d_table.add_row("Init System", d.init_system)
                        d_table.add_row("Package Manager", d.package_manager)
                        d_table.add_row("Default Firewall", d.default_firewall)
                        d_table.add_row("Security Engine", d.security_subsystem)
                        console.print(d_table)
                    else:
                        print("\n--- Linux Distribution Profile ---")
                        print(f"Family:           {d.family_id}")
                        print(f"Distribution:     {d.distro_name}")
                        print(f"Init System:      {d.init_system}")
                        print(f"Package Manager:  {d.package_manager}")
                        print(f"Default Firewall: {d.default_firewall}")
                        print(f"Security Engine:  {d.security_subsystem}\n")

            elif cmd_lower.startswith("safety") or cmd_lower.startswith("eval"):
                parts = query.split(maxsplit=1)
                if len(parts) > 1:
                    target_cmd = parts[1].strip()
                    render_safety_inspection(target_cmd, validator)
                else:
                    print("Usage: safety <command> (e.g. safety 'echo cm0gLXJmIC8= | base64 -d | sh')")

            elif cmd_lower.startswith("export"):
                parts = query.split()
                if len(parts) >= 3 and last_report:
                    fmt = parts[1].lower()
                    path = parts[2]
                    export_report(last_report, path, fmt=fmt)
                elif not last_report:
                    print("No diagnostic report has been generated yet in this session.")
                else:
                    print("Usage: export json <path> OR export md <path>")

            elif cmd_lower in ["history"]:
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
                                str(idx),
                                h.get("command", ""),
                                "[green]YES[/green]" if h.get("executed") else "[yellow]DRY_RUN[/yellow]",
                                str(h.get("returncode", "")),
                                h.get("rollback_command") or "[dim]N/A[/dim]"
                            )
                        console.print(h_table)
                    else:
                        print("Session Execution History:")
                        for idx, h in enumerate(executor.history, 1):
                            print(f"  [{idx}] {h.get('command')} -> code {h.get('returncode')} (Rollback: {h.get('rollback_command') or 'None'})")

            elif cmd_lower in ["rollback", "undo"]:
                res = executor.rollback_last()
                if res.get("executed"):
                    print(f"↩ Rollback executed: {res.get('command')} -> code {res.get('returncode')}")
                else:
                    print(f"⚠️ {res.get('stderr')}")

            elif cmd_lower in ["demo"]:
                run_demo(agent, executor)

            elif cmd_lower in ["benchmark"]:
                run_benchmark(agent)

            elif cmd_lower in ["failed", "units"]:
                failed = agent.hub.systemd.get_failed_units()
                if failed:
                    print(f"Found {len(failed)} failed unit(s):")
                    for u in failed:
                        rep = agent.diagnose(f"Why is {u.unit_name} failing?", distro_override=active_distro)
                        last_report = rep
                        render_diagnostic_report(rep, executor, interactive_exec=True)
                else:
                    print(f"✓ No failed {d_info.init_system} units detected.")

            else:
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
    parser.add_argument("--safety-check", "-s", type=str, help="Perform AST safety analysis and deobfuscation check on a command", default=None)
    parser.add_argument("--demo", action="store_true", help="Run interactive demo across representative failure scenarios")
    parser.add_argument("--benchmark", action="store_true", help="Run automated empirical performance and accuracy benchmark")
    parser.add_argument("--interactive", "-i", action="store_true", help="Enable interactive command execution prompt")
    parser.add_argument("--export-json", type=str, help="Export diagnostic report to JSON file path", default=None)
    parser.add_argument("--export-md", type=str, help="Export diagnostic report to Markdown file path", default=None)

    args = parser.parse_args()

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

    if args.safety_check:
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
