"""Explainable AI (XAI) Engine for transparent root-cause reasoning and command deconstruction."""

import re
import shlex
from typing import List, Dict, Tuple, Optional
from ops_assistant.models import (
    XAIExplanation, CommandProposal, CommandFlagExplanation, SafetyLevel
)

RE_SYS_START = re.compile(r"\bsystemctl\s+start\s+([a-zA-Z0-9_-]+)")
RE_SYS_STOP = re.compile(r"\bsystemctl\s+stop\s+([a-zA-Z0-9_-]+)")
RE_SYS_ENABLE = re.compile(r"\bsystemctl\s+enable\s+([a-zA-Z0-9_-]+)")
RE_UFW_ALLOW = re.compile(r"\bufw\s+allow\s+([a-zA-Z0-9_/]+)")
RE_UFW_DENY = re.compile(r"\bufw\s+deny\s+([a-zA-Z0-9_/]+)")

class XAIExplainer:
    FLAG_DICTIONARY: Dict[str, Dict[str, str]] = {
        "journalctl": {
            "-u": "Filters logs strictly to the specified systemd unit name.",
            "-n": "Limits output to the N most recent log lines.",
            "-p": "Filters by syslog priority level (e.g. 0:emerg to 3:err).",
            "-xeu": "Combines: -x (catalog explanation), -e (jump to end), -u (unit filter).",
            "-f": "Follows active log stream in real time.",
            "--since": "Filters log events starting from specified timestamp.",
            "--no-pager": "Outputs raw stream directly without launching terminal pager (less/more)."
        },
        "ss": {
            "-t": "Displays TCP sockets.",
            "-u": "Displays UDP sockets.",
            "-l": "Shows only listening sockets.",
            "-p": "Shows process holding the socket descriptor.",
            "-n": "Renders numeric port numbers rather than resolving service names.",
            "-tulpn": "Combined: TCP, UDP, Listening, Process info, Numeric ports."
        },
        "systemctl": {
            "status": "Displays active/sub state, PID, memory, and recent log journal slice.",
            "restart": "Issues stop followed by start transition on the target unit.",
            "reload": "Asks service daemon to re-read configuration without terminating active connections.",
            "start": "Initiates unit activation sequence.",
            "stop": "Gracefully terminates unit processes via SIGTERM/SIGKILL.",
            "enable": "Creates systemd symlinks so unit automatically starts at boot.",
            "disable": "Removes systemd symlinks to prevent automatic startup at boot.",
            "daemon-reload": "Reloads all systemd unit configuration files from disk.",
            "reset-failed": "Resets the 'failed' state on units that exceeded restart rate limits.",
            "--failed": "Lists all units currently in failed state."
        },
        "df": {
            "-h": "Prints filesystem capacity and usage in human-readable units (MB/GB).",
            "-i": "Prints inode allocation statistics instead of disk block usage.",
            "-T": "Displays filesystem type (ext4, xfs, btrfs, tmpfs) for each partition."
        },
        "free": {
            "-h": "Displays RAM and Swap memory utilization in human-readable gigabytes/megabytes.",
            "-m": "Displays memory statistics in megabytes.",
            "-w": "Displays wide output separating active buffers and cache columns."
        },
        "ps": {
            "aux": "Lists all running processes across all users with CPU/MEM percentages.",
            "--sort=-%mem": "Sorts process table descending by memory consumption.",
            "--sort=-%cpu": "Sorts process table descending by CPU utilization.",
            "-ef": "Standard full-format process listing.",
            "axjf": "Displays hierarchical process tree showing parent-child PID relationships."
        },
        "nginx": {
            "-t": "Tests configuration files for syntax errors and structural validity without restarting.",
            "-T": "Dumps entire merged configuration with syntax test output.",
            "-s": "Sends signal (stop, quit, reopen, reload) to running master process."
        },
        "apache2ctl": {
            "configtest": "Parses and verifies Apache HTTP server configuration files for errors.",
            "status": "Displays live Apache runtime worker thread statistics."
        },
        "ip": {
            "-br": "Renders concise one-line brief network interface table.",
            "a": "Displays IP addresses assigned to all network interfaces.",
            "addr": "Displays IP addresses assigned to all network interfaces.",
            "link": "Displays link-layer status (UP/DOWN/CARRIER) for interfaces.",
            "route": "Displays kernel routing table with default gateways and metrics.",
            "neigh": "Displays ARP neighbor cache entries."
        },
        "lsof": {
            "-i": "Lists all open internet network sockets.",
            "-P": "Inhibits conversion of port numbers to service names.",
            "-n": "Inhibits IP address resolution to hostnames for faster output.",
            "+D": "Recursively searches for open file handles within target directory."
        },
        "curl": {
            "-I": "Fetches HTTP response headers only (HEAD request).",
            "-v": "Enables verbose debugging output including TLS handshake logs.",
            "-k": "Allows insecure SSL connections (ignores untrusted certificates).",
            "-s": "Silent mode (suppresses progress bar and error messages).",
            "--connect-timeout": "Maximum time in seconds allowed for network connection attempt."
        },
        "dmesg": {
            "-T": "Renders human-readable timestamps on kernel log messages.",
            "--level=err,crit": "Filters kernel ring buffer strictly to errors and critical faults.",
            "-w": "Follows new kernel messages in real time.",
            "-c": "Clears the kernel ring buffer after printing."
        },
        "iostat": {
            "-x": "Displays extended disk I/O metrics including %util, await, and queue size.",
            "-d": "Displays block device throughput in sectors/second.",
            "-z": "Omits devices with zero activity for cleaner output."
        },
        "vmstat": {
            "-s": "Displays cumulative event counter statistics (page faults, context switches).",
            "-d": "Displays disk statistics summary table."
        },
        "timedatectl": {
            "status": "Displays local time, UTC time, RTC time, and NTP synchronization state.",
            "set-ntp": "Enables or disables automatic network time synchronization.",
            "timesync-status": "Displays offset, jitter, and upstream NTP server details."
        },
        "ufw": {
            "status": "Displays firewall operational state and active allow/deny rule table.",
            "allow": "Adds firewall rule allowing ingress traffic on specified port/protocol.",
            "deny": "Adds firewall rule dropping ingress traffic on specified port/protocol.",
            "reload": "Re-reads firewall rule tables without dropping active connection state."
        },
        "iptables": {
            "-L": "Lists all active firewall filter rules.",
            "-n": "Displays IP addresses and port numbers numerically.",
            "-v": "Displays packet and byte counters for matching rules.",
            "-F": "Flushes (deletes) all rules in target chain or table."
        },
        "dpkg": {
            "--configure": "Reconfigures unpacked packages that failed during previous install.",
            "-a": "Applies configuration action to all pending unconfigured packages.",
            "-l": "Lists all installed packages matching pattern."
        },
        "apt": {
            "update": "Fetches updated package index files from configured repository sources.",
            "-f": "Fixes broken package dependencies and incomplete installations.",
            "clean": "Clears downloaded .deb package cache from /var/cache/apt/archives/."
        },
        "openssl": {
            "s_client": "Initiates generic SSL/TLS client connection to test server certificates.",
            "-connect": "Specifies target host:port endpoint for TLS handshake testing.",
            "-servername": "Passes SNI (Server Name Indication) extension for virtual hosting.",
            "x509": "Displays certificate fields, expiration dates, and issuer fingerprints."
        },
        "docker": {
            "ps": "Lists running container instances.",
            "logs": "Fetches stdout and stderr streams from specified container.",
            "inspect": "Displays low-level JSON configuration and state of container or image.",
            "restart": "Stops and re-creates container process."
        }
    }

    def generate_rollback_command(self, command_str: str) -> Tuple[Optional[str], Optional[str]]:
        """Synthesizes safe undo/rollback commands for state-modifying actions with precompiled regex patterns."""
        stripped = command_str.strip()
        
        # Systemctl start -> stop
        m = RE_SYS_START.search(stripped)
        if m:
            svc = m.group(1)
            return f"sudo systemctl stop {svc}", f"Stops {svc} if newly started service proves unstable."

        # Systemctl stop -> start
        m = RE_SYS_STOP.search(stripped)
        if m:
            svc = m.group(1)
            return f"sudo systemctl start {svc}", f"Restarts {svc} to return to previous running state."

        # Systemctl enable -> disable
        m = RE_SYS_ENABLE.search(stripped)
        if m:
            svc = m.group(1)
            return f"sudo systemctl disable {svc}", f"Disables {svc} boot startup symlink."

        # UFW allow -> delete allow
        m = RE_UFW_ALLOW.search(stripped)
        if m:
            rule = m.group(1)
            return f"sudo ufw delete allow {rule}", f"Deletes firewall allow rule for {rule}."

        # UFW deny -> delete deny
        m = RE_UFW_DENY.search(stripped)
        if m:
            rule = m.group(1)
            return f"sudo ufw delete deny {rule}", f"Deletes firewall deny rule for {rule}."

        return None, None

    def deconstruct_command(self, command_str: str) -> List[CommandFlagExplanation]:
        """Breaks down command flags and verbs into transparent human explanations with fast tokenizer."""
        explanations: List[CommandFlagExplanation] = []
        if '"' not in command_str and "'" not in command_str and "\\" not in command_str:
            tokens = command_str.split()
        else:
            try:
                tokens = shlex.split(command_str)
            except Exception:
                tokens = command_str.split()

        if not tokens:
            return []

        has_sudo = tokens[0] == "sudo"
        exec_tokens = tokens[1:] if has_sudo and len(tokens) > 1 else tokens
        base_cmd = exec_tokens[0] if exec_tokens else ""

        dict_entries = self.FLAG_DICTIONARY.get(base_cmd)

        if dict_entries is not None:
            for token in exec_tokens[1:]:
                purpose = dict_entries.get(token)
                if purpose is not None:
                    explanations.append(CommandFlagExplanation(flag=token, purpose=purpose))
                elif token.startswith("-"):
                    explanations.append(CommandFlagExplanation(flag=token, purpose=f"Option flag passed to {base_cmd}."))
        else:
            for token in exec_tokens[1:]:
                if token.startswith("-"):
                    explanations.append(CommandFlagExplanation(flag=token, purpose=f"Option flag passed to {base_cmd}."))

        return explanations

    def synthesize_xai(
        self,
        symptom: str,
        root_cause: str,
        evidence_logs: List[str],
        commands: List[Tuple[str, SafetyLevel, float, str]],
        rationale: str,
        confidence: float = 0.95,
        mitigation_steps: Optional[List[str]] = None
    ) -> XAIExplanation:
        """Synthesizes a fully grounded XAIExplanation object."""
        proposals: List[CommandProposal] = []

        for cmd_str, safety, risk_score, cmd_rationale in commands:
            flags = self.deconstruct_command(cmd_str)
            requires_sudo = cmd_str.startswith("sudo ") or safety in [SafetyLevel.MODIFYING, SafetyLevel.HIGH_RISK]
            rollback_cmd, rollback_rat = self.generate_rollback_command(cmd_str)
            proposals.append(CommandProposal(
                command=cmd_str,
                safety_level=safety,
                risk_score=risk_score,
                flag_breakdown=flags,
                rationale=cmd_rationale,
                requires_sudo=requires_sudo,
                rollback_command=rollback_cmd,
                rollback_rationale=rollback_rat
            ))

        steps = mitigation_steps or [
            "Verify current service and system state with read-only diagnostic commands.",
            "Review proposed remediation command rationale and safety tier.",
            "Execute remediation with step-by-step confirmation.",
            "Verify service recovery and monitor logs for residual anomalies."
        ]

        return XAIExplanation(
            symptom=symptom,
            root_cause=root_cause,
            evidence_logs=evidence_logs[:5],
            confidence_score=confidence,
            rationale=rationale,
            proposed_commands=proposals,
            mitigation_steps=steps
        )

