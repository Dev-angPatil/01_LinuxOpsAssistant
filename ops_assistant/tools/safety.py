"""Command Safety Validator and AST Security Sandbox for Linux Operations Assistant.

Provides multi-stage AST parsing, obfuscation decoding (Base64, Hex, Octal, ANSI-C),
subshell and pipeline isolation, interpreter code inspection, and comprehensive
destructive pattern gating.
"""

import re
import ast
import shlex
import base64
from typing import Tuple, List, Dict, Set, Optional, Any
from dataclasses import dataclass, field

from ops_assistant.models import SafetyLevel


@dataclass
class SafetyValidationResult:
    """Structured result of safety validation on a shell command."""
    command: str
    level: SafetyLevel
    risk_score: float
    matched_rule: str
    is_destructive: bool
    suggested_rollback: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "level": self.level.value,
            "risk_score": self.risk_score,
            "matched_rule": self.matched_rule,
            "is_destructive": self.is_destructive,
            "suggested_rollback": self.suggested_rollback
        }


@dataclass
class CommandASTNode:
    """Represents a parsed AST node in a compound shell pipeline."""
    raw: str
    tokens: List[str] = field(default_factory=list)
    base_cmd: str = ""
    sub_cmd: str = ""
    has_sudo: bool = False
    redirects: List[Tuple[str, str]] = field(default_factory=list)
    subshells: List[str] = field(default_factory=list)
    obfuscation_detected: List[str] = field(default_factory=list)
    safety_level: SafetyLevel = SafetyLevel.MODIFYING
    risk_score: float = 0.50
    reason: str = ""


class CommandSafetyValidator:
    """Rigorous AST-based safety validator and de-obfuscation filter."""

    READ_ONLY_COMMANDS: Set[str] = {
        "cat", "ls", "less", "more", "head", "tail", "grep", "egrep", "fgrep", "awk",
        "sed", "journalctl", "dmesg", "ss", "netstat", "lsof", "ps", "top", "htop",
        "free", "df", "du", "uptime", "uname", "ip", "ifconfig", "ping", "traceroute",
        "systemctl status", "systemctl is-active", "systemctl is-failed",
        "systemctl list-units", "systemctl list-unit-files", "nginx -t",
        "apache2ctl configtest", "apachectl configtest", "fuser", "dnf check",
        "nft list", "nft list ruleset", "firewall-cmd --state", "firewall-cmd --list-all",
        "sestatus", "aa-status", "apparmor_status", "timedatectl", "chronyc tracking",
        "chronyc sources", "curl -I", "which", "whereis", "find", "stat", "wc",
        "diff", "cmp", "file", "id", "whoami", "w", "last", "lsblk", "lscpu",
        "lsmod", "sysctl -a", "sysctl -n", "sysctl -p", "resolvectl status",
        "systemd-resolve --status", "hostnamectl", "loginctl", "awall list",
        "apk info", "pacman -Q", "rpm -qa", "dpkg -l", "apt list", "echo", "printf"
    }

    MODIFYING_COMMANDS: Set[str] = {
        "systemctl restart", "systemctl reload", "systemctl start", "systemctl stop",
        "systemctl enable", "systemctl disable", "systemctl reset-failed",
        "service", "touch", "mkdir", "cp", "mv", "systemd-resolve --flush-caches",
        "resolvectl flush-caches", "truncate"
    }

    HIGH_RISK_COMMANDS: Set[str] = {
        "kill", "pkill", "killall", "iptables", "ip6tables", "nft", "ufw",
        "firewall-cmd", "awall", "reboot", "shutdown", "sysctl", "dpkg", "apt",
        "apt-get", "dnf", "yum", "pacman", "zypper", "apk", "rpm", "chmod",
        "chown", "chgrp", "useradd", "userdel", "usermod", "passwd", "groupadd",
        "groupdel", "groupmod", "crontab", "mkswap", "swapon", "swapoff",
        "init", "telinit", "mount", "umount", "modprobe", "rmmod", "insmod"
    }

    DESTRUCTIVE_COMMANDS: Set[str] = {
        "mkfs", "mkfs.ext2", "mkfs.ext3", "mkfs.ext4", "mkfs.xfs", "mkfs.btrfs",
        "mkfs.vfat", "mkfs.fat", "mkfs.ntfs", "mkfs.cramfs", "wipefs", "blkdiscard",
        "fdisk", "gdisk", "parted", "sfdisk", "shred"
    }

    CATASTROPHIC_PATTERNS: List[str] = [
        # Recursive rm targeting root, home, or core system mount points
        r"\brm\s+([^\s]*\s+)*(-[a-zA-Z]*r[a-zA-Z]*|[a-zA-Z]*--recursive)\s+.*(/|/\*|/\.|~|\$HOME|\$\{HOME\}|/etc|/boot|/sys|/proc|/var|/usr|/bin|/sbin|/lib(64)?|/root)\b",
        r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|[a-zA-Z]*f[a-zA-Z]*r)\s+(/|/\*|/\.|~|\$HOME|\$\{HOME\}|/etc|/boot|/sys|/proc|/var|/usr|/bin|/sbin|/lib(64)?|/root)\b",
        r"\brm\s+-[a-zA-Z]*f[a-zA-Z]*\s+/etc/(passwd|shadow|sudoers|fstab|crypttab|gshadow)\b",
        # Disk formatting / partitioning wipes
        r"\bmkfs(\.[a-zA-Z0-9]+)?\s+/dev/",
        r"\b(wipefs\s+-a|blkdiscard)\s+/dev/",
        # dd writing to raw storage devices, kernel memory, or zeroing disks
        r"\bdd\s+.*of=/dev/(sd[a-z]|nvme[0-9]n[0-9]|vd[a-z]|hd[a-z]|kmem|mem|null)",
        # chmod 777 or 000 on root or system root directories
        r"\bchmod\s+(-[a-zA-Z]*R[a-zA-Z]*\s+)?(777|000|u-rwx|a-rwx)\s+/(etc|boot|sys|proc|var|usr|bin|sbin|lib(64)?|root)?\b",
        r"\bchmod\s+([^\s]+\s+)?(777|000)\s+/etc/(shadow|passwd|sudoers)",
        # Raw redirections overwriting block devices or critical system auth / kernel triggers
        r">\s*/dev/(sd[a-z]|nvme|vd[a-z]|hd[a-z]|kmem|mem)",
        r">\s*/etc/(passwd|shadow|sudoers|fstab|crypttab|gshadow)",
        r">\s*/proc/sysrq-trigger",
        r">\s*/boot/(vmlinuz|initrd|grub)",
        # Fork bombs (classic, variants, and recursive shell functions)
        r":\(\)\s*{\s*:\|:&\s*};\s*:",
        r":\(\)\s*{\s*:\|:&\s*};:",
        r"\b[a-zA-Z0-9_]+\(\)\s*{\s*[a-zA-Z0-9_]+\s*\|\s*[a-zA-Z0-9_]+\s*&\s*};\s*[a-zA-Z0-9_]+",
        # Total process termination / init killing
        r"\bkill\s+-9\s+-1\b",
        r"\bkillall\s+-9\s+init\b",
        r"\bkill\s+-9\s+1\b",
        # Remote unvalidated shell execution pipelines
        r"\b(curl|wget|fetch)\s+.*\|\s*(sudo\s+)?(bash|sh|zsh|dash)\b",
        r"\b(bash|sh|zsh)\s+<\(\s*(curl|wget|fetch)\b",
        # Reverse shells & raw network redirects
        r"(&>|>&|>)\s*/dev/(tcp|udp)/[0-9a-zA-Z\.\-]+/[0-9]+",
        r"\bnc(\.traditional)?\s+.*-e\s+/(bin/)?(sh|bash)"
    ]

    _COMPILED_CATASTROPHIC: List[re.Pattern] = [
        re.compile(p, re.IGNORECASE) for p in CATASTROPHIC_PATTERNS
    ]

    CRITICAL_ROOT_TARGETS: Set[str] = {
        "/", "/*", "/.", "~", "$HOME", "${HOME}",
        "/etc", "/boot", "/sys", "/proc", "/var", "/usr",
        "/bin", "/sbin", "/lib", "/lib64", "/root"
    }

    CRITICAL_AUTH_FILES: Set[str] = {
        "/etc/passwd", "/etc/shadow", "/etc/sudoers", "/etc/fstab",
        "/etc/crypttab", "/etc/gshadow", "/etc/group"
    }

    # -------------------------------------------------------------------------
    # Obfuscation Detection & Decoding Helpers
    # -------------------------------------------------------------------------

    def unescape_hex_octal(self, cmd_str: str) -> Tuple[str, List[str]]:
        """Detects and unescapes Hex (\\xHH), Octal (\\OOO), and ANSI-C ($'...') escapes."""
        findings = []

        def replace_hex(m):
            try:
                dec = bytes.fromhex(m.group(1)).decode("utf-8", errors="ignore")
                findings.append(f"Hex escape \\x{m.group(1)} -> '{dec}'")
                return dec
            except Exception:
                return m.group(0)

        def replace_oct(m):
            try:
                dec = chr(int(m.group(1), 8))
                findings.append(f"Octal escape \\{m.group(1)} -> '{dec}'")
                return dec
            except Exception:
                return m.group(0)

        s = re.sub(r"\\x([0-9a-fA-F]{2})", replace_hex, cmd_str)
        s = re.sub(r"\\([0-7]{1,3})", replace_oct, s)
        # Handle ANSI-C quoting $'...'
        s = re.sub(r"\$'(.*?)'", r"\1", s)

        # Handle xxd hex dumps e.g. xxd -r -p <<< "..."
        xxd_matches = re.findall(r"xxd\s+(?:-r|-p|\s)+\s*<<<\s*['\"]([0-9a-fA-F]+)['\"]", cmd_str)
        for hex_str in xxd_matches:
            try:
                dec = bytes.fromhex(hex_str).decode("utf-8", errors="ignore")
                findings.append(f"xxd hex stream '{hex_str}' -> '{dec}'")
                s = s + f" ; {dec}"
            except Exception:
                pass

        return s, findings

    def extract_and_decode_base64(self, cmd_str: str) -> List[Tuple[str, str]]:
        """Extracts potential Base64 strings in pipeline/arguments and decodes them."""
        decoded_pairs = []
        candidates = re.findall(r"[A-Za-z0-9+/]{4,}={0,2}", cmd_str)
        for cand in candidates:
            if len(cand) % 4 != 0:
                continue
            try:
                raw = base64.b64decode(cand, validate=True)
                text = raw.decode("utf-8")
                if text.isprintable() and len(text.strip()) > 0:
                    decoded_pairs.append((cand, text))
            except Exception:
                pass
        return decoded_pairs

    def deobfuscate(self, cmd_str: str) -> Tuple[str, List[str]]:
        """Applies comprehensive deobfuscation and returns (expanded_command, detected_techniques)."""
        detected_techniques = []
        expanded, hex_findings = self.unescape_hex_octal(cmd_str)
        if hex_findings:
            detected_techniques.extend(hex_findings)

        b64_pairs = self.extract_and_decode_base64(cmd_str)
        for cand, decoded in b64_pairs:
            detected_techniques.append(f"Base64 payload '{cand}' -> '{decoded}'")
            if re.search(r"base64\s+(?:-d|--decode)", cmd_str, re.IGNORECASE) or \
               re.search(r"\|\s*(sudo\s+)?(sh|bash|zsh)", cmd_str, re.IGNORECASE):
                expanded = expanded + f" ; {decoded}"

        # If echo or printf is piped to bash/sh/zsh, also evaluate inner payload
        m_pipe = re.search(r"(?:echo|printf)\s+(?:-[a-zA-Z]+\s+)?['\"](.+?)['\"]\s*\|\s*(?:sudo\s+)?(?:bash|sh|zsh|dash)", expanded)
        if m_pipe:
            inner_cmd = m_pipe.group(1).strip()
            detected_techniques.append(f"Piped shell string -> '{inner_cmd}'")
            expanded = expanded + f" ; {inner_cmd}"

        return expanded, detected_techniques

    # -------------------------------------------------------------------------
    # Compound Command and Subshell Splitting
    # -------------------------------------------------------------------------

    def split_compound_commands(self, cmd_str: str) -> List[str]:
        """Splits command string on ;, &&, ||, \\n, & while respecting quotes."""
        commands = []
        current = []
        in_single = False
        in_double = False
        escape = False
        chars = list(cmd_str)
        i = 0

        while i < len(chars):
            c = chars[i]
            if escape:
                current.append(c)
                escape = False
                i += 1
                continue
            if c == "\\":
                escape = True
                current.append(c)
                i += 1
                continue
            if c == "'" and not in_double:
                in_single = not in_single
                current.append(c)
                i += 1
                continue
            if c == '"' and not in_single:
                in_double = not in_double
                current.append(c)
                i += 1
                continue
            if not in_single and not in_double:
                if chars[i:i+2] == ["&", "&"] or chars[i:i+2] == ["|", "|"]:
                    part = "".join(current).strip()
                    if part:
                        commands.append(part)
                    current = []
                    i += 2
                    continue
                elif c in (";", "\n", "&"):
                    part = "".join(current).strip()
                    if part:
                        commands.append(part)
                    current = []
                    i += 1
                    continue
            current.append(c)
            i += 1

        rem = "".join(current).strip()
        if rem:
            commands.append(rem)
        return commands

    def split_pipeline_stages(self, cmd_str: str) -> List[str]:
        """Splits a single command segment into pipeline stages (| or |&) respecting quotes."""
        stages = []
        current = []
        in_single = False
        in_double = False
        escape = False
        chars = list(cmd_str)
        i = 0

        while i < len(chars):
            c = chars[i]
            if escape:
                current.append(c)
                escape = False
                i += 1
                continue
            if c == "\\":
                escape = True
                current.append(c)
                i += 1
                continue
            if c == "'" and not in_double:
                in_single = not in_single
                current.append(c)
                i += 1
                continue
            if c == '"' and not in_single:
                in_double = not in_double
                current.append(c)
                i += 1
                continue
            if not in_single and not in_double:
                if chars[i:i+2] == ["|", "|"]:
                    current.append(c)
                    current.append(chars[i+1])
                    i += 2
                    continue
                elif chars[i:i+2] == ["|", "&"]:
                    part = "".join(current).strip()
                    if part:
                        stages.append(part)
                    current = []
                    i += 2
                    continue
                elif c == "|":
                    part = "".join(current).strip()
                    if part:
                        stages.append(part)
                    current = []
                    i += 1
                    continue
            current.append(c)
            i += 1

        rem = "".join(current).strip()
        if rem:
            stages.append(rem)
        return stages

    def extract_subshells(self, cmd_str: str) -> List[str]:
        """Extracts subshell commands from $(...), `...`, <(...), >(...)."""
        subshells = []
        dollar_subs = re.findall(r"\$\((.+?)\)", cmd_str)
        subshells.extend(dollar_subs)
        backtick_subs = re.findall(r"`([^`]+)`", cmd_str)
        subshells.extend(backtick_subs)
        proc_subs = re.findall(r"[<>]\((.+?)\)", cmd_str)
        subshells.extend(proc_subs)
        return [s.strip() for s in subshells if s.strip()]

    # -------------------------------------------------------------------------
    # Inline Interpreter Code Safety Inspection (Python, Perl, Node, Ruby, Shell)
    # -------------------------------------------------------------------------

    def evaluate_inline_code(self, interpreter: str, code: str) -> Tuple[SafetyLevel, float, str]:
        """Inspects inline interpreter scripts (-c, -e, -r) for destructive operations."""
        interp = interpreter.lower()
        if interp in ("python", "python3", "python2"):
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        # Detect shutil.rmtree
                        if isinstance(node.func, ast.Attribute) and node.func.attr == "rmtree":
                            if node.args and isinstance(node.args[0], ast.Constant):
                                target = str(node.args[0].value).strip()
                                if target in self.CRITICAL_ROOT_TARGETS:
                                    return (
                                        SafetyLevel.DESTRUCTIVE,
                                        1.0,
                                        f"Destructive Python AST operation: shutil.rmtree targeting '{target}'."
                                    )
                            return (
                                SafetyLevel.HIGH_RISK,
                                0.75,
                                "Python AST operation: recursive shutil.rmtree modification."
                            )

                        # Detect os.remove / os.unlink on critical files
                        if isinstance(node.func, ast.Attribute) and node.func.attr in ("remove", "unlink"):
                            if node.args and isinstance(node.args[0], ast.Constant):
                                target = str(node.args[0].value).strip()
                                if any(target == auth or target.startswith(auth) for auth in self.CRITICAL_AUTH_FILES):
                                    return (
                                        SafetyLevel.DESTRUCTIVE,
                                        1.0,
                                        f"Destructive Python AST operation: unlinking critical file '{target}'."
                                    )

                        # Detect os.system / subprocess calls with embedded shell commands
                        if isinstance(node.func, ast.Attribute) and node.func.attr in ("system", "popen", "run", "call", "Popen"):
                            for arg in node.args:
                                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                    inner_lvl, inner_risk, inner_reason = self.evaluate_safety(arg.value)
                                    if inner_lvl in (SafetyLevel.DESTRUCTIVE, SafetyLevel.HIGH_RISK):
                                        return inner_lvl, inner_risk, f"Python inline code invoking dangerous shell command: {inner_reason}"

                        # Detect os.fork bombs
                        if isinstance(node.func, ast.Attribute) and node.func.attr == "fork":
                            return SafetyLevel.DESTRUCTIVE, 1.0, "Destructive Python AST operation: unbounded fork invocation."
            except Exception:
                pass

            if re.search(r"rmtree\s*\(\s*['\"](/|/\*|~|/etc|/boot)['\"]\s*\)", code):
                return SafetyLevel.DESTRUCTIVE, 1.0, "Destructive Python operation targeting root/system directory."
            if re.search(r"os\.system\s*\(\s*['\"].*rm\s+-rf\s+/.*['\"]\s*\)", code):
                return SafetyLevel.DESTRUCTIVE, 1.0, "Destructive Python command execution targeting root."

        elif interp in ("bash", "sh", "zsh", "dash"):
            return self.evaluate_safety(code)

        elif interp in ("perl", "ruby", "node", "nodejs", "php"):
            if re.search(r"(system|exec|execSync|spawnSync)\s*\(.*rm\s+-rf\s+/.*", code):
                return SafetyLevel.DESTRUCTIVE, 1.0, f"Destructive inline {interp} script invoking recursive root removal."
            if re.search(r"(unlink|rmdir|rmtree)\s*\(.*['\"](/|/etc|/boot)['\"].*", code):
                return SafetyLevel.DESTRUCTIVE, 1.0, f"Destructive inline {interp} script unlinking system paths."

        return SafetyLevel.MODIFYING, 0.50, f"Inline script execution via {interp}."

    # -------------------------------------------------------------------------
    # Single AST Node Evaluation
    # -------------------------------------------------------------------------

    def evaluate_node(self, node: CommandASTNode) -> Tuple[SafetyLevel, float, str]:
        """Evaluates a single parsed AST node."""
        raw = node.raw.strip()
        if not raw:
            return SafetyLevel.READ_ONLY, 0.0, "Empty command."

        # 1. Catastrophic Regex Check on Raw
        for pat in self.CATASTROPHIC_PATTERNS:
            if re.search(pat, raw, flags=re.IGNORECASE):
                return (
                    SafetyLevel.DESTRUCTIVE,
                    1.0,
                    "Catastrophic destructive pattern detected: targets root, system block device, critical auth file, or triggers fork bomb."
                )

        tokens = node.tokens
        if not tokens:
            return SafetyLevel.MODIFYING, 0.50, "Unclassified system command."

        has_sudo = tokens[0] == "sudo"
        exec_tokens = tokens[1:] if has_sudo and len(tokens) > 1 else tokens
        base_cmd = exec_tokens[0] if exec_tokens else ""
        sub_cmd = f"{base_cmd} {exec_tokens[1]}" if len(exec_tokens) > 1 else base_cmd

        # 2. Check Redirects
        for op, target in node.redirects:
            if re.search(r"^/dev/(sd[a-z]|nvme|vd[a-z]|hd[a-z]|kmem|mem|port)", target):
                return SafetyLevel.DESTRUCTIVE, 1.0, f"Destructive file redirection overwriting raw block device '{target}'."
            if target in self.CRITICAL_AUTH_FILES or target.startswith("/etc/pam.d/"):
                return SafetyLevel.DESTRUCTIVE, 1.0, f"Destructive file redirection clobbering critical authentication file '{target}'."
            if target == "/proc/sysrq-trigger":
                return SafetyLevel.DESTRUCTIVE, 1.0, "Destructive file redirection triggering kernel sysrq state change."

        # 3. Check Known Destructive Commands
        if base_cmd in self.DESTRUCTIVE_COMMANDS:
            for t in exec_tokens[1:]:
                if t.startswith("/dev/"):
                    return SafetyLevel.DESTRUCTIVE, 1.0, f"Destructive disk formatting/partitioning command targeting '{t}'."
            return SafetyLevel.DESTRUCTIVE, 1.0, f"Destructive filesystem wipe/partition tool '{base_cmd}'."

        # 4. Check Inline Interpreter Code (-c, -e, -r)
        if base_cmd in ("python", "python3", "python2", "perl", "ruby", "node", "nodejs", "php", "bash", "sh", "zsh"):
            for i, t in enumerate(exec_tokens):
                if t in ("-c", "-e", "-r") and i + 1 < len(exec_tokens):
                    code_snippet = exec_tokens[i + 1]
                    code_lvl, code_risk, code_reason = self.evaluate_inline_code(base_cmd, code_snippet)
                    if code_lvl == SafetyLevel.DESTRUCTIVE:
                        return code_lvl, code_risk, code_reason
                    if code_lvl == SafetyLevel.HIGH_RISK:
                        return code_lvl, code_risk, code_reason

        # 5. Check 'eval' and 'exec' and 'source'
        if base_cmd in ("eval", "exec", "source", "."):
            if len(exec_tokens) > 1:
                inner = " ".join(exec_tokens[1:])
                inner_lvl, inner_risk, inner_reason = self.evaluate_safety(inner)
                if inner_lvl == SafetyLevel.DESTRUCTIVE:
                    return inner_lvl, inner_risk, f"Destructive command inside dynamic evaluation '{base_cmd}': {inner_reason}"
                return SafetyLevel.HIGH_RISK, max(0.65, inner_risk), f"Dynamic execution '{base_cmd}' evaluating inner arguments."

        # 6. Check 'rm', 'chmod', 'chown'
        if base_cmd == "rm":
            is_recursive = any("r" in t.lower() for t in exec_tokens if t.startswith("-"))
            targets = [t for t in exec_tokens[1:] if not t.startswith("-")]
            for tgt in targets:
                tgt_clean = tgt.rstrip("/")
                if is_recursive and (tgt_clean in self.CRITICAL_ROOT_TARGETS or tgt_clean == ""):
                    return SafetyLevel.DESTRUCTIVE, 1.0, f"Destructive recursive deletion targeting critical system path '{tgt}'."
                if tgt_clean in self.CRITICAL_AUTH_FILES:
                    return SafetyLevel.DESTRUCTIVE, 1.0, f"Destructive deletion of critical authentication file '{tgt}'."
            if is_recursive:
                return SafetyLevel.HIGH_RISK, 0.75, "Recursive file deletion modification."
            return SafetyLevel.MODIFYING, 0.40, "Local file deletion."

        if base_cmd in ("chmod", "chown", "chgrp"):
            is_recursive = any("r" in t.lower() for t in exec_tokens if t.startswith("-"))
            targets = [t for t in exec_tokens[1:] if not t.startswith("-")]
            for tgt in targets:
                tgt_clean = tgt.rstrip("/")
                if is_recursive and (tgt_clean in self.CRITICAL_ROOT_TARGETS or tgt_clean == ""):
                    return SafetyLevel.DESTRUCTIVE, 1.0, f"Destructive recursive permission/ownership modification on root '{tgt}'."
                if tgt_clean in self.CRITICAL_AUTH_FILES:
                    return SafetyLevel.DESTRUCTIVE, 1.0, f"Destructive permission change on critical authentication file '{tgt}'."
            if is_recursive:
                return SafetyLevel.HIGH_RISK, 0.75, "Recursive permission or ownership change."
            return SafetyLevel.MODIFYING, 0.40, "Local permission or ownership modification."

        # 7. Check 'dd'
        if base_cmd == "dd":
            for t in exec_tokens[1:]:
                if t.startswith("of=/dev/"):
                    return SafetyLevel.DESTRUCTIVE, 1.0, f"Destructive raw storage device write via dd '{t}'."
            return SafetyLevel.HIGH_RISK, 0.70, "Block device copy via dd."

        # 8. Check Read-Only Whitelist (Checked BEFORE High-Risk to permit commands like 'firewall-cmd --state')
        if sub_cmd in self.READ_ONLY_COMMANDS or base_cmd in self.READ_ONLY_COMMANDS:
            # Check for modifying redirections
            if node.redirects or any(redirect in raw for redirect in [">", ">>", "| sudo tee", "| tee"]):
                return SafetyLevel.MODIFYING, 0.35, "Inspection command with output redirection to file."
            # sed -i is modifying
            if base_cmd == "sed" and any("-i" in t for t in exec_tokens):
                return SafetyLevel.MODIFYING, 0.40, "In-place file editing via sed."
            # find -delete or -exec rm is high risk
            if base_cmd == "find" and any(t in ("-delete", "-exec") for t in exec_tokens):
                if "-delete" in exec_tokens or "rm" in exec_tokens:
                    return SafetyLevel.HIGH_RISK, 0.75, "Batch file deletion via find."
            return SafetyLevel.READ_ONLY, 0.05, "Non-mutating diagnostic inspection command."

        # 9. Check High Risk Commands
        if base_cmd in self.HIGH_RISK_COMMANDS:
            return SafetyLevel.HIGH_RISK, 0.70, f"Process management, kernel tuning, package installation, or networking alteration ({base_cmd})."

        # 10. Check Modifying Whitelist
        if sub_cmd in self.MODIFYING_COMMANDS or base_cmd in self.MODIFYING_COMMANDS:
            return SafetyLevel.MODIFYING, 0.35, "Standard service state transition or safe file modification."

        # 11. Default Unclassified
        return SafetyLevel.MODIFYING, 0.50, "Unclassified system command."

    # -------------------------------------------------------------------------
    # Full AST Parsing Pipeline
    # -------------------------------------------------------------------------

    def parse_ast(self, command_str: str) -> List[CommandASTNode]:
        """Parses compound command string into an AST list of CommandASTNode objects."""
        stripped = command_str.strip()
        if not stripped:
            return []

        # Step 1: Deobfuscate
        expanded_cmd, detected_techs = self.deobfuscate(stripped)

        # Step 2: Split compound commands (;, &&, ||, \n)
        segments = self.split_compound_commands(expanded_cmd)

        ast_nodes = []
        for seg in segments:
            stages = self.split_pipeline_stages(seg)
            for stage_idx, stage in enumerate(stages):
                stage_str = stage.strip()
                if not stage_str:
                    continue

                subshells = self.extract_subshells(stage_str)

                redirects = []
                red_matches = re.findall(r"(>>?|>&|>\|)\s*([^\s;&|]+)", stage_str)
                for op, tgt in red_matches:
                    redirects.append((op, tgt))

                try:
                    tokens = shlex.split(stage_str)
                except Exception:
                    tokens = stage_str.split()

                has_sudo = bool(tokens and tokens[0] == "sudo")
                exec_tokens = tokens[1:] if has_sudo and len(tokens) > 1 else tokens
                base_cmd = exec_tokens[0] if exec_tokens else ""
                sub_cmd = f"{base_cmd} {exec_tokens[1]}" if len(exec_tokens) > 1 else base_cmd

                node = CommandASTNode(
                    raw=stage_str,
                    tokens=tokens,
                    base_cmd=base_cmd,
                    sub_cmd=sub_cmd,
                    has_sudo=has_sudo,
                    redirects=redirects,
                    subshells=subshells,
                    obfuscation_detected=detected_techs
                )

                # Check if this stage pipes into a shell interpreter downstream
                if stage_idx + 1 < len(stages):
                    downstream = stages[stage_idx + 1].strip()
                    try:
                        down_tokens = shlex.split(downstream)
                    except Exception:
                        down_tokens = downstream.split()
                    if down_tokens and (down_tokens[0] in ("bash", "sh", "zsh", "dash") or (len(down_tokens) > 1 and down_tokens[0] == "sudo" and down_tokens[1] in ("bash", "sh", "zsh"))):
                        # If current stage is echo/printf, evaluate its string argument
                        if base_cmd in ("echo", "printf") and len(exec_tokens) > 1:
                            piped_payload = " ".join(exec_tokens[1:]).strip("'\"")
                            pipe_lvl, pipe_risk, pipe_reason = self.evaluate_safety(piped_payload)
                            if pipe_lvl == SafetyLevel.DESTRUCTIVE:
                                node.safety_level = SafetyLevel.DESTRUCTIVE
                                node.risk_score = 1.0
                                node.reason = f"Piped destructive payload to shell interpreter: {pipe_reason}"
                                ast_nodes.append(node)
                                continue

                lvl, risk, reason = self.evaluate_node(node)
                node.safety_level = lvl
                node.risk_score = risk
                node.reason = reason

                ast_nodes.append(node)

        return ast_nodes

    # -------------------------------------------------------------------------
    # Main Public Safety Evaluation Entry Point
    # -------------------------------------------------------------------------

    def evaluate_safety(self, command_str: str) -> Tuple[SafetyLevel, float, str]:
        """Evaluates a command string and returns (SafetyLevel, risk_score, reason).

        Decomposes compound pipelines, extracts obfuscated payloads (Base64, Hex,
        Octal, ANSI-C), inspects subshells and AST nodes, and aggregates overall safety.
        """
        stripped = command_str.strip()
        if not stripped:
            return SafetyLevel.READ_ONLY, 0.0, "Empty command."

        # Stage 1: Quick Catastrophic Pattern Match on Raw Command
        for pattern in self.CATASTROPHIC_PATTERNS:
            if re.search(pattern, stripped, flags=re.IGNORECASE):
                return (
                    SafetyLevel.DESTRUCTIVE,
                    1.0,
                    "Catastrophic destructive pattern detected: targets root, system block device, critical auth file, or triggers fork bomb."
                )

        # Stage 2: Parse AST & Deobfuscate
        nodes = self.parse_ast(stripped)
        if not nodes:
            return SafetyLevel.MODIFYING, 0.50, "Unclassified command."

        # Stage 3: Aggregate Across All Nodes and Nested Subshells
        highest_level = SafetyLevel.READ_ONLY
        max_risk = 0.0
        primary_reason = "Non-mutating diagnostic inspection command."
        level_order = {
            SafetyLevel.READ_ONLY: 1,
            SafetyLevel.MODIFYING: 2,
            SafetyLevel.HIGH_RISK: 3,
            SafetyLevel.DESTRUCTIVE: 4
        }

        for node in nodes:
            for sub in node.subshells:
                sub_lvl, sub_risk, sub_reason = self.evaluate_safety(sub)
                if level_order[sub_lvl] > level_order[highest_level]:
                    highest_level = sub_lvl
                    max_risk = max(max_risk, sub_risk)
                    primary_reason = f"Destructive/risky subshell execution '$({sub})': {sub_reason}"

            if level_order[node.safety_level] > level_order[highest_level]:
                highest_level = node.safety_level
                max_risk = max(max_risk, node.risk_score)
                primary_reason = node.reason
            elif node.risk_score > max_risk:
                max_risk = node.risk_score

            if node.obfuscation_detected and highest_level == SafetyLevel.DESTRUCTIVE:
                primary_reason = f"Obfuscated destructive payload detected ({'; '.join(node.obfuscation_detected[:2])}): {primary_reason}"

        if re.search(r"base64\s+(?:-d|--decode)\s*\|\s*(sudo\s+)?(sh|bash|zsh)", stripped, re.IGNORECASE):
            if highest_level not in (SafetyLevel.DESTRUCTIVE, SafetyLevel.HIGH_RISK):
                highest_level = SafetyLevel.HIGH_RISK
                max_risk = max(max_risk, 0.85)
                primary_reason = "Base64 decode directly piped to execution shell."

        return highest_level, max_risk, primary_reason

    def is_destructive(self, command_str: str) -> bool:
        """Returns True if the command is classified as DESTRUCTIVE."""
        lvl, _, _ = self.evaluate_safety(command_str)
        return lvl == SafetyLevel.DESTRUCTIVE

    @classmethod
    def validate(cls, command_str: str) -> SafetyValidationResult:
        """Classmethod validating a command and returning a structured SafetyValidationResult."""
        instance = cls()
        lvl, score, reason = instance.evaluate_safety(command_str)
        from ops_assistant.explainer.xai import XAIExplainer
        rollback, _ = XAIExplainer().generate_rollback_command(command_str)
        return SafetyValidationResult(
            command=command_str,
            level=lvl,
            risk_score=score,
            matched_rule=reason,
            is_destructive=(lvl == SafetyLevel.DESTRUCTIVE),
            suggested_rollback=rollback
        )

