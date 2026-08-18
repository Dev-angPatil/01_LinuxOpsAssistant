"""Command Safety Validator for Linux Operations Assistant."""

import re
import shlex
from typing import Tuple, List
from ops_assistant.models import SafetyLevel

class CommandSafetyValidator:
    READ_ONLY_COMMANDS = {
        "cat", "ls", "less", "more", "head", "tail", "grep", "awk", "sed",
        "journalctl", "dmesg", "ss", "netstat", "lsof", "ps", "top", "htop",
        "free", "df", "du", "uptime", "uname", "ip", "ifconfig", "ping",
        "systemctl status", "systemctl is-active", "systemctl is-failed",
        "systemctl list-units", "nginx -t", "apache2ctl configtest"
    }

    MODIFYING_COMMANDS = {
        "systemctl restart", "systemctl reload", "systemctl start", "systemctl stop",
        "systemctl enable", "systemctl disable", "touch", "mkdir", "cp", "mv",
        "service", "systemd-resolve --flush-caches"
    }

    CATASTROPHIC_PATTERNS = [
        r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|[a-zA-Z]*f[a-zA-Z]*r)\s+(/|/\*|/\.|~|\$HOME)",
        r"\bmkfs(\.[a-zA-Z0-9]+)?\s+/dev/",
        r"\bdd\s+.*of=/dev/(sd[a-z]|nvme[0-9]n[0-9]|hd[a-z]|kmem|mem|null)",
        r"\bchmod\s+(-R\s+)?(777|000)\s+/(etc|boot|sys|proc|var|usr|bin|lib)?\b",
        r">\s*/dev/(sd[a-z]|nvme|kmem|mem)",
        r":\(\)\s*{\s*:\|:&\s*};\s*:",  # Fork bomb
        r">\s*/etc/(passwd|shadow|sudoers|fstab)",  # Clobbering critical auth/mount files
        r"\bkill\s+-9\s+-1\b",  # Kill all processes
        r"\b(curl|wget)\s+.*\|\s*(sudo\s+)?(bash|sh)\b"  # Unvalidated remote pipe execution
    ]

    def evaluate_safety(self, command_str: str) -> Tuple[SafetyLevel, float, str]:
        """Evaluates command string and returns (SafetyLevel, risk_score, reason)."""
        stripped = command_str.strip()
        if not stripped:
            return SafetyLevel.READ_ONLY, 0.0, "Empty command."

        # 1. Check for catastrophic/destructive patterns
        for pattern in self.CATASTROPHIC_PATTERNS:
            if re.search(pattern, stripped, flags=re.IGNORECASE):
                return (
                    SafetyLevel.DESTRUCTIVE,
                    1.0,
                    "Catastrophic destructive pattern detected: targets root, system block device, critical auth file, or triggers fork bomb."
                )

        try:
            tokens = shlex.split(stripped)
        except Exception:
            tokens = stripped.split()

        has_sudo = tokens[0] == "sudo"
        exec_tokens = tokens[1:] if has_sudo and len(tokens) > 1 else tokens
        base_cmd = exec_tokens[0] if exec_tokens else ""
        sub_cmd = f"{base_cmd} {exec_tokens[1]}" if len(exec_tokens) > 1 else base_cmd

        # 2. Check Read-Only
        if sub_cmd in self.READ_ONLY_COMMANDS or base_cmd in self.READ_ONLY_COMMANDS:
            if not any(redirect in stripped for redirect in [">", ">>", "| sudo tee"]):
                return SafetyLevel.READ_ONLY, 0.05, "Non-mutating diagnostic inspection command."

        # 3. Check Modifying
        if sub_cmd in self.MODIFYING_COMMANDS or base_cmd in self.MODIFYING_COMMANDS:
            return SafetyLevel.MODIFYING, 0.35, "Standard service state transition or safe file modification."

        # 4. Check High Risk
        if base_cmd in ["kill", "pkill", "killall", "iptables", "nft", "ufw", "reboot", "shutdown", "sysctl"]:
            return SafetyLevel.HIGH_RISK, 0.70, "Process termination, kernel parameter tuning, or networking firewall modification."

        if base_cmd in ["rm", "chmod", "chown", "dpkg", "apt", "apt-get"]:
            is_recursive = any("r" in t.lower() for t in exec_tokens if t.startswith("-"))
            if is_recursive or base_cmd in ["dpkg", "apt", "apt-get"]:
                return SafetyLevel.HIGH_RISK, 0.75, "Package alteration or recursive file permission/deletion modification."
            return SafetyLevel.MODIFYING, 0.40, "Local file or package alteration."

        return SafetyLevel.MODIFYING, 0.50, "Unclassified system command."

