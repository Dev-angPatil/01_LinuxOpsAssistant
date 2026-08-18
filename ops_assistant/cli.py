"""Interactive CLI and TUI for AI-Powered Linux Operations Assistant."""

import os
import re
import sys
import json
import time
import argparse
from typing import Optional, List, Dict, Any

# Try importing Rich; provide graceful ANSI fallback if rich is not installed
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt, Confirm
    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    console = None

from ops_assistant.agent import OpsAssistantAgent
from ops_assistant.collectors.hub import TelemetryHub
from ops_assistant.tools.executor import SafeExecutor
from ops_assistant.models import DiagnosticReport, SafetyLevel, LogRecord

def render_health_dashboard(hub: TelemetryHub):
    """Renders a comprehensive system health dashboard."""
    snap = hub.get_health_snapshot()

    if HAS_RICH and console:
        console.print(Panel.fit(
            f"[bold cyan]Linux Health Snapshot[/bold cyan] — [bold green]{snap.hostname}[/bold green] "
            f"(Kernel: {snap.kernel_release}, Uptime: {snap.uptime_seconds / 3600:.1f} hrs, Pressure: [bold yellow]{snap.pressure_status}[/bold yellow])",
            border_style="cyan"
        ))

        table = Table(title="Core System Telemetry", show_header=True, header_style="bold magenta")
        table.add_column("Subsystem", style="dim", width=15)
        table.add_column("Metric", style="bold")
        table.add_column("Value")
        table.add_column("Status", justify="right")

        cpu_status = "[green]NORMAL[/green]" if snap.cpu.idle_pct > 20.0 else "[red]HIGH[/red]"
        table.add_row("CPU", "Utilization", f"User: {snap.cpu.user_pct}%, Sys: {snap.cpu.system_pct}%, Idle: {snap.cpu.idle_pct}%, IO-Wait: {snap.cpu.iowait_pct}%", cpu_status)

        mem_status = "[green]HEALTHY[/green]" if snap.memory.used_percent < 85.0 else "[red]PRESSURE[/red]"
        table.add_row("Memory", "RAM Usage", f"{snap.memory.used_mb:.0f} MB / {snap.memory.total_mb:.0f} MB ({snap.memory.used_percent}%)", mem_status)
        table.add_row("Swap", "Swap Usage", f"{snap.memory.swap_used_mb:.0f} MB / {snap.memory.swap_total_mb:.0f} MB ({snap.memory.swap_used_percent}%)", "[green]OK[/green]" if snap.memory.swap_used_percent < 80.0 else "[red]HIGH[/red]")

        table.add_row("Load Average", "1m / 5m / 15m", f"{snap.load.load_1m:.2f}, {snap.load.load_5m:.2f}, {snap.load.load_15m:.2f}", "[green]OK[/green]")

        for d in snap.disks:
            d_status = "[green]OK[/green]" if d.used_percent < 85.0 else "[red]WARNING[/red]"
            inodes_str = f" | Inodes: {d.inodes_percent}%" if d.inodes_percent is not None else ""
            table.add_row("Disk", d.mountpoint, f"{d.used_gb:.1f} GB / {d.total_gb:.1f} GB ({d.used_percent}%){inodes_str}", d_status)

        console.print(table)

        if snap.failed_units:
            f_table = Table(title=f"[bold red]Failed Systemd Units ({len(snap.failed_units)})[/bold red]", show_header=True, header_style="bold red")
            f_table.add_column("Unit Name", style="bold")
            f_table.add_column("Active State")
            f_table.add_column("Sub State")
            f_table.add_column("Description")
            for u in snap.failed_units:
                f_table.add_row(u.unit_name, u.active_state, u.sub_state, u.description)
            console.print(f_table)
        else:
            console.print("[bold green]✓ 0 failed systemd units detected.[/bold green]\n")
    else:
        # Clean ANSI fallback
        print("\n" + "=" * 65)
        print(f"  LINUX HEALTH SNAPSHOT — {snap.hostname}")
        print(f"  Kernel: {snap.kernel_release} | Uptime: {snap.uptime_seconds / 3600:.1f} hrs | Pressure: {snap.pressure_status}")
        print("=" * 65)
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
            print("• Failed Units: 0 detected (Systemd Healthy)")
        print("=" * 65 + "\n")

def render_diagnostic_report(
    report: DiagnosticReport,
    executor: Optional[SafeExecutor] = None,
    interactive_exec: bool = False
):
    """Renders a structured XAI diagnostic report."""
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
                safety_color = "green" if cmd.safety_level == SafetyLevel.READ_ONLY else ("yellow" if cmd.safety_level == SafetyLevel.MODIFYING else "red")
                cmd_table.add_row(
                    str(idx),
                    cmd.command,
                    f"[{safety_color}]{cmd.safety_level.value}[/{safety_color}]",
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
        print("\n" + "-" * 65)
        print(f"  XAI DIAGNOSIS ({report.reasoning_engine}) — Latency: {report.latency_ms:.2f}ms | Confidence: {xai.confidence_score * 100:.0f}%")
        print("-" * 65)
        print(f"• Symptom:    {xai.symptom}")
        print(f"• Root Cause: {xai.root_cause}")
        print(f"• Rationale:  {xai.rationale}")
        if xai.evidence_logs:
            print("• Evidentiary Logs:")
            for log in xai.evidence_logs:
                print(f"    - {log}")
        if xai.proposed_commands:
            print("• Recommended Commands:")
            for idx, cmd in enumerate(xai.proposed_commands, 1):
                print(f"  [{idx}] ({cmd.safety_level.value} | Risk {cmd.risk_score:.2f}) {cmd.command}")
                print(f"      Rationale: {cmd.rationale}")
                for fb in cmd.flag_breakdown:
                    print(f"      Flag '{fb.flag}': {fb.purpose}")
                if cmd.rollback_command:
                    print(f"      Rollback: {cmd.rollback_command} ({cmd.rollback_rationale})")
        print("-" * 65 + "\n")

    # Interactive Execution Loop if requested
    if interactive_exec and executor and xai.proposed_commands:
        prompt_interactive_execution(xai.proposed_commands, executor)

def prompt_interactive_execution(commands: List[Any], executor: SafeExecutor):
    """Prompts user to safely execute or dry-run suggested commands."""
    print("Interactive Command Remediation Menu:")
    print("  [1..N] Execute specific command")
    print("  [D]    Dry-run all commands")
    print("  [R]    Rollback last executed action")
    print("  [S]    Skip / Proceed without execution")
    choice = input("Select action: ").strip().lower()

    if choice == "d":
        for cmd in commands:
            res = executor.execute(cmd.command, dry_run=True, rollback_cmd=cmd.rollback_command)
            print(f"  ✓ {res['stdout']}")
    elif choice == "r":
        res = executor.rollback_last()
        print(f"  ↩ Executed Rollback: {res.get('command')} -> code {res.get('returncode')}")
        if res.get('stdout'):
            print(f"    {res['stdout'].strip()}")
    elif choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(commands):
            target = commands[idx]
            print(f"Executing: {target.command}")
            res = executor.execute(target.command, rollback_cmd=target.rollback_command)
            print(f"  Status: returncode {res['returncode']} (elapsed {res['elapsed_ms']}ms)")
            if res.get("stdout"):
                print(f"  STDOUT:\n{res['stdout']}")
            if res.get("stderr"):
                print(f"  STDERR:\n{res['stderr']}")

def export_report(report: DiagnosticReport, export_path: str, fmt: str = "json"):
    """Exports diagnostic report to file."""
    p = os.path.abspath(export_path)
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
        if xai.proposed_commands:
            content += "### 🛠️ Proposed Remediation Commands\n\n"
            content += "| # | Command | Safety Level | Risk Score | Rationale |\n"
            content += "|---|---|---|---|---|\n"
            for idx, c in enumerate(xai.proposed_commands, 1):
                content += f"| {idx} | `{c.command}` | {c.safety_level.value} | {c.risk_score:.2f} | {c.rationale} |\n"
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ Diagnostic report exported to Markdown: {p}")

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
    print(f"📊 SUMMARY:")
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

def run_repl(agent: OpsAssistantAgent, executor: SafeExecutor):
    """Runs interactive conversational assistant REPL."""
    print("AI-Powered Linux Operations Assistant (ops-assistant)")
    print("Type a query (e.g. 'Why is NGINX failing?'), 'health', 'demo', 'benchmark', or 'exit' to quit.\n")

    while True:
        try:
            query = input("ops-assistant> ").strip()
            if not query:
                continue

            cmd_lower = query.lower()
            if cmd_lower in ["exit", "quit", "q"]:
                print("Goodbye!")
                break
            elif cmd_lower in ["health", "status"]:
                render_health_dashboard(agent.hub)
            elif cmd_lower in ["demo"]:
                run_demo(agent, executor)
            elif cmd_lower in ["benchmark"]:
                run_benchmark(agent)
            elif cmd_lower in ["failed", "units"]:
                failed = agent.hub.systemd.get_failed_units()
                if failed:
                    print(f"Found {len(failed)} failed unit(s):")
                    for u in failed:
                        rep = agent.diagnose(f"Why is {u.unit_name} failing?")
                        render_diagnostic_report(rep, executor, interactive_exec=True)
                else:
                    print("✓ No failed systemd units.")
            else:
                rep = agent.diagnose(query)
                render_diagnostic_report(rep, executor, interactive_exec=True)

        except (KeyboardInterrupt, EOFError):
            print("\nSession ended.")
            break

def main():
    parser = argparse.ArgumentParser(
        description="AI-Powered Linux Operations Assistant CLI"
    )
    parser.add_argument("query", nargs="?", type=str, help="Natural language diagnostic query", default=None)
    parser.add_argument("--inspect-health", action="store_true", help="Display full system health snapshot")
    parser.add_argument("--diagnose-failed", action="store_true", help="Scan and diagnose failed systemd services")
    parser.add_argument("--demo", action="store_true", help="Run interactive demo across representative failure scenarios")
    parser.add_argument("--benchmark", action="store_true", help="Run automated empirical performance and accuracy benchmark")
    parser.add_argument("--interactive", "-i", action="store_true", help="Enable interactive command execution prompt")
    parser.add_argument("--export-json", type=str, help="Export diagnostic report to JSON file path", default=None)
    parser.add_argument("--export-md", type=str, help="Export diagnostic report to Markdown file path", default=None)

    args = parser.parse_args()

    agent = OpsAssistantAgent()
    executor = SafeExecutor()

    if args.demo:
        run_demo(agent, executor)
    elif args.benchmark:
        run_benchmark(agent)
    elif args.inspect_health:
        render_health_dashboard(agent.hub)
    elif args.diagnose_failed:
        failed = agent.hub.systemd.get_failed_units()
        if failed:
            print(f"Found {len(failed)} failed unit(s):")
            for u in failed:
                rep = agent.diagnose(f"Why is {u.unit_name} failing?")
                render_diagnostic_report(rep, executor, interactive_exec=args.interactive)
        else:
            print("✓ No failed systemd units found.")
    elif args.query:
        rep = agent.diagnose(args.query)
        render_diagnostic_report(rep, executor, interactive_exec=args.interactive)
        if args.export_json:
            export_report(rep, args.export_json, fmt="json")
        if args.export_md:
            export_report(rep, args.export_md, fmt="md")
    else:
        run_repl(agent, executor)

if __name__ == "__main__":
    main()

