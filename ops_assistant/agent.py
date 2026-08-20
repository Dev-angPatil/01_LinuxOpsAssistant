"""Agentic Diagnostic Loop for Linux Operations Assistant with Causal DAG and Sandbox Verification."""

import os
import re
import json
import time
import urllib.request
from dataclasses import asdict
from typing import Dict, Any, List, Optional, Tuple, Union
from ops_assistant.models import (
    DiagnosticReport, XAIExplanation, SystemHealthSnapshot, SafetyLevel, LogRecord
)
from ops_assistant.collectors.hub import TelemetryHub
from ops_assistant.collectors.distro_detector import DistroDetector, DistroInfo
from ops_assistant.db.distro_db import DistroKnowledgeBase
from ops_assistant.explainer.xai import XAIExplainer
from ops_assistant.explainer.causality_dag import CausalityDAGEngine, CausalityGraphResult
from ops_assistant.tools.safety import CommandSafetyValidator
from ops_assistant.tools.sandbox_probe import EphemeralSandboxProbe

class LLMProvider:
    """Base class for pluggable LLM inference backends."""
    def generate_diagnosis(self, query: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

class OllamaProvider(LLMProvider):
    def __init__(self, endpoint: str = "http://localhost:11434/api/generate", model: str = "llama3:8b"):
        self.endpoint = endpoint
        self.model = model

    def generate_diagnosis(self, query: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        prompt = (
            f"You are an expert Linux System Administrator AI. Diagnose the following query given system telemetry and logs.\n"
            f"Query: {query}\n"
            f"Context: {json.dumps(context)}\n"
            f"Respond ONLY in valid JSON with keys: symptom, root_cause, rationale, proposed_commands (list of tuples: [command, safety_level, risk_score, rationale]), confidence."
        )
        try:
            req_data = json.dumps({"model": self.model, "prompt": prompt, "stream": False, "format": "json"}).encode("utf-8")
            req = urllib.request.Request(self.endpoint, data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return json.loads(data.get("response", "{}"))
        except Exception:
            return None

class LlamaCppProvider(LLMProvider):
    """Direct in-process LLM inference using llama-cpp-python and local GGUF models."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        n_ctx: int = 2048,
        n_threads: Optional[int] = None,
        verbose: bool = False
    ):
        self.model_path = model_path
        if self.model_path is None:
            try:
                from ops_assistant.config import get_config
                cfg = get_config()
                if cfg.get("active_model_path") and os.path.exists(cfg["active_model_path"]):
                    self.model_path = cfg["active_model_path"]
            except Exception:
                pass
            if self.model_path is None:
                try:
                    from ops_assistant.model_manager.downloader import ModelDownloader
                    downloader = ModelDownloader()
                    active_path = downloader.get_active_model_path()
                    if active_path:
                        self.model_path = str(active_path)
                except Exception:
                    pass

        self.n_ctx = n_ctx
        self.n_threads = n_threads or max(1, (os.cpu_count() or 4) // 2)
        self.verbose = verbose
        self._llm = None
        self._load_error = None

    def is_available(self) -> Tuple[bool, str]:
        """Check if llama-cpp-python and model weights are ready."""
        if not self.model_path or not os.path.exists(self.model_path):
            return False, f"Model weights not found at '{self.model_path}'"
        try:
            import llama_cpp
            return True, f"Ready ({os.path.basename(self.model_path)})"
        except ImportError:
            return False, "llama-cpp-python is not installed (run 'pip install llama-cpp-python')"

    def _ensure_loaded(self):
        if self._llm is not None:
            return
        if self._load_error:
            raise RuntimeError(self._load_error)

        if not self.model_path or not os.path.exists(self.model_path):
            self._load_error = f"Model file not found: {self.model_path}"
            raise FileNotFoundError(self._load_error)

        try:
            from llama_cpp import Llama
            self._llm = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                verbose=self.verbose
            )
        except ImportError:
            self._load_error = "llama-cpp-python is not installed. Install with 'pip install llama-cpp-python'."
            raise ImportError(self._load_error)
        except Exception as e:
            self._load_error = f"Failed to initialize Llama context: {e}"
            raise RuntimeError(self._load_error)

    def generate_diagnosis(self, query: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            self._ensure_loaded()
        except Exception:
            return None

        prompt = (
            f"<|im_start|>system\n"
            f"You are an expert Linux System Administrator AI. Diagnose the sysadmin query given system telemetry and logs.\n"
            f"Respond ONLY in valid JSON format with keys:\n"
            f"- 'symptom': string\n"
            f"- 'root_cause': string\n"
            f"- 'rationale': string\n"
            f"- 'proposed_commands': list of lists: [[command, safety_level, risk_score, rationale], ...]\n"
            f"  where safety_level is one of: READ_ONLY, MODIFYING, HIGH_RISK, DESTRUCTIVE\n"
            f"- 'confidence': float between 0.0 and 1.0\n"
            f"<|im_end|>\n"
            f"<|im_start|>user\n"
            f"Query: {query}\n"
            f"Context: {json.dumps(context)}\n"
            f"<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
        try:
            response = self._llm(
                prompt,
                max_tokens=512,
                temperature=0.2,
                stop=["<|im_end|>", "```"]
            )
            text = response["choices"][0]["text"].strip()
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            return json.loads(text)
        except Exception:
            return None

class OpsAssistantAgent:
    COMMON_SERVICES = [
        "nginx", "apache2", "docker", "postgres", "postgresql", "mysql",
        "redis", "systemd-resolved", "ssh", "sshd", "kubelet", "cron", "named",
        "chrony", "timesyncd", "ufw", "iptables"
    ]

    FAILURE_TAXONOMY = [
        {
            "id": "PORT_CONFLICT",
            "pattern": r"(Address already in use|bind\(\) to .* failed|port \d+ already in use|EADDRINUSE)",
            "symptom": "Service failed to bind to target TCP/UDP socket.",
            "root_cause": "The configured listening port is already bound by another active process.",
            "commands": [
                ("sudo ss -tulpn | grep -E ':(80|443|8080|5432|3306|6379|22)'", SafetyLevel.READ_ONLY, 0.05, "Inspect which PID currently holds the listening port descriptor."),
                ("sudo systemctl status {service}", SafetyLevel.READ_ONLY, 0.05, "Inspect systemd unit exit status and error journal slice.")
            ],
            "rationale": "Socket collisions prevent daemons from starting. You must either terminate the colliding process or reconfigure the service port."
        },
        {
            "id": "PERMISSION_DENIED",
            "pattern": r"(Permission denied|EACCES|Failed to open .*: Permission denied|could not open directory|access denied for user)",
            "symptom": "File, socket or path access blocked by filesystem permissions.",
            "root_cause": "The service process user does not possess POSIX read/write permissions for the designated path.",
            "commands": [
                ("ls -la /var/log/{service} /etc/{service}", SafetyLevel.READ_ONLY, 0.05, "Check user, group, and mode bits on service paths."),
                ("sudo chown -R {service}:{service} /var/log/{service}", SafetyLevel.MODIFYING, 0.40, "Restore expected service ownership to log directory.")
            ],
            "rationale": "Daemon processes dropped privileges to service accounts (e.g. www-data, postgres) and cannot access root-owned paths."
        },
        {
            "id": "OOM_KILL",
            "pattern": r"(Out of memory|Killed process \d+|oom-killer|invoked oom-killer|fatal error: runtime: out of memory|Memory cgroup out of memory)",
            "symptom": "Process terminated by Linux kernel Out-of-Memory (OOM) killer.",
            "root_cause": "Linux kernel Out-of-Memory (OOM) killer terminated the process due to exhausted system RAM + Swap or exceeded cgroup memory limit.",
            "commands": [
                ("free -h", SafetyLevel.READ_ONLY, 0.05, "Check current physical RAM and swap partition availability."),
                ("ps aux --sort=-%mem | head -n 10", SafetyLevel.READ_ONLY, 0.05, "Identify the top 10 memory-consuming processes."),
                ("dmesg -T --level=err,crit | tail -n 20", SafetyLevel.READ_ONLY, 0.05, "Inspect exact kernel OOM invocation logs and killed process PIDs.")
            ],
            "rationale": "Kernel killed the process to prevent an unrecoverable kernel panic when page allocation failed."
        },
        {
            "id": "DISK_EXHAUSTION",
            "pattern": r"(No space left on device|ENOSPC|disk full|write error: No space)",
            "symptom": "Disk write failure due to 0 remaining blocks or exhausted partition capacity.",
            "root_cause": "Target partition has exhausted available physical disk blocks.",
            "commands": [
                ("df -h", SafetyLevel.READ_ONLY, 0.05, "Verify disk partition block utilization across all mounts."),
                ("sudo du -sh /var/log/* /var/tmp/* /tmp/* 2>/dev/null | sort -rh | head -n 10", SafetyLevel.READ_ONLY, 0.05, "Pinpoint the largest log or temp files consuming disk space."),
                ("sudo journalctl --vacuum-size=200M", SafetyLevel.MODIFYING, 0.30, "Vacuum older systemd journal logs to reclaim disk space.")
            ],
            "rationale": "Logging, cache, or database write failed because the filesystem cannot allocate additional extents."
        },
        {
            "id": "INODE_EXHAUSTION",
            "pattern": r"(No space left on device: inode|cannot create directory: No space|out of inodes|structure needs cleaning)",
            "symptom": "Filesystem metadata exhaustion (0 available inodes despite free block space).",
            "root_cause": "Target filesystem inode allocation table has zero remaining entries due to millions of micro-files or session caches.",
            "commands": [
                ("df -i", SafetyLevel.READ_ONLY, 0.05, "Verify inode allocation table availability across all mounted partitions."),
                ("sudo find /var/spool /tmp /var/tmp -xdev -printf '%h\n' | sort | uniq -c | sort -k 1 -n | tail -n 10", SafetyLevel.READ_ONLY, 0.05, "Pinpoint directory trees hoarding excessive file counts.")
            ],
            "rationale": "Every file requires an inode entry; massive collections of tiny session files deplete inodes while disk blocks appear free."
        },
        {
            "id": "CONFIG_SYNTAX_ERROR",
            "pattern": r"(syntax error|directive .* is not allowed here|unknown directive|Configuration file .* test failed|failed to parse|invalid configuration)",
            "symptom": "Service configuration file parsing error.",
            "root_cause": "Syntax error, missing closing bracket, or unsupported directive in service configuration file.",
            "commands": [
                ("sudo nginx -t", SafetyLevel.READ_ONLY, 0.05, "Test NGINX configuration syntax and line numbers."),
                ("sudo journalctl -u {service} -n 30 --no-pager", SafetyLevel.READ_ONLY, 0.05, "View recent daemon config parser error messages.")
            ],
            "rationale": "Daemon aborts initialization before binding sockets when syntax validation fails."
        },
        {
            "id": "SSL_CERT_ERROR",
            "pattern": r"(certificate has expired|SSL_ERROR_SSL|certificate verify failed|certificate signed by unknown authority|certificate expired|SSL handshake failed|SSL routines:.*:certificate)",
            "symptom": "TLS handshake failure due to expired, mismatched, or untrusted SSL/TLS certificate.",
            "root_cause": "The active SSL/TLS X.509 certificate passed its Not-After expiration date or lacks valid intermediate CA chains.",
            "commands": [
                ("openssl x509 -enddate -noout -in /etc/ssl/certs/ssl-cert-snakeoil.pem", SafetyLevel.READ_ONLY, 0.05, "Check exact expiry timestamp of local SSL certificate."),
                ("sudo certbot certificates", SafetyLevel.READ_ONLY, 0.05, "Audit status of all Let's Encrypt managed SSL certificates."),
                ("sudo certbot renew --dry-run", SafetyLevel.READ_ONLY, 0.05, "Test automatic TLS certificate renewal pipeline.")
            ],
            "rationale": "Modern clients terminate TLS connections immediately upon encountering expired or invalid certificate chains."
        },
        {
            "id": "DNS_RESOLUTION_FAILURE",
            "pattern": r"(Temporary failure in name resolution|Could not resolve host|EAI_NONAME|Name or service not known|nameserver failure|systemd-resolved.*failed)",
            "symptom": "Domain name resolution failure (DNS lookup timeout or SERVFAIL).",
            "root_cause": "Upstream DNS resolvers are unreachable, `/etc/resolv.conf` is misconfigured, or `systemd-resolved` cache is stalled.",
            "commands": [
                ("resolvectl status", SafetyLevel.READ_ONLY, 0.05, "Inspect active DNS link upstream servers and query statistics."),
                ("cat /etc/resolv.conf", SafetyLevel.READ_ONLY, 0.05, "Inspect active nameserver directives in resolver configuration."),
                ("sudo systemd-resolve --flush-caches", SafetyLevel.MODIFYING, 0.20, "Flush stale DNS query cache.")
            ],
            "rationale": "System cannot translate domain names into IP addresses, causing network timeouts for external APIs and services."
        },
        {
            "id": "DPKG_LOCK_BLOCKED",
            "pattern": r"(Could not get lock /var/lib/dpkg/lock|Resource temporarily unavailable|dpkg: error: dpkg frontend lock is held|Unable to acquire the dpkg frontend lock|Could not open lock file /var/lib/apt/lists/lock)",
            "symptom": "Package manager execution blocked by another running apt/dpkg instance.",
            "root_cause": "An automated background unattended-upgrades job or another package manager session holds the exclusive dpkg frontend lock.",
            "commands": [
                ("sudo lsof /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock", SafetyLevel.READ_ONLY, 0.05, "Identify the active PID holding the dpkg lock descriptor."),
                ("sudo ps aux | grep -E 'apt|dpkg|unattended-upgrade'", SafetyLevel.READ_ONLY, 0.05, "Inspect running package manager processes."),
                ("sudo dpkg --configure -a", SafetyLevel.HIGH_RISK, 0.70, "Cleanly resume and repair pending package installation states.")
            ],
            "rationale": "Debian/Ubuntu package management uses advisory locks to guarantee atomic database updates."
        },
        {
            "id": "SYSTEMD_CRASH_LOOP",
            "pattern": r"(Start request repeated too quickly|Unit .* entered failed state|Failed with result 'exit-code'|Main process exited, code=dumped|Holdoff time finished, scheduling restart)",
            "symptom": "Systemd unit entered crash loop and exceeded restart burst limit (`StartLimitBurst`).",
            "root_cause": "Service crashed immediately upon boot repeatedly, triggering systemd rate-limiting backoff to protect CPU.",
            "commands": [
                ("sudo systemctl status {service} -l --no-pager", SafetyLevel.READ_ONLY, 0.05, "Inspect full failure callstack and unit properties."),
                ("sudo journalctl -u {service} -xeu {service} -n 40 --no-pager", SafetyLevel.READ_ONLY, 0.05, "Inspect crash error messages with systemd catalog explanations."),
                ("sudo systemctl reset-failed {service}", SafetyLevel.MODIFYING, 0.30, "Reset the rate-limit failure counter on the unit.")
            ],
            "rationale": "Systemd suspends automatic restarts when `StartLimitBurst` is breached to prevent spinning CPU cores."
        },
        {
            "id": "DB_CONN_EXHAUSTION",
            "pattern": r"(too many connections|remaining connection slots are reserved|Connection pool exhausted|max_connections exceeded|Can't connect to MySQL server|server closed the connection unexpectedly)",
            "symptom": "Database connection pool saturated (clients receiving connection refused).",
            "root_cause": "Active concurrent client connections reached database `max_connections` limit or file descriptor `ulimit`.",
            "commands": [
                ("sudo ss -tan state established '( dport = :5432 or dport = :3306 or dport = :6379 )' | wc -l", SafetyLevel.READ_ONLY, 0.05, "Count total active established database client connections."),
                ("sudo systemctl status postgresql mysql redis", SafetyLevel.READ_ONLY, 0.05, "Inspect database daemon health status.")
            ],
            "rationale": "Database engines reject new connection requests once backend worker limits or OS socket descriptors are exhausted."
        },
        {
            "id": "FIREWALL_PORT_BLOCKED",
            "pattern": r"(Connection refused|Connection timed out.*port|Host unreachable|No route to host|iptables: DROP|UFW BLOCK|filtered port)",
            "symptom": "Network ingress or egress traffic dropped by kernel packet filter.",
            "root_cause": "Firewall rules (UFW / iptables / nftables) are dropping packets targeting the specified port or IP range.",
            "commands": [
                ("sudo ufw status verbose", SafetyLevel.READ_ONLY, 0.05, "Check active UFW firewall rule configuration and status."),
                ("sudo iptables -L -n -v --line-numbers", SafetyLevel.READ_ONLY, 0.05, "Inspect low-level netfilter chains and dropped packet counters."),
                ("sudo ufw allow 80/tcp", SafetyLevel.HIGH_RISK, 0.70, "Allow HTTP traffic through UFW firewall.")
            ],
            "rationale": "Default-drop firewall policies isolate unconfigured ports to prevent unauthorized remote network access."
        },
        {
            "id": "ZOMBIE_PROCESS_ACCUMULATION",
            "pattern": r"(defunct|zombie process|defunct process accumulating|maximum number of processes reached|fork: Resource temporarily unavailable)",
            "symptom": "Process table saturated by defunct zombie child processes.",
            "root_cause": "Parent processes terminated or failed to invoke `wait()`/`waitpid()` on exited children, causing zombie PID accumulation.",
            "commands": [
                ("ps aux | awk '{if ($8 ~ /Z/) print $0}'", SafetyLevel.READ_ONLY, 0.05, "List all current defunct zombie processes with their PIDs."),
                ("ps -ef | grep defunct | head -n 10", SafetyLevel.READ_ONLY, 0.05, "Identify parent PIDs responsible for uncollected zombie children.")
            ],
            "rationale": "Zombies occupy PID slots in the kernel process table without consuming RAM until their parent is terminated."
        },
        {
            "id": "IOWAIT_BOTTLENECK",
            "pattern": r"(high\s+iowait|iowait.*high|task .* blocked for more than \d+ seconds|blk_update_request: I/O error|Buffer I/O error on dev|high disk latency|iowait\s+spike)",
            "symptom": "High kernel CPU I/O wait state causing sluggish system response.",
            "root_cause": "Disk block layer is bottlenecked by saturated write throughput, degrading storage drive, or failing hardware controller.",
            "commands": [
                ("iostat -x 1 3", SafetyLevel.READ_ONLY, 0.05, "Inspect device await, r/s, w/s, and disk %utilization."),
                ("dmesg -T --level=err,crit | grep -i -E 'i/o|ata|nvme|scsi|error'", SafetyLevel.READ_ONLY, 0.05, "Inspect kernel ring buffer for disk hardware errors.")
            ],
            "rationale": "Processes enter uninterruptible sleep ('D' state) while waiting for slow or unresponsive storage controllers."
        },
        {
            "id": "SELINUX_APPARMOR_DENIAL",
            "pattern": r"(type=AVC msg=audit|apparmor=\"DENIED\"|avc:\s+denied|permission=requested_mask|audit: type=1400)",
            "symptom": "Mandatory Access Control (MAC) security policy denial.",
            "root_cause": "SELinux or AppArmor security profile prevented service executable from reading/writing confined resources.",
            "commands": [
                ("sudo aa-status", SafetyLevel.READ_ONLY, 0.05, "Check AppArmor profile status and confined applications."),
                ("sudo dmesg -T | grep -i -E 'apparmor|audit|avc' | tail -n 20", SafetyLevel.READ_ONLY, 0.05, "Inspect exact security policy violation audit records.")
            ],
            "rationale": "Linux Security Modules (LSM) enforce least-privilege security profiles overriding standard DAC permissions."
        },
        {
            "id": "NTP_CLOCK_DRIFT",
            "pattern": r"(Time has been changed|Server has gone too long without receiving time|system clock desynchronized|NTP sync failed|clock skew detected)",
            "symptom": "System clock drift desynchronizing authentication tokens and TLS certificates.",
            "root_cause": "Network Time Protocol (NTP) service is stopped, blocked by firewall, or upstream time servers are unreachable.",
            "commands": [
                ("timedatectl status", SafetyLevel.READ_ONLY, 0.05, "Check local RTC time, UTC time, and NTP synchronization state."),
                ("timedatectl timesync-status", SafetyLevel.READ_ONLY, 0.05, "Inspect upstream time server jitter, delay, and offset."),
                ("sudo timedatectl set-ntp true", SafetyLevel.MODIFYING, 0.35, "Enable automatic systemd network time synchronization.")
            ],
            "rationale": "Clock drift breaks Kerberos tokens, JWT signatures, SSL certificate validation, and distributed clustering."
        }
    ]

    def __init__(
        self,
        llm_provider: Optional[Union[LLMProvider, str]] = None,
        distro_db: Optional[DistroKnowledgeBase] = None,
        distro_detector: Optional[DistroDetector] = None,
        model_path: Optional[str] = None
    ):
        self.distro_db = distro_db or DistroKnowledgeBase()
        self.distro_detector = distro_detector or DistroDetector(self.distro_db)
        self.hub = TelemetryHub(distro_detector=self.distro_detector)
        self.explainer = XAIExplainer()
        self.causality_engine = CausalityDAGEngine()
        self.sandbox_probe = EphemeralSandboxProbe()
        self.safety_validator = CommandSafetyValidator()

        from ops_assistant.hardware.advisor import HardwareAdvisor
        self.hardware_advisor = HardwareAdvisor()

        if isinstance(llm_provider, str):
            prov_str = llm_provider.lower().strip()
            if prov_str in ["gguf", "llama_cpp", "local"]:
                self.llm_provider = LlamaCppProvider(model_path=model_path)
            elif prov_str in ["ollama", "remote"]:
                self.llm_provider = OllamaProvider()
            elif prov_str == "auto":
                gguf_p = LlamaCppProvider(model_path=model_path)
                avail, _ = gguf_p.is_available()
                self.llm_provider = gguf_p if avail else None
            else:
                self.llm_provider = None
        else:
            self.llm_provider = llm_provider

    def extract_subsystem(self, query: str) -> Optional[str]:
        query_lower = query.lower()
        for svc in self.COMMON_SERVICES:
            if svc in query_lower:
                return svc
        return None

    def _adapt_commands_for_distro(
        self,
        matched_id: Optional[str],
        default_cmds: List[Tuple[str, SafetyLevel, float, str]],
        distro_info: DistroInfo,
        svc_name: str
    ) -> List[Tuple[str, SafetyLevel, float, str]]:
        fid = distro_info.family_id

        # Package Lock adaptations
        if matched_id == "DPKG_LOCK_BLOCKED":
            if fid == "rhel":
                return [
                    ("sudo fuser /var/run/dnf.pid /var/lib/rpm/.rpm.lock 2>/dev/null", SafetyLevel.READ_ONLY, 0.05, "Inspect PID holding DNF/RPM package lock."),
                    ("sudo dnf check", SafetyLevel.READ_ONLY, 0.05, "Check package database consistency and duplicates."),
                    ("sudo rpm --rebuilddb", SafetyLevel.HIGH_RISK, 0.70, "Rebuild corrupted Berkeley DB RPM package database.")
                ]
            elif fid == "arch":
                return [
                    ("sudo fuser /var/lib/pacman/db.lck 2>/dev/null", SafetyLevel.READ_ONLY, 0.05, "Identify process locking pacman database."),
                    ("sudo pacman -Sy --noconfirm archlinux-keyring && sudo pacman -Syu", SafetyLevel.HIGH_RISK, 0.70, "Refresh Arch keyring and sync pacman repositories.")
                ]
            elif fid == "alpine":
                return [
                    ("sudo pidof apk", SafetyLevel.READ_ONLY, 0.05, "Inspect active APK package processes."),
                    ("sudo apk fix --purge", SafetyLevel.HIGH_RISK, 0.70, "Purge and repair broken packages and reinstall missing files.")
                ]
            elif fid == "suse":
                return [
                    ("sudo fuser /var/run/zypp.pid 2>/dev/null", SafetyLevel.READ_ONLY, 0.05, "Identify PID holding Zypper package lock."),
                    ("sudo systemctl stop packagekit", SafetyLevel.MODIFYING, 0.35, "Stop competing PackageKit background daemon."),
                    ("sudo zypper clean -a && sudo zypper ref -f", SafetyLevel.HIGH_RISK, 0.70, "Clean cache and force refresh Zypper repositories.")
                ]

        # Firewall adaptations
        elif matched_id == "FIREWALL_PORT_BLOCKED":
            if fid in ["rhel", "suse"]:
                return [
                    ("sudo firewall-cmd --state && sudo firewall-cmd --list-all", SafetyLevel.READ_ONLY, 0.05, "Check active Firewalld status and rules."),
                    ("sudo iptables -L -n -v --line-numbers", SafetyLevel.READ_ONLY, 0.05, "Inspect low-level netfilter chains and dropped packet counters."),
                    ("sudo firewall-cmd --permanent --add-port=80/tcp && sudo firewall-cmd --reload", SafetyLevel.HIGH_RISK, 0.70, "Allow HTTP traffic through firewalld.")
                ]
            elif fid == "arch":
                return [
                    ("sudo nft list ruleset", SafetyLevel.READ_ONLY, 0.05, "Inspect active nftables ruleset."),
                    ("sudo nft add rule inet filter input tcp dport 80 accept", SafetyLevel.HIGH_RISK, 0.70, "Allow HTTP traffic via nftables.")
                ]
            elif fid == "alpine":
                return [
                    ("sudo awall list", SafetyLevel.READ_ONLY, 0.05, "Inspect Alpine Wall firewall status."),
                    ("sudo awall activate -f", SafetyLevel.HIGH_RISK, 0.70, "Apply Alpine Wall configuration.")
                ]

        # Security Subsystem adaptations
        elif matched_id == "SELINUX_APPARMOR_DENIAL":
            if fid == "rhel":
                return [
                    ("sestatus", SafetyLevel.READ_ONLY, 0.05, "Check SELinux mode and policy status."),
                    ("sudo ausearch -m avc -ts recent | audit2why", SafetyLevel.READ_ONLY, 0.05, "Explain exact SELinux denial reasons with audit2why."),
                    (f"sudo restorecon -Rv /var/log/{svc_name}", SafetyLevel.MODIFYING, 0.40, "Restore standard SELinux security contexts.")
                ]
            elif fid == "alpine":
                return [
                    ("dmesg | grep -i pax", SafetyLevel.READ_ONLY, 0.05, "Check PaX / hardened kernel security logs.")
                ]

        # Alpine OpenRC Service Command Translations
        if fid == "alpine":
            adapted_cmds = []
            for cmd_str, level, risk, rationale in default_cmds:
                c = cmd_str
                c = re.sub(r"sudo systemctl status (\S+)", r"sudo rc-service \1 status", c)
                c = re.sub(r"systemctl status (\S+)", r"rc-service \1 status", c)
                c = re.sub(r"sudo systemctl restart (\S+)", r"sudo rc-service \1 restart", c)
                c = re.sub(r"systemctl restart (\S+)", r"rc-service \1 restart", c)
                c = re.sub(r"sudo systemctl stop (\S+)", r"sudo rc-service \1 stop", c)
                c = re.sub(r"systemctl stop (\S+)", r"rc-service \1 stop", c)
                c = re.sub(r"sudo systemctl start (\S+)", r"sudo rc-service \1 start", c)
                c = re.sub(r"systemctl start (\S+)", r"rc-service \1 start", c)
                c = re.sub(r"sudo journalctl -u (\S+).*", r"logread | grep \1", c)
                c = re.sub(r"journalctl -u (\S+).*", r"logread | grep \1", c)
                c = re.sub(r"journalctl.*", r"logread", c)
                adapted_cmds.append((c, level, risk, rationale))
            return adapted_cmds

        return default_cmds

    def diagnose(
        self,
        query: str,
        custom_logs: Optional[List[LogRecord]] = None,
        distro_override: Optional[str] = None
    ) -> DiagnosticReport:
        start_time = time.perf_counter()
        subsystem = self.extract_subsystem(query)

        # 1. Distro Detection & Telemetry Snapshot
        distro_info = self.distro_detector.detect(override_family=distro_override)
        health = self.hub.get_health_snapshot(distro_override=distro_override)

        # 2. Collect Logs across all sources
        if custom_logs is not None:
            logs = custom_logs
        else:
            logs = self.hub.journal.query_all_relevant_logs(
                unit=f"{subsystem}.service" if subsystem else None,
                subsystem=subsystem,
                lines=50
            )

        # Combine text for pattern search and causality DAG
        log_messages = [l.message for l in logs]
        combined_text = query + "\n" + "\n".join(log_messages)

        # 3. Build Dynamic Causality DAG from Ingested Logs
        dag_result = self.causality_engine.build_dag_from_events(log_messages)

        # 4. Match Failure Taxonomy (Neuro-Symbolic Rules & Distro Signatures)
        matched_item = None
        evidence: List[str] = []

        # Check core taxonomy first
        for item in self.FAILURE_TAXONOMY:
            matches = re.findall(item["pattern"], combined_text, flags=re.IGNORECASE)
            if matches:
                matched_item = item
                for l in logs:
                    if re.search(item["pattern"], l.message, flags=re.IGNORECASE):
                        evidence.append(f"[{l.source}] {l.message}")
                break

        # Check distro-specific error signatures from SQLite database
        if not matched_item:
            distro_sigs = self.distro_db.get_error_signatures(distro_info.family_id)
            for sig in distro_sigs:
                if re.search(sig["pattern"], combined_text, flags=re.IGNORECASE):
                    matched_item = {
                        "id": sig["id"],
                        "pattern": sig["pattern"],
                        "symptom": f"Distro-specific issue ({distro_info.distro_name}): {sig['id']}",
                        "root_cause": sig["explanation"],
                        "commands": [
                            (sig["remediation"].replace("{service}", subsystem or "service").replace("{path}", f"/var/log/{subsystem or 'service'}"), SafetyLevel.HIGH_RISK, 0.70, sig["explanation"])
                        ],
                        "rationale": sig["explanation"]
                    }
                    for l in logs:
                        if re.search(sig["pattern"], l.message, flags=re.IGNORECASE):
                            evidence.append(f"[{l.source}] {l.message}")
                    break

        svc_name = subsystem or ("service" if distro_info.family_id == "alpine" else "systemd")

        # 5. Optional LLM inference if configured
        if self.llm_provider and not matched_item:
            context = {
                "distro": distro_info.to_dict(),
                "subsystem": svc_name,
                "pressure_status": health.pressure_status,
                "recent_logs": [l.message for l in logs[:10]],
                "causality_root": dag_result.summary
            }
            llm_res = self.llm_provider.generate_diagnosis(query, context)
            if llm_res and "symptom" in llm_res:
                parsed_cmds = []
                for cmd in llm_res.get("proposed_commands", []):
                    if isinstance(cmd, (list, tuple)) and len(cmd) >= 4:
                        sec_str = str(cmd[1]).upper()
                        sec_lvl = SafetyLevel.READ_ONLY
                        for s in SafetyLevel:
                            if s.name == sec_str or s.value == sec_str:
                                sec_lvl = s
                                break
                        parsed_cmds.append((str(cmd[0]), sec_lvl, float(cmd[2]), str(cmd[3])))
                    elif isinstance(cmd, (list, tuple)) and len(cmd) >= 1:
                        parsed_cmds.append((str(cmd[0]), SafetyLevel.READ_ONLY, 0.05, "Proposed remediation command."))

                provider_label = type(self.llm_provider).__name__
                xai = self.explainer.synthesize_xai(
                    symptom=llm_res.get("symptom", "LLM-detected system anomaly"),
                    root_cause=llm_res.get("root_cause", "Anomaly identified via LLM inference"),
                    evidence_logs=evidence if evidence else [f"[{l.source}] {l.message}" for l in logs[:2]],
                    commands=parsed_cmds,
                    rationale=llm_res.get("rationale", "LLM reasoning explanation."),
                    confidence=float(llm_res.get("confidence", 0.90))
                )
                for cmd_prop in xai.proposed_commands:
                    probe_res = self.sandbox_probe.verify_command(cmd_prop.command)
                    cmd_prop.sandbox_verified = probe_res.is_verified

                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                return DiagnosticReport(
                    query=query,
                    target_subsystem=subsystem,
                    health_snapshot=health,
                    explanation=xai,
                    causality_dag=dag_result.to_dict(),
                    latency_ms=round(elapsed_ms, 2),
                    reasoning_engine=f"{provider_label}-Augmented-Causality-XAI ({distro_info.distro_name})"
                )

        if matched_item:
            symptom = matched_item["symptom"]
            root_cause = matched_item["root_cause"]
            rationale = matched_item["rationale"]
            # Format commands with service name
            raw_cmds = [
                (cmd[0].replace("{service}", svc_name), cmd[1], cmd[2], cmd[3])
                for cmd in matched_item["commands"]
            ]
            raw_cmds = self._adapt_commands_for_distro(
                matched_item.get("id"), raw_cmds, distro_info, svc_name
            )
        else:
            symptom = f"Unclassified anomaly detected on {svc_name}."
            root_cause = "General service startup or operational failure."
            rationale = "Inspect recent service logs and process state to identify failure root cause."
            if distro_info.family_id == "alpine":
                raw_cmds = [
                    (f"logread | grep {svc_name}", SafetyLevel.READ_ONLY, 0.05, "Retrieve recent service logs from syslogd buffer."),
                    (f"sudo rc-service {svc_name} status", SafetyLevel.READ_ONLY, 0.05, "Inspect OpenRC service status and PID.")
                ]
            else:
                raw_cmds = [
                    (f"sudo journalctl -u {svc_name} -n 50 --no-pager", SafetyLevel.READ_ONLY, 0.05, "Retrieve recent systemd service logs."),
                    (f"systemctl status {svc_name}", SafetyLevel.READ_ONLY, 0.05, "Inspect unit status and active process ID.")
                ]
            if not evidence and logs:
                evidence = [f"[{l.source}] {l.message}" for l in logs[:2]]

        # 6. Synthesize XAI Explanation
        xai = self.explainer.synthesize_xai(
            symptom=symptom,
            root_cause=root_cause,
            evidence_logs=evidence if evidence else ["No specific error logs matched; general triage initiated."],
            commands=raw_cmds,
            rationale=rationale,
            confidence=0.96 if matched_item else 0.80
        )

        # 7. Dry-Run Ephemeral Namespace Probe on Proposed Commands
        for cmd_prop in xai.proposed_commands:
            probe_res = self.sandbox_probe.verify_command(cmd_prop.command)
            cmd_prop.sandbox_verified = probe_res.is_verified

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return DiagnosticReport(
            query=query,
            target_subsystem=subsystem,
            health_snapshot=health,
            explanation=xai,
            causality_dag=dag_result.to_dict(),
            latency_ms=round(elapsed_ms, 2),
            reasoning_engine="NeuroSymbolic-Causality-XAI"
        )

    def execute_agent_action(self, query: str, context: Optional[Dict[str, Any]] = None, execute: bool = True) -> Dict[str, Any]:
        """
        Unified Natural Language Agent Execution Engine for CLI & GUI.
        Classifies user query and dispatches to tools or diagnostic engine.
        Provides explicit planned commands, short descriptions, and safety guardrails.
        """
        from ops_assistant.nlp.intent_router import IntentRouter, IntentType
        from ops_assistant.tools import (
            desktop_ops, download_ops, storage_ops, process_ops, network_ops,
            log_ops, system_ops, docker_ops, security_ops, backup_ops
        )

        router = getattr(self, "_router", None)
        if router is None:
            router = IntentRouter(llm_provider=self.llm_provider)
            self._router = router

        intent = router.classify(query)
        args = intent.args or {}
        result: Dict[str, Any] = {
            "query": query,
            "intent": intent.type.value,
            "confidence": intent.confidence,
            "steps": [],
            "summary": "",
            "command": "",
            "command_description": "",
            "planned_commands": [],
            "safety_level": SafetyLevel.READ_ONLY.value,
            "risk_score": 0.05,
            "output": None,
            "rollback_command": None,
            "diagnostic_report": None,
            "requires_permission": False,
            "executed": execute,
        }

        if intent.type == IntentType.DESKTOP_OPEN_FOLDER:
            path = args.get("path", "~")
            cmd = f"xdg-open '{path}'"
            desc = f"Opens directory '{path}' in the default desktop file manager."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append(f"Resolving path '{path}' for system file manager...")
            if execute:
                res = desktop_ops.open_folder(path)
                result["output"] = res
                result["summary"] = res.get("message") or res.get("error", "Opened folder")
            else:
                result["summary"] = f"Ready to open folder '{path}'."
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.DESKTOP_OPEN_FILE:
            path = args.get("path", "")
            cmd = f"xdg-open '{path}'"
            desc = f"Opens file '{path}' using its associated desktop application."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append(f"Resolving file '{path}' for default application...")
            if execute:
                res = desktop_ops.open_file(path)
                result["output"] = res
                result["summary"] = res.get("message") or res.get("error", "Opened file")
            else:
                result["summary"] = f"Ready to open file '{path}'."
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.DESKTOP_OPEN_IMAGE:
            path = args.get("path", "")
            cmd = f"xdg-open '{path}'"
            desc = f"Displays image '{path}' in the default system image viewer."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append(f"Opening image '{path}' with system viewer...")
            if execute:
                res = desktop_ops.open_image(path)
                result["output"] = res
                result["summary"] = res.get("message") or res.get("error", "Opened image")
            else:
                result["summary"] = f"Ready to open image '{path}'."
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.DESKTOP_OPEN_BROWSER:
            url = args.get("url", "https://google.com")
            cmd = f"xdg-open '{url}'"
            desc = f"Opens web address '{url}' in the default internet browser."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append(f"Opening web URL '{url}' in default browser...")
            if execute:
                res = desktop_ops.open_browser(url)
                result["output"] = res
                result["summary"] = res.get("message") or res.get("error", "Opened browser")
            else:
                result["summary"] = f"Ready to open browser at '{url}'."
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.DOWNLOAD_URL:
            url = args.get("url", "")
            dest = args.get("dest", "~/Downloads")
            cmd = f"curl -fsSL -O '{url}' --output-dir '{dest}'"
            desc = f"Downloads stream from '{url}' to destination '{dest}' with auto-extraction."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.20
            result["requires_permission"] = not execute
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.20}]
            result["steps"].append(f"Initiating stream download from '{url}' to '{dest}'...")
            if execute:
                res = download_ops.download_file(url, destination_dir=dest, auto_extract=True)
                result["output"] = res
                result["summary"] = res.get("message") or res.get("error", "Download completed")
                if res.get("file_path"):
                    result["rollback_command"] = f"rm -f '{res['file_path']}'"
            else:
                result["summary"] = f"Ready to download '{url}' to '{dest}'."

        elif intent.type == IntentType.FILE_MOVE:
            src = args.get("src", "")
            dst = args.get("dst", "")
            cmd = f"mv '{src}' '{dst}'"
            desc = f"Moves file or directory from '{src}' to '{dst}'."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.30
            result["rollback_command"] = f"mv '{dst}' '{src}'"
            result["requires_permission"] = not execute
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.30, "rollback_command": f"mv '{dst}' '{src}'"}]
            result["steps"].append(f"Moving path '{src}' to '{dst}'...")
            if execute:
                res = desktop_ops.move_path(src, dst)
                result["output"] = res
                result["summary"] = res.get("message") or res.get("error", "Moved successfully")
                result["rollback_command"] = res.get("rollback_command") or result["rollback_command"]
            else:
                result["summary"] = f"Ready to move '{src}' to '{dst}'."

        elif intent.type == IntentType.FILE_COPY:
            src = args.get("src", "")
            dst = args.get("dst", "")
            cmd = f"cp -r '{src}' '{dst}'"
            desc = f"Copies file or directory recursively from '{src}' to '{dst}'."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.25
            result["rollback_command"] = f"rm -rf '{dst}'"
            result["requires_permission"] = not execute
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.25, "rollback_command": f"rm -rf '{dst}'"}]
            result["steps"].append(f"Copying path '{src}' to '{dst}'...")
            if execute:
                res = desktop_ops.copy_path(src, dst)
                result["output"] = res
                result["summary"] = res.get("message") or res.get("error", "Copied successfully")
                result["rollback_command"] = res.get("rollback_command") or result["rollback_command"]
            else:
                result["summary"] = f"Ready to copy '{src}' to '{dst}'."

        elif intent.type == IntentType.FILE_TRASH:
            path = args.get("path", "")
            cmd = f"gio trash '{path}'"
            desc = f"Moves '{path}' safely to user trash directory."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.35
            result["requires_permission"] = not execute
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.35}]
            result["steps"].append(f"Moving '{path}' to user trash...")
            if execute:
                res = desktop_ops.trash_path(path)
                result["output"] = res
                result["summary"] = res.get("message") or res.get("error", "Trashed successfully")
                result["rollback_command"] = res.get("rollback_command")
            else:
                result["summary"] = f"Ready to trash '{path}'."

        elif intent.type == IntentType.STORAGE_ORGANISE:
            raw_path = args.get("path", "~/Downloads")
            cmd = f"ops-assistant organise '{raw_path}'"
            desc = f"Categorizes files in '{raw_path}' into Images, Documents, Videos, Audio, Archives, and Code."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.30
            result["requires_permission"] = not execute
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.30}]
            result["steps"].append(f"Organizing directory '{raw_path}'...")
            if execute:
                res = storage_ops.organise_directory(raw_path, dry_run=False)
                result["output"] = res
                result["summary"] = f"Organised {res.get('moved_count', 0)} files in {res.get('directory', raw_path)}"
                result["rollback_command"] = res.get("rollback_command")
            else:
                result["summary"] = f"Ready to organize directory '{raw_path}'."

        elif intent.type == IntentType.STORAGE_CLEAN:
            cmd = "journalctl --vacuum-size=200M && rm -rf /tmp/*"
            desc = "Purges rotated journal logs, package manager cache, and stale temporary files."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.40
            result["requires_permission"] = not execute
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.40}]
            result["steps"].append("Cleaning old log files and temporary space...")
            if execute:
                res = storage_ops.clean_logs_and_temp(dry_run=False)
                result["output"] = res
                result["summary"] = f"Cleaned {res.get('cleaned_count', 0)} items, freed {res.get('freed_human', '0 MB')}"
            else:
                result["summary"] = "Ready to clean system logs and temporary files."

        elif intent.type == IntentType.HEALTH:
            cmd = "cat /proc/pressure/{cpu,memory,io} && uptime"
            desc = "Queries kernel PSI pressure stall info, load averages, and memory headroom."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Capturing real-time Linux kernel telemetry and PSI metrics...")
            snap = self.hub.get_health_snapshot()
            result["output"] = snap.to_dict()
            result["summary"] = f"System Health: {snap.hostname} | Kernel: {snap.kernel_release} | Pressure: {snap.pressure_status}"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.PROCESS_LIST:
            cmd = "ps aux --sort=-%cpu | head -n 15"
            desc = "Lists top resource-consuming processes sorted by CPU and memory consumption."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Listing top CPU/Memory processes...")
            procs = process_ops.list_top_processes(n=10)
            result["output"] = procs
            result["summary"] = f"Found {len(procs)} active processes in process table."
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.PROCESS_KILL:
            pid = args.get("pid")
            name = args.get("name")
            target_str = f"PID {pid}" if pid else f"process '{name}'"
            cmd = f"kill -15 {pid}" if pid else f"pkill -15 {name}"
            desc = f"Sends SIGTERM (signal 15) to terminate {target_str}."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.HIGH_RISK.value
            result["risk_score"] = 0.70
            result["requires_permission"] = not execute
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.HIGH_RISK.value, "risk_score": 0.70}]
            result["steps"].append(f"Terminating process ({target_str})...")
            if execute:
                res = process_ops.kill_process(pid=pid, name=name)
                result["output"] = res
                result["summary"] = f"Terminated {target_str} (success={res.get('success', False)})"
            else:
                result["summary"] = f"Ready to terminate {target_str}."

        elif intent.type in (IntentType.FIREWALL_STATUS, IntentType.NETWORK_STATUS, IntentType.NETWORK_PORTS):
            cmd = "ss -tulpn && ufw status"
            desc = "Inspects listening sockets, bound ports, network interfaces, and firewall rules."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Inspecting network configuration and ports...")
            ports = network_ops.list_listening_ports()
            fw = network_ops.get_firewall_status()
            result["output"] = {"ports": ports, "firewall": fw}
            result["summary"] = f"Firewall: {fw.get('status', 'active')} | Listening ports: {len(ports)}"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        # Hardware & Model Selection Advisory
        elif intent.type == IntentType.HARDWARE_PROFILE:
            cmd = "lscpu && free -h && lspci | grep -i vga"
            desc = "Profiles system CPU cores, RAM bandwidth, GPU acceleration, and storage."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Profiling CPU, RAM headroom, GPU acceleration, and storage...")
            prof = self.hardware_advisor.profiler.profile()
            res = prof.to_dict()
            result["output"] = res
            result["summary"] = f"Hardware: {res['cpu']['model_name']} ({res['cpu']['logical_cores']} cores) | RAM: {res['memory']['total_gb']} GB | GPU: {res['gpu']['device_name']}"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.HARDWARE_RECOMMEND_MODEL:
            cmd = "ops-assistant recommend-model"
            desc = "Evaluates hardware compute tier to determine the optimal GGUF quantization model."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Calculating hardware performance score and matching optimal GGUF model...")
            from ops_assistant.hardware.advisor import ModelSelector
            prof = self.hardware_advisor.profiler.profile()
            rec = ModelSelector.recommend_model(prof)
            result["output"] = rec
            result["summary"] = f"Recommended Model: {rec['name']} ({rec.get('tier', 'Standard')}) — {rec['reason']}"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.HARDWARE_AUTO_TUNE:
            cmd = "ops-assistant auto-tune"
            desc = "Configures LLM thread allocation, context windows, and GPU offloading parameters."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Analyzing hardware profile and generating capability matrix...")
            adv = self.hardware_advisor.get_full_advisory()
            result["output"] = adv
            result["summary"] = f"Tuned for {adv['profile']['compute_tier']}: Selected {adv['recommended_model']['name']}"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        # Proactive System Health
        elif intent.type == IntentType.PROACTIVE_AUDIT:
            cmd = "ops-assistant audit"
            desc = "Runs autonomous multi-subsystem audit across kernel, storage, network, and security."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Running comprehensive autonomous multi-subsystem audit...")
            from ops_assistant.tools import proactive_engine
            res = proactive_engine.run_proactive_audit()
            result["output"] = res
            result["summary"] = f"System Health: {res['overall_health']} | Found {res['findings_count']} issues ({res['critical_count']} critical)"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        # Docker Operations
        elif intent.type == IntentType.DOCKER_LIST:
            cmd = "docker ps -a --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}'"
            desc = "Inspects active and stopped Docker containers and port bindings."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Inspecting Docker daemon and active containers...")
            from ops_assistant.tools import docker_ops
            res = docker_ops.list_containers(all_containers=True)
            result["output"] = res
            result["summary"] = f"Docker: {res.get('running_count', 0)} running, {res.get('failed_count', 0)} failed ({res.get('count', 0)} total)"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.DOCKER_LOGS:
            c = args.get("container", "")
            cmd = f"docker logs --tail 100 '{c}'"
            desc = f"Fetches recent standard output and error logs for container '{c}'."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append(f"Retrieving recent logs for container '{c}'...")
            from ops_assistant.tools import docker_ops
            res = docker_ops.get_container_logs(c)
            result["output"] = res
            result["summary"] = f"Retrieved {res.get('lines_count', 0)} log lines for container '{c}'"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.DOCKER_RESTART:
            c = args.get("container", "")
            cmd = f"docker restart '{c}'"
            desc = f"Restarts container '{c}', cycling its process and re-initializing networking."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.35
            result["rollback_command"] = f"docker restart '{c}'"
            result["requires_permission"] = not execute
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.35, "rollback_command": f"docker restart '{c}'"}]
            result["steps"].append(f"Restarting container '{c}'...")
            if execute:
                from ops_assistant.tools import docker_ops
                res = docker_ops.restart_container(c)
                result["output"] = res
                result["summary"] = res.get("message") or res.get("error", "Restarted container")
                result["rollback_command"] = res.get("rollback_command") or result["rollback_command"]
            else:
                result["summary"] = f"Ready to restart container '{c}'."

        elif intent.type == IntentType.DOCKER_PRUNE:
            cmd = "docker system prune -f"
            desc = "Removes all stopped containers, unused networks, and dangling images."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.30
            result["requires_permission"] = not execute
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.30}]
            result["steps"].append("Pruning unused Docker images, volumes, and builder cache...")
            if execute:
                from ops_assistant.tools import docker_ops
                res = docker_ops.prune_docker_resources(dry_run=False)
                result["output"] = res
                result["summary"] = res.get("message", "Docker pruned")
            else:
                result["summary"] = "Ready to prune unused Docker resources."

        # System Maintenance & Crontab
        elif intent.type == IntentType.CRON_LIST:
            cmd = "crontab -l && ls -la /etc/cron.*"
            desc = "Lists scheduled cron jobs for current user and system cron directories."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Inspecting user and system crontabs...")
            from ops_assistant.tools import system_ops
            res = system_ops.list_cron_jobs()
            result["output"] = res
            result["summary"] = f"Crontab: {res['user_jobs_count']} user jobs, {res['system_files_count']} system cron files"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.CRON_REMOVE:
            pat = args.get("pattern", "")
            cmd = f"crontab -l | grep -v '{pat}' | crontab -"
            desc = f"Removes scheduled cron entries matching pattern '{pat}'."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.35
            result["requires_permission"] = not execute
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.35}]
            result["steps"].append(f"Removing cron jobs matching '{pat}'...")
            if execute:
                from ops_assistant.tools import system_ops
                res = system_ops.remove_cron_job(pat)
                result["output"] = res
                result["summary"] = res.get("message") or res.get("error", "Removed cron job")
            else:
                result["summary"] = f"Ready to remove cron jobs matching '{pat}'."

        elif intent.type == IntentType.SYSTEM_BOOT_ANALYSIS:
            cmd = "systemd-analyze && systemd-analyze blame | head -n 10"
            desc = "Evaluates kernel and userspace startup duration and pinpoints slowest system services."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Analyzing system boot times and service blame breakdown...")
            from ops_assistant.tools import system_ops
            res = system_ops.analyze_boot_time()
            result["output"] = res
            slowest = res['top_slow_services'][0]['service'] if res.get('top_slow_services') else 'None'
            result["summary"] = f"Boot Time: {res.get('overall_boot_time', 'N/A')} | Slowest service: {slowest}"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.SYSTEM_TRIM_SSD:
            cmd = "fstrim -av"
            desc = "Trims mounted SSD blocks to inform storage hardware of unallocated blocks."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.20
            result["requires_permission"] = not execute
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.20}]
            result["steps"].append("Executing SSD TRIM on mounted filesystems...")
            if execute:
                from ops_assistant.tools import system_ops
                res = system_ops.trim_ssds(dry_run=False)
                result["output"] = res
                result["summary"] = res.get("message") or res.get("error", "Trimmed SSDs")
            else:
                result["summary"] = "Ready to execute SSD TRIM across mounted filesystems."

        elif intent.type == IntentType.SYSTEM_PACKAGE_CLEAN:
            cmd = "apt-get clean || dnf clean all || pacman -Sc --noconfirm || apk cache clean"
            desc = "Deletes cached package archive files from local repository directories."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.25
            result["requires_permission"] = not execute
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.25}]
            result["steps"].append("Purging downloaded package cache archives...")
            if execute:
                from ops_assistant.tools import system_ops
                res = system_ops.clean_package_cache(dry_run=False)
                result["output"] = res
                result["summary"] = res.get("message") or res.get("error", "Cleaned package cache")
            else:
                result["summary"] = "Ready to purge downloaded package cache archives."

        elif intent.type == IntentType.SYSTEM_JOURNAL_VACUUM:
            cmd = "journalctl --vacuum-size=200M"
            desc = "Reduces systemd journal size on disk by removing archived log entries exceeding 200MB."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.30
            result["requires_permission"] = not execute
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.30}]
            result["steps"].append("Vacuuming systemd journal logs to reclaim space...")
            if execute:
                from ops_assistant.tools import system_ops
                res = system_ops.vacuum_journal(max_size="200M", dry_run=False)
                result["output"] = res
                result["summary"] = res.get("message") or res.get("error", "Journal vacuumed")
            else:
                result["summary"] = "Ready to vacuum systemd journal logs."

        # Security Auditing
        elif intent.type == IntentType.SECURITY_AUDIT:
            cmd = "ss -tulpn && grep -i 'Failed password' /var/log/auth.log | tail -n 20"
            desc = "Audits open listening ports, firewall posture, SSH login failures, and SUID binaries."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Running comprehensive security audit (ports, SSH, brute force, SUID)...")
            from ops_assistant.tools import security_ops
            res = security_ops.audit_security()
            result["output"] = res
            result["summary"] = f"Security Status: {res.get('overall_status')} | Firewall: {res.get('firewall', {}).get('status')} | Open Ports: {res.get('listening_ports_count')}"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.SECURITY_SSH_CHECK:
            cmd = "sshd -T || cat /etc/ssh/sshd_config"
            desc = "Analyzes SSH daemon configuration for root login, password auth, and port security."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Auditing SSH daemon configuration hardening...")
            from ops_assistant.tools import security_ops
            res = security_ops.inspect_ssh_security()
            result["output"] = res
            result["summary"] = f"SSH Security Score: {res.get('security_score')}% | Checks: {len(res.get('findings', []))}"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.SECURITY_BRUTEFORCE:
            cmd = "grep -E '(Failed password|authentication failure)' /var/log/auth.log | tail -n 50"
            desc = "Scans auth logs for repeated failed password attempts and potential brute force attacks."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Scanning auth logs and journal for failed SSH authentication attempts...")
            from ops_assistant.tools import security_ops
            res = security_ops.detect_ssh_bruteforce(hours=24)
            result["output"] = res
            result["summary"] = f"Auth Threat: {res.get('threat_level')} | {res.get('total_failed_attempts')} failed attempts"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.SECURITY_SUID:
            cmd = "find / -perm -4000 -type f 2>/dev/null"
            desc = "Discovers binaries with SUID permission bit set that run with superuser privileges."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Auditing system binaries for SUID/SGID executable permissions...")
            from ops_assistant.tools import security_ops
            res = security_ops.audit_suid_binaries()
            result["output"] = res
            result["summary"] = f"SUID Binaries: {res.get('total_suid_count')} total ({res.get('anomalous_suid_count')} anomalies)"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        # Backup & Restore
        elif intent.type == IntentType.BACKUP_CREATE:
            path = args.get("path", "/etc")
            dest = args.get("dest", "~/.ops_assistant/backups")
            cmd = f"tar -czf '{dest}/backup.tar.gz' '{path}'"
            desc = f"Creates a gzip-compressed backup archive of '{path}'."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.20
            result["requires_permission"] = not execute
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.20}]
            result["steps"].append(f"Creating compressed snapshot of '{path}'...")
            if execute:
                from ops_assistant.tools import backup_ops
                res = backup_ops.create_backup(path, backup_dir=dest)
                result["output"] = res
                result["summary"] = res.get("message") or res.get("error", "Created backup")
                result["rollback_command"] = res.get("rollback_command")
            else:
                result["summary"] = f"Ready to create backup snapshot of '{path}'."

        elif intent.type == IntentType.BACKUP_LIST:
            cmd = "ls -lh ~/.ops_assistant/backups"
            desc = "Lists stored configuration backup archives with sizes and creation timestamps."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Listing stored configuration backup archives...")
            from ops_assistant.tools import backup_ops
            res = backup_ops.list_backups()
            result["output"] = res
            result["summary"] = f"Found {res.get('count', 0)} backups in {res.get('directory')}"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.BACKUP_RESTORE:
            path = args.get("path", "")
            dest = args.get("dest", "")
            cmd = f"tar -xzf '{path}' -C '{dest}'"
            desc = f"Extracts and restores backup archive '{path}' to target destination '{dest}'."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.HIGH_RISK.value
            result["risk_score"] = 0.70
            result["requires_permission"] = not execute
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.HIGH_RISK.value, "risk_score": 0.70}]
            result["steps"].append(f"Restoring backup archive '{path}' to '{dest}'...")
            if execute:
                from ops_assistant.tools import backup_ops
                res = backup_ops.restore_backup(path, dest)
                result["output"] = res
                result["summary"] = res.get("message") or res.get("error", "Restored backup")
            else:
                result["summary"] = f"Ready to restore backup archive '{path}' to '{dest}'."

        # Storage Analysis & Search
        elif intent.type == IntentType.STORAGE_ANALYSE:
            raw_path = args.get("path", "/")
            cmd = f"df -h '{raw_path}' && du -sh '{raw_path}'/* 2>/dev/null | sort -hr | head -10"
            desc = f"Analyzes disk space and partition usage for '{raw_path}'."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append(f"Analyzing disk partitions and directory usage for '{raw_path}'...")
            res = storage_ops.analyse_disk(raw_path)
            result["output"] = res
            result["summary"] = f"Analyzed {raw_path}: {len(res.get('partitions', []))} partitions, {len(res.get('top_dirs', []))} top directories."
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.STORAGE_FIND_LARGE:
            raw_path = args.get("path", "/")
            cmd = f"find '{raw_path}' -xdev -type f -size +100M -exec ls -lh {{}} + 2>/dev/null | sort -k5 -hr | head -20"
            desc = f"Scans '{raw_path}' for large files exceeding 100MB."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append(f"Scanning '{raw_path}' for large files (>100MB)...")
            res = storage_ops.find_large_files(search_path=raw_path, threshold_mb=100, top_n=20)
            result["output"] = res
            result["summary"] = f"Found {len(res.get('files', []))} large files in {raw_path} (~{res.get('total_size_human', '0 B')} total)."
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        # Service Management
        elif intent.type == IntentType.SERVICE_STATUS:
            svc = args.get("service", "")
            cmd = f"systemctl status '{svc}' --no-pager -l"
            desc = f"Inspects status and unit properties for service '{svc}'."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append(f"Checking status for service '{svc}'...")
            res = process_ops.show_service_status(svc)
            result["output"] = res
            result["summary"] = f"Service '{svc}': {res.get('active_state', 'unknown')}/{res.get('sub_state', 'unknown')}"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.SERVICE_START:
            svc = args.get("service", "")
            cmd = f"sudo systemctl start '{svc}'"
            desc = f"Starts systemd service '{svc}'."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.30
            result["requires_permission"] = not execute
            result["rollback_command"] = f"sudo systemctl stop '{svc}'"
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.30, "rollback_command": result["rollback_command"]}]
            result["steps"].append(f"Starting service '{svc}'...")
            if execute:
                res = process_ops.start_service(svc)
                result["output"] = res
                result["summary"] = f"Started service '{svc}' (success={res.get('success', False)})"
            else:
                result["summary"] = f"Ready to start service '{svc}'."

        elif intent.type == IntentType.SERVICE_STOP:
            svc = args.get("service", "")
            cmd = f"sudo systemctl stop '{svc}'"
            desc = f"Stops systemd service '{svc}'."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.35
            result["requires_permission"] = not execute
            result["rollback_command"] = f"sudo systemctl start '{svc}'"
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.35, "rollback_command": result["rollback_command"]}]
            result["steps"].append(f"Stopping service '{svc}'...")
            if execute:
                res = process_ops.stop_service(svc)
                result["output"] = res
                result["summary"] = f"Stopped service '{svc}' (success={res.get('success', False)})"
            else:
                result["summary"] = f"Ready to stop service '{svc}'."

        elif intent.type == IntentType.SERVICE_RESTART:
            svc = args.get("service", "")
            cmd = f"sudo systemctl restart '{svc}'"
            desc = f"Restarts systemd service '{svc}'."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.30
            result["requires_permission"] = not execute
            result["rollback_command"] = f"sudo systemctl restart '{svc}'"
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.30, "rollback_command": result["rollback_command"]}]
            result["steps"].append(f"Restarting service '{svc}'...")
            if execute:
                res = process_ops.restart_service(svc)
                result["output"] = res
                result["summary"] = f"Restarted service '{svc}' (success={res.get('success', False)})"
            else:
                result["summary"] = f"Ready to restart service '{svc}'."

        elif intent.type == IntentType.SERVICE_RELOAD:
            svc = args.get("service", "")
            cmd = f"sudo systemctl reload '{svc}'"
            desc = f"Reloads configuration for service '{svc}' without stopping."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.20
            result["requires_permission"] = not execute
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.20}]
            result["steps"].append(f"Reloading configuration for service '{svc}'...")
            if execute:
                res = process_ops.reload_service(svc)
                result["output"] = res
                result["summary"] = f"Reloaded service '{svc}' (success={res.get('success', False)})"
            else:
                result["summary"] = f"Ready to reload service '{svc}'."

        elif intent.type == IntentType.SERVICE_ENABLE:
            svc = args.get("service", "")
            cmd = f"sudo systemctl enable '{svc}'"
            desc = f"Enables systemd service '{svc}' to start on system boot."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.25
            result["requires_permission"] = not execute
            result["rollback_command"] = f"sudo systemctl disable '{svc}'"
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.25, "rollback_command": result["rollback_command"]}]
            result["steps"].append(f"Enabling service '{svc}' on boot...")
            if execute:
                res = process_ops.enable_service(svc)
                result["output"] = res
                result["summary"] = f"Enabled service '{svc}' on boot (success={res.get('success', False)})"
            else:
                result["summary"] = f"Ready to enable service '{svc}' on boot."

        elif intent.type == IntentType.SERVICE_DISABLE:
            svc = args.get("service", "")
            cmd = f"sudo systemctl disable '{svc}'"
            desc = f"Disables systemd service '{svc}' from starting on system boot."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.25
            result["requires_permission"] = not execute
            result["rollback_command"] = f"sudo systemctl enable '{svc}'"
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.25, "rollback_command": result["rollback_command"]}]
            result["steps"].append(f"Disabling service '{svc}' from boot...")
            if execute:
                res = process_ops.disable_service(svc)
                result["output"] = res
                result["summary"] = f"Disabled service '{svc}' from boot (success={res.get('success', False)})"
            else:
                result["summary"] = f"Ready to disable service '{svc}' from boot."

        elif intent.type == IntentType.SERVICE_LOGS:
            svc = args.get("service", "")
            cmd = f"journalctl -u '{svc}' -n 50 --no-pager -o short-iso"
            desc = f"Fetches recent journal logs for service '{svc}'."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append(f"Tailing journal logs for service '{svc}'...")
            res = log_ops.tail_log(svc, lines=50)
            result["output"] = res
            result["summary"] = f"Fetched {len(res.get('lines', []))} log lines for '{svc}'."
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.PROCESS_INFO:
            pid = args.get("pid", 0)
            cmd = f"ps -p {pid} -o pid,ppid,user,%cpu,%mem,vsz,rss,stat,etime,comm,args"
            desc = f"Inspects detailed resource utilization and hierarchy for process PID {pid}."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append(f"Querying process information for PID {pid}...")
            res = process_ops.get_process_info(pid)
            result["output"] = res
            result["summary"] = f"PID {pid} ({res.get('command', 'unknown')}): CPU {res.get('cpu', 0)}%, MEM {res.get('mem', 0)}%, State {res.get('stat', '?')}"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        # Network Tools
        elif intent.type == IntentType.NETWORK_PING:
            host = args.get("host", "1.1.1.1")
            cmd = f"ping -c 4 '{host}'"
            desc = f"Tests network reachability and round-trip latency to '{host}'."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append(f"Pinging host '{host}'...")
            res = network_ops.ping_host(host)
            result["output"] = res
            status_str = f"Reachable (avg RTT: {res.get('rtt_avg')})" if res.get("reachable") else f"Unreachable (loss: {res.get('packet_loss')})"
            result["summary"] = f"Ping {host}: {status_str}"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.NETWORK_DNS:
            host = args.get("host", "google.com")
            cmd = f"dig +short '{host}' || nslookup '{host}'"
            desc = f"Performs DNS resolution lookup for hostname '{host}'."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append(f"Resolving DNS for '{host}'...")
            res = network_ops.dns_lookup(host)
            result["output"] = res
            addrs = res.get("addresses", [])
            result["summary"] = f"DNS for {host}: {', '.join(addrs) if addrs else 'No addresses resolved'}"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.NETWORK_ROUTE:
            cmd = "ip route show"
            desc = "Displays system network routing table and default gateway."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Querying kernel routing table...")
            res = network_ops.show_routes()
            result["output"] = res
            result["summary"] = f"Routing table: {len(res.get('routes', []))} active routes."
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.FIREWALL_ALLOW:
            port = str(args.get("port", ""))
            proto = args.get("proto", "tcp")
            cmd = f"sudo ufw allow {port}/{proto}"
            desc = f"Allows incoming network traffic on {port}/{proto}."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.30
            result["requires_permission"] = not execute
            result["rollback_command"] = f"sudo ufw delete allow {port}/{proto}"
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.30, "rollback_command": result["rollback_command"]}]
            result["steps"].append(f"Configuring firewall to allow {port}/{proto}...")
            if execute:
                res = network_ops.allow_port(port, proto=proto)
                result["output"] = res
                result["summary"] = f"Allowed port {port}/{proto} (success={res.get('success', False)})"
            else:
                result["summary"] = f"Ready to allow port {port}/{proto} in firewall."

        elif intent.type == IntentType.FIREWALL_DENY:
            port = str(args.get("port", ""))
            proto = args.get("proto", "tcp")
            cmd = f"sudo ufw deny {port}/{proto}"
            desc = f"Blocks incoming network traffic on {port}/{proto}."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.30
            result["requires_permission"] = not execute
            result["rollback_command"] = f"sudo ufw delete deny {port}/{proto}"
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.30, "rollback_command": result["rollback_command"]}]
            result["steps"].append(f"Configuring firewall to block {port}/{proto}...")
            if execute:
                res = network_ops.deny_port(port, proto=proto)
                result["output"] = res
                result["summary"] = f"Blocked port {port}/{proto} (success={res.get('success', False)})"
            else:
                result["summary"] = f"Ready to block port {port}/{proto} in firewall."

        # Crontab Automation
        elif intent.type == IntentType.CRON_ADD:
            schedule = args.get("schedule", "0 2 * * *")
            command = args.get("command", "")
            cmd = f"(crontab -l 2>/dev/null; echo '{schedule} {command}') | crontab -"
            desc = f"Adds scheduled cron job: '{schedule} {command}'."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.MODIFYING.value
            result["risk_score"] = 0.40
            result["requires_permission"] = not execute
            result["rollback_command"] = f"crontab -l | grep -vF '{command}' | crontab -"
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.MODIFYING.value, "risk_score": 0.40, "rollback_command": result["rollback_command"]}]
            result["steps"].append(f"Adding cron job '{schedule} {command}'...")
            if execute:
                res = system_ops.add_cron_job(schedule, command)
                result["output"] = res
                result["summary"] = res.get("message") or res.get("error", "Added cron job")
            else:
                result["summary"] = f"Ready to add cron job '{schedule} {command}'."

        # System Inspection & Power
        elif intent.type == IntentType.SYSTEM_INFO:
            cmd = "uname -a && cat /etc/os-release"
            desc = "Displays host OS distribution, kernel version, and architecture."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            d_info = DistroDetector().detect()
            snap = self.hub.get_health_snapshot()
            result["output"] = {"distro": d_info.to_dict(), "kernel": snap.kernel_release, "hostname": snap.hostname}
            d_name = getattr(d_info, "display_name", None) or getattr(d_info, "distro_name", "Linux")
            result["summary"] = f"{d_name} | Kernel {snap.kernel_release} on {snap.hostname}"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.SYSTEM_UPTIME:
            cmd = "uptime"
            desc = "Shows system uptime duration and 1/5/15 minute load averages."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Checking system uptime and load...")
            snap = self.hub.get_health_snapshot()
            hours = round(snap.uptime_seconds / 3600, 1)
            result["output"] = {"uptime_seconds": snap.uptime_seconds, "uptime_hours": hours, "load": asdict(snap.load)}
            result["summary"] = f"Uptime: {hours} hours | Load: {snap.load.load_1m}, {snap.load.load_5m}, {snap.load.load_15m}"
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.SYSTEM_REBOOT:
            cmd = "sudo reboot"
            desc = "Reboots the operating system."
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = SafetyLevel.HIGH_RISK.value
            result["risk_score"] = 0.85
            result["requires_permission"] = not execute
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.HIGH_RISK.value, "risk_score": 0.85}]
            result["steps"].append("Preparing system reboot...")
            if execute:
                result["summary"] = "System reboot requested (requires elevated execution)."
            else:
                result["summary"] = "Ready to reboot system (requires confirmation)."

        # User Management
        elif intent.type == IntentType.USER_LIST:
            cmd = "cat /etc/passwd"
            desc = "Lists local system users from /etc/passwd."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Querying local system users...")
            res = log_ops.list_all_users()
            result["output"] = res
            result["summary"] = f"Found {len(res.get('users', []))} system users in /etc/passwd."
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.USER_WHO:
            cmd = "who"
            desc = "Displays currently logged-in user sessions and active TTYs."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Querying active user sessions...")
            res = log_ops.who_is_logged_in()
            result["output"] = res
            result["summary"] = f"Logged-in sessions: {len(res.get('sessions', []))} active."
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        # Logs & Diagnostics
        elif intent.type == IntentType.LOGS_SHOW:
            target = args.get("path") or args.get("service") or "syslog"
            cmd = f"journalctl -u '{target}' -n 50 --no-pager"
            desc = f"Tails recent log entries for '{target}'."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append(f"Tailing logs for '{target}'...")
            res = log_ops.tail_log(target, lines=50)
            result["output"] = res
            result["summary"] = f"Tailed {len(res.get('lines', []))} lines from {res.get('source', target)}."
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.LOGS_ERRORS:
            cmd = "journalctl -p err --since='1h ago' -n 50 --no-pager"
            desc = "Surfaces recent error and critical priority log messages."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Scanning journal for error and critical log records...")
            res = log_ops.show_errors(since="1h")
            result["output"] = res
            result["summary"] = f"Found {res.get('count', 0)} error-level log entries in the past hour."
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        elif intent.type == IntentType.LOGS_KERNEL:
            cmd = "dmesg -T --level=err,warn -x"
            desc = "Queries kernel ring buffer for hardware and driver errors."
            result["command"] = cmd
            result["command_description"] = desc
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": SafetyLevel.READ_ONLY.value, "risk_score": 0.05}]
            result["steps"].append("Querying kernel ring buffer (dmesg)...")
            res = log_ops.show_kernel_errors(lines=50)
            result["output"] = res
            result["summary"] = f"Found {res.get('count', 0)} kernel error/warning messages."
            result["safety_level"] = SafetyLevel.READ_ONLY.value
            result["risk_score"] = 0.05

        # Package Operations
        elif intent.type in (IntentType.PACKAGE_INSTALL, IntentType.PACKAGE_REMOVE, IntentType.PACKAGE_UPDATE, IntentType.PACKAGE_SEARCH):
            pkg = args.get("package", "")
            d_info = DistroDetector().detect()
            pkg_mgr = d_info.package_manager
            act = "install" if intent.type == IntentType.PACKAGE_INSTALL else ("remove" if intent.type == IntentType.PACKAGE_REMOVE else ("update" if intent.type == IntentType.PACKAGE_UPDATE else "search"))
            cmd = f"sudo {pkg_mgr} {act} {pkg}".strip()
            desc = f"Executes package manager {act} action for '{pkg}'."
            is_modifying = intent.type != IntentType.PACKAGE_SEARCH
            safety = SafetyLevel.MODIFYING.value if is_modifying else SafetyLevel.READ_ONLY.value
            risk = 0.35 if is_modifying else 0.05
            result["command"] = cmd
            result["command_description"] = desc
            result["safety_level"] = safety
            result["risk_score"] = risk
            result["requires_permission"] = is_modifying and not execute
            result["planned_commands"] = [{"command": cmd, "description": desc, "safety_level": safety, "risk_score": risk}]
            result["steps"].append(f"Preparing package {act} for '{pkg}' via {pkg_mgr}...")
            result["summary"] = f"Package {act} command for {pkg_mgr}: '{cmd}'."


        else:
            result["steps"].append("Analyzing multi-vector telemetry & matching 16-class failure taxonomies...")
            distro_override = context.get("distro") if context else None
            report = self.diagnose(query, distro_override=distro_override)
            result["diagnostic_report"] = report.to_dict()
            result["output"] = report.to_dict()
            result["summary"] = f"{report.explanation.symptom} — Root cause: {report.explanation.root_cause}"
            if report.explanation.proposed_commands:
                first_cmd = report.explanation.proposed_commands[0]
                result["command"] = first_cmd.command
                result["command_description"] = first_cmd.rationale
                result["safety_level"] = first_cmd.safety_level.value if hasattr(first_cmd.safety_level, 'value') else str(first_cmd.safety_level)
                result["risk_score"] = first_cmd.risk_score
                result["rollback_command"] = first_cmd.rollback_command
                result["planned_commands"] = [
                    {
                        "command": c.command,
                        "description": c.rationale,
                        "safety_level": c.safety_level.value if hasattr(c.safety_level, 'value') else str(c.safety_level),
                        "risk_score": c.risk_score,
                        "rollback_command": c.rollback_command,
                        "sandbox_verified": getattr(c, "sandbox_verified", False)
                    }
                    for c in report.explanation.proposed_commands
                ]

        return result

