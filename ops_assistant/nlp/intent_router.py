"""
Intent Router — Hybrid NL→Action classifier for the Linux Ops Assistant.

Uses a two-stage pipeline:
  1. Fast regex/keyword pattern matching (deterministic, offline)
  2. LLM fallback for ambiguous or complex expressions (optional)

Maps any free-form English utterance to a structured Intent with extracted
arguments ready for dispatch to tool functions.
"""

from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Intent taxonomy
# ---------------------------------------------------------------------------

class IntentType(Enum):
    # Storage
    STORAGE_ANALYSE    = "storage_analyse"
    STORAGE_CLEAN      = "storage_clean"
    STORAGE_ORGANISE   = "storage_organise"
    STORAGE_FIND_LARGE = "storage_find_large"

    # Processes
    PROCESS_LIST       = "process_list"
    PROCESS_KILL       = "process_kill"
    PROCESS_INFO       = "process_info"

    # Services (systemd / init)
    SERVICE_STATUS     = "service_status"
    SERVICE_START      = "service_start"
    SERVICE_STOP       = "service_stop"
    SERVICE_RESTART    = "service_restart"
    SERVICE_ENABLE     = "service_enable"
    SERVICE_DISABLE    = "service_disable"
    SERVICE_RELOAD     = "service_reload"
    SERVICE_LOGS       = "service_logs"

    # Packages
    PACKAGE_INSTALL    = "package_install"
    PACKAGE_REMOVE     = "package_remove"
    PACKAGE_UPDATE     = "package_update"
    PACKAGE_SEARCH     = "package_search"

    # Network
    NETWORK_STATUS     = "network_status"
    NETWORK_PORTS      = "network_ports"
    NETWORK_PING       = "network_ping"
    NETWORK_DNS        = "network_dns"
    NETWORK_ROUTE      = "network_route"

    # Files
    FILE_FIND          = "file_find"
    FILE_SHOW          = "file_show"
    FILE_EDIT          = "file_edit"

    # Logs & Errors
    LOGS_SHOW          = "logs_show"
    LOGS_ERRORS        = "logs_errors"
    LOGS_KERNEL        = "logs_kernel"

    # Cron / scheduling
    CRON_LIST          = "cron_list"
    CRON_ADD           = "cron_add"

    # Users & permissions
    USER_LIST          = "user_list"
    USER_WHO           = "user_who"

    # Firewall
    FIREWALL_STATUS    = "firewall_status"
    FIREWALL_ALLOW     = "firewall_allow"
    FIREWALL_DENY      = "firewall_deny"

    # System info
    SYSTEM_INFO        = "system_info"
    SYSTEM_UPTIME      = "system_uptime"
    SYSTEM_REBOOT      = "system_reboot"

    # Remediation menu (REPL action prompt)
    REMEDIATION_EXEC_N  = "remediation_exec_n"   # execute command N
    REMEDIATION_EXEC_ALL = "remediation_exec_all"
    REMEDIATION_DRY_RUN  = "remediation_dry_run"
    REMEDIATION_INSPECT  = "remediation_inspect"
    REMEDIATION_ROLLBACK = "remediation_rollback"
    REMEDIATION_SKIP     = "remediation_skip"

    # Desktop & Automation
    DESKTOP_OPEN_FOLDER = "desktop_open_folder"
    DESKTOP_OPEN_FILE   = "desktop_open_file"
    DESKTOP_OPEN_IMAGE  = "desktop_open_image"
    DESKTOP_OPEN_BROWSER = "desktop_open_browser"
    DOWNLOAD_URL        = "download_url"
    FILE_MOVE           = "file_move"
    FILE_COPY           = "file_copy"
    FILE_TRASH          = "file_trash"

    # Hardware & AI Model Advisory
    HARDWARE_PROFILE     = "hardware_profile"
    HARDWARE_RECOMMEND_MODEL = "hardware_recommend_model"
    HARDWARE_AUTO_TUNE   = "hardware_auto_tune"

    # Proactive Health Audit
    PROACTIVE_AUDIT      = "proactive_audit"

    # Docker & Containers
    DOCKER_LIST          = "docker_list"
    DOCKER_LOGS          = "docker_logs"
    DOCKER_RESTART       = "docker_restart"
    DOCKER_PRUNE         = "docker_prune"

    # System Maintenance & Boot Performance
    CRON_REMOVE          = "cron_remove"
    SYSTEM_BOOT_ANALYSIS = "system_boot_analysis"
    SYSTEM_TRIM_SSD      = "system_trim_ssd"
    SYSTEM_PACKAGE_CLEAN = "system_package_clean"
    SYSTEM_JOURNAL_VACUUM = "system_journal_vacuum"

    # Security & Vulnerability Audits
    SECURITY_AUDIT       = "security_audit"
    SECURITY_SSH_CHECK   = "security_ssh_check"
    SECURITY_BRUTEFORCE  = "security_bruteforce"
    SECURITY_SUID        = "security_suid"

    # Backup & Restore
    BACKUP_CREATE        = "backup_create"
    BACKUP_LIST          = "backup_list"
    BACKUP_RESTORE       = "backup_restore"

    # Extended File & Directory Operations
    FILE_CREATE          = "file_create"
    FILE_DELETE          = "file_delete"
    FILE_READ            = "file_read"
    DIR_CREATE           = "dir_create"
    DIR_DELETE           = "dir_delete"
    DIR_LIST             = "dir_list"
    PERM_CHANGE          = "perm_change"
    ARCHIVE_CREATE       = "archive_create"
    ARCHIVE_EXTRACT      = "archive_extract"
    NETWORK_CURL         = "network_curl"
    SYSTEM_WHOAMI        = "system_whoami"
    SYSTEM_ENV           = "system_env"
    GENERIC_COMMAND      = "generic_command"

    # Command & Error Explanation
    COMMAND_EXPLAIN      = "command_explain"

    # Project Operations
    PROJECT_INSTALL_DEPS = "project_install_deps"
    PROJECT_CREATE_VENV  = "project_create_venv"

    # Specialized Storage & Maintenance
    STORAGE_CLEAN_TRASH  = "storage_clean_trash"
    SYSTEM_CHECK_CPU     = "system_check_cpu"
    SYSTEM_CHECK_RAM     = "system_check_ram"
    SYSTEM_CHECK_DISK    = "system_check_disk"
    SYSTEM_UPDATE        = "system_update"
    SYSTEM_FIND_LARGE    = "system_find_large"

    # Pass-through shell
    SHELL_RUN          = "shell_run"

    # Assistant meta
    DIAGNOSE           = "diagnose"   # original diagnostic engine
    HEALTH             = "health"
    HELP               = "help"
    CLEAR              = "clear"
    EXIT               = "exit"
    HISTORY            = "history"
    ROLLBACK           = "rollback"
    EXPORT             = "export"

    UNKNOWN            = "unknown"


@dataclass
class Intent:
    """A classified user intent with extracted arguments."""
    type: IntentType
    args: Dict[str, Any] = field(default_factory=dict)
    raw: str = ""
    confidence: float = 1.0
    ambiguous: bool = False

    def __repr__(self) -> str:
        return f"Intent({self.type.value}, args={self.args}, conf={self.confidence:.2f})"


# ---------------------------------------------------------------------------
# Pattern rules
# ---------------------------------------------------------------------------

# Each rule: (IntentType, [(regex_pattern, arg_extractor_fn or None), ...])
# arg_extractor receives the re.Match and returns a dict.

def _sanitize_arg(val: str) -> str:
    """Strip dangerous control characters, newlines, and null bytes from extracted arguments."""
    if not isinstance(val, str):
        return val
    return re.sub(r"[\x00-\x1f\x7f]", "", val).strip()


def _sanitize_token(val: str) -> str:
    """Sanitize strict identifier tokens (services, packages, container names)."""
    if not isinstance(val, str):
        return val
    val = re.sub(r"[\x00-\x1f\x7f]", "", val)
    return re.sub(r"[/;&|`$<>(){}\[\]\\\"']", "", val).strip().rstrip("?.,!")


def _extract_service(m: re.Match) -> Dict[str, Any]:
    """Pull the service name from a named group 'svc'."""
    svc = _sanitize_token(m.group("svc") or "")
    return {"service": svc} if svc else {}


def _extract_package(m: re.Match) -> Dict[str, Any]:
    pkg = _sanitize_token(m.group("pkg") or "")
    return {"package": pkg} if pkg else {}


def _extract_path(m: re.Match) -> Dict[str, Any]:
    try:
        path = _sanitize_arg(m.group("path") or "").strip("\"'")
        return {"path": path} if path else {}
    except IndexError:
        return {}


def _extract_host(m: re.Match) -> Dict[str, Any]:
    host = _sanitize_token(m.group("host") or "")
    return {"host": host} if host else {}


def _extract_port(m: re.Match) -> Dict[str, Any]:
    port = (m.group("port") or "").strip()
    digits = re.sub(r"\D", "", port)
    return {"port": digits} if digits else {}


def _extract_url(m: re.Match) -> Dict[str, Any]:
    try:
        url = _sanitize_arg(m.group("url") or "").strip("\"'") if "url" in m.groupdict() and m.group("url") else ""
        return {"url": url or "https://google.com"}
    except Exception:
        return {"url": "https://google.com"}


def _extract_cmd(m: re.Match) -> Dict[str, Any]:
    try:
        cmd = _sanitize_arg(m.group("cmd") or "").strip().strip("\"'`")
        return {"command": cmd}
    except Exception:
        return {}


def _extract_project_args(m: re.Match) -> Dict[str, Any]:
    try:
        path = _sanitize_arg(m.group("path") or "").strip("\"'") if "path" in m.groupdict() and m.group("path") else "."
        name = _sanitize_token(m.group("name") or "") if "name" in m.groupdict() and m.group("name") else "venv"
        return {"path": path or ".", "venv_name": name or "venv"}
    except Exception:
        return {"path": ".", "venv_name": "venv"}


def _extract_move_copy(m: re.Match) -> Dict[str, Any]:
    try:
        src = (m.group("src") or "").strip().strip("\"'")
        dst = (m.group("dst") or "").strip().strip("\"'")
        res: Dict[str, Any] = {}
        if src:
            res["src"] = src
        if dst:
            res["dst"] = dst
        return res
    except Exception:
        return {}


def _extract_download(m: re.Match) -> Dict[str, Any]:
    try:
        url = (m.group("url") or "").strip().strip("\"'")
        dest = (m.group("dest") or "").strip().strip("\"'") if "dest" in m.groupdict() and m.group("dest") else None
        res: Dict[str, Any] = {"url": url}
        if dest:
            res["dest"] = dest
        return res
    except Exception:
        return {}


def _extract_folder_path(m: re.Match) -> Dict[str, Any]:
    try:
        named_dir = m.group("dir") if "dir" in m.groupdict() and m.group("dir") else None
        if named_dir:
            named_map = {
                "downloads": "~/Downloads", "download": "~/Downloads",
                "documents": "~/Documents", "document": "~/Documents",
                "pictures": "~/Pictures", "picture": "~/Pictures",
                "desktop": "~/Desktop", "music": "~/Music",
                "videos": "~/Videos", "video": "~/Videos",
                "home": "~", "root": "/"
            }
            path = named_map.get(named_dir.lower(), f"~/{named_dir.capitalize()}")
            return {"path": path}
        path = (m.group("path") or "").strip().strip("\"'")
        return {"path": path} if path else {"path": "~"}
    except Exception:
        return {"path": "~"}


def _extract_pid(m: re.Match) -> Dict[str, Any]:
    try:
        pid = m.group("pid")
        name = m.group("name") if "name" in m.groupdict() else None
        result: Dict[str, Any] = {}
        if pid:
            result["pid"] = int(pid)
        if name:
            result["name"] = name.strip()
        return result
    except Exception:
        return {}


def _extract_container(m: re.Match) -> Dict[str, Any]:
    try:
        c = (m.group("container") or "").strip().rstrip("?.,!")
        return {"container": c} if c else {}
    except Exception:
        return {}


def _extract_cron_pattern(m: re.Match) -> Dict[str, Any]:
    try:
        pat = (m.group("pattern") or "").strip()
        return {"pattern": pat} if pat else {}
    except Exception:
        return {}


def _extract_backup_args(m: re.Match) -> Dict[str, Any]:
    try:
        path = (m.group("path") or "").strip().strip("\"'")
        dest = (m.group("dest") or "").strip().strip("\"'") if "dest" in m.groupdict() and m.group("dest") else None
        res: Dict[str, Any] = {"path": path} if path else {}
        if dest:
            res["dest"] = dest
        return res
    except Exception:
        return {}


def _extract_file_create(m: re.Match) -> Dict[str, Any]:
    try:
        path = (m.group("path") or "").strip().strip("\"'")
        content = (m.group("content") or "").strip().strip("\"'") if "content" in m.groupdict() and m.group("content") else ""
        return {"path": path, "content": content}
    except Exception:
        return {}


def _extract_file_delete(m: re.Match) -> Dict[str, Any]:
    try:
        path = (m.group("path") or "").strip().strip("\"'")
        return {"path": path} if path else {}
    except Exception:
        return {}


def _extract_dir_path(m: re.Match) -> Dict[str, Any]:
    try:
        path = (m.group("path") or "").strip().strip("\"'")
        return {"path": path} if path else {"path": "."}
    except Exception:
        return {"path": "."}


def _extract_perm_change(m: re.Match) -> Dict[str, Any]:
    try:
        path = (m.group("path") or "").strip().strip("\"'")
        mode = (m.group("mode") or "").strip().strip("\"'") if "mode" in m.groupdict() and m.group("mode") else "+x"
        owner = (m.group("owner") or "").strip().strip("\"'") if "owner" in m.groupdict() and m.group("owner") else ""
        res: Dict[str, Any] = {"path": path}
        if mode:
            res["mode"] = mode
        if owner:
            res["owner"] = owner
        return res
    except Exception:
        return {}


def _extract_archive(m: re.Match) -> Dict[str, Any]:
    try:
        src = (m.group("src") or "").strip().strip("\"'")
        dest = (m.group("dest") or "").strip().strip("\"'") if "dest" in m.groupdict() and m.group("dest") else ""
        return {"src": src, "dest": dest}
    except Exception:
        return {}


_RULES: List[Tuple[IntentType, List[Tuple[str, Optional]]]] = [

    # -----------------------------------------------------------------------
    # Exit / quit
    # -----------------------------------------------------------------------
    (IntentType.EXIT, [
        (r"^(exit|quit|bye|goodbye|q)$", None),
    ]),

    # -----------------------------------------------------------------------
    # Help
    # -----------------------------------------------------------------------
    (IntentType.HELP, [
        (r"^(help|\?)$", None),
        (r"\bhelp\b", None),
        (r"what can you do", None),
        (r"list commands", None),
        (r"show commands", None),
    ]),

    # -----------------------------------------------------------------------
    # Clear
    # -----------------------------------------------------------------------
    (IntentType.CLEAR, [
        (r"^(clear|cls)$", None),
    ]),

    # -----------------------------------------------------------------------
    # Shell passthrough — MUST be early so ":run df -h" isn't stolen by df→storage
    # -----------------------------------------------------------------------
    (IntentType.SHELL_RUN, [
        (r"^:run\s+(?P<cmd>.+)$", lambda m: {"cmd": m.group("cmd").strip()}),
        (r"^run:\s*(?P<cmd>.+)$",  lambda m: {"cmd": m.group("cmd").strip()}),
        (r"^!\s*(?P<cmd>.+)$",     lambda m: {"cmd": m.group("cmd").strip()}),
    ]),

    # -----------------------------------------------------------------------
    # Health / status dashboard
    # -----------------------------------------------------------------------
    (IntentType.HEALTH, [
        (r"^(health|status)$", None),
        (r"\b(system health|health (check|status|snapshot))\b", None),
        (r"\bhow is (my |the )?(system|server|machine)\b", None),
        (r"\bshow (system |server )?(health|status|overview)\b", None),
    ]),

    # -----------------------------------------------------------------------
    # System info
    # -----------------------------------------------------------------------
    (IntentType.SYSTEM_INFO, [
        (r"\b(system info|sysinfo|uname|what (distro|os|linux) am i)\b", None),
        (r"\bshow (me |the )?(system|os|kernel) (info|information|version)\b", None),
        (r"\bwhat (version|kernel|distro)\b", None),
    ]),

    (IntentType.SYSTEM_UPTIME, [
        (r"\b(uptime|how long (has|have) (the |it |system )?been (up|running))\b", None),
    ]),

    (IntentType.SYSTEM_REBOOT, [
        (r"\b(reboot|restart the (system|server|machine|box))\b", None),
    ]),

    # -----------------------------------------------------------------------
    # Desktop Operations
    # -----------------------------------------------------------------------
    (IntentType.DESKTOP_OPEN_FOLDER, [
        (r"\b(?:open|launch|show)\s+(?:the\s+|my\s+)?(?P<dir>downloads|documents|pictures|desktop|music|videos|home|root)\s+(?:folder|dir|directory)\b", _extract_folder_path),
        (r"\b(?:open|launch|show)\s+(?:the\s+|my\s+)?(?P<dir>downloads|documents|pictures|desktop|music|videos|home)\b", _extract_folder_path),
        (r"\b(?:open|launch|explore)\s+(?:folder|directory|dir)\s+(?P<path>[\w\.\-\/~]+)", _extract_folder_path),
        (r"\b(?:open|explore)\s+(?P<path>(?:~|\/|\.\/)[^\s]+)\s+in\s+(?:file\s+manager|folder|finder|explorer|nautilus|dolphin|thunar)\b", _extract_folder_path),
        (r"\b(?:open|launch)\s+in\s+(?:file\s+manager|nautilus|dolphin|thunar)\s+(?P<path>[\w\.\-\/~]+)", _extract_folder_path),
    ]),

    (IntentType.DESKTOP_OPEN_IMAGE, [
        (r"\b(?:open|show|view|display)\s+(?:image|photo|picture|screenshot|pic)\s+(?P<path>[\w\.\-\/~]+)", _extract_path),
        (r"\b(?:open|view|show)\s+(?P<path>[\w\.\-\/~]+\.(?:png|jpg|jpeg|gif|bmp|svg|webp|tiff|ico))\b", _extract_path),
    ]),

    (IntentType.DESKTOP_OPEN_FILE, [
        (r"\b(?:open|launch|view)\s+(?:file|document|doc)\s+(?P<path>[\w\.\-\/~]+)", _extract_path),
        (r"\b(?:open|view)\s+(?P<path>[\w\.\-\/~]+\.(?:txt|json|yml|yaml|md|conf|cfg|py|sh|c|h|cpp|log|html|css|js|pdf|docx|odt))\b", _extract_path),
    ]),

    (IntentType.DESKTOP_OPEN_BROWSER, [
        (r"\b(?:open|launch|start)\s+(?:my\s+)?(?:web\s+)?(?:browser|chrome|firefox|brave|chromium)\b", _extract_url),
        (r"\b(?:open|launch|browse)\s+(?:in\s+)?(?:browser|web|chrome|firefox)\s+(?P<url>[^\s]+)", _extract_url),
        (r"\b(?:open|launch|browse)\s+(?:website|url|link|page)\s+(?P<url>[^\s]+)", _extract_url),
        (r"\b(?:open|browse\s+to)\s+(?P<url>https?:\/\/[^\s]+)", _extract_url),
        (r"\bopen\s+(?P<url>(?:www\.)?[a-zA-Z0-9\-]+\.[a-z]{2,}(?:\/[^\s]*)?)\s+in\s+browser\b", _extract_url),
        (r"^(?:open|launch)\s+browser$", _extract_url),
    ]),

    # -----------------------------------------------------------------------
    # Command & Error Explanation
    # -----------------------------------------------------------------------
    (IntentType.COMMAND_EXPLAIN, [
        (r"^(?:explain|what\s+does|how\s+does)\s+(?:this\s+)?(?:linux\s+)?(?:command|cmd)?\s*[:\?]?\s*(?P<cmd>.+)$", _extract_cmd),
        (r"^(?:explain|decode|breakdown)\s+(?P<cmd>(?:tar|chmod|chown|find|grep|awk|sed|curl|wget|ps|kill|pkill|systemctl|journalctl|df|free|ip|iptables|ufw|docker|git|cp|mv|rm|mkdir|cat|ls|head|tail)\b.+)$", _extract_cmd),
        (r"^what\s+does\s+(?P<cmd>[a-zA-Z0-9_\-\.\/]+(?:\s+-[a-zA-Z0-9_\-\.\/]+)*.*?)\s+do\??$", _extract_cmd),
    ]),

    # -----------------------------------------------------------------------
    # Project & Developer Operations
    # -----------------------------------------------------------------------
    (IntentType.PROJECT_INSTALL_DEPS, [
        (r"\b(?:install|setup|fetch|download)\s+(?:project\s+|all\s+)?dependencies\b", _extract_project_args),
        (r"\b(?:install|setup)\s+(?:the\s+)?requirements(?:\.txt)?\b", _extract_project_args),
        (r"\b(?:run\s+|execute\s+)?(?:npm|pip|cargo|yarn|pnpm|bundle)\s+install\b", _extract_project_args),
        (r"\binstall\s+dependencies\s+(?:in|for)\s+(?P<path>[\w\.\-\/~]+)", _extract_project_args),
    ]),

    (IntentType.PROJECT_CREATE_VENV, [
        (r"\b(?:create|make|setup)\s+(?:a\s+)?(?:python\s+)?(?:virtual\s*env(?:ironment)?|venv)(?:\s+(?:named|called)\s+(?P<name>[\w\.\-]+))?\b", _extract_project_args),
        (r"\bpython3?\s+-m\s+venv\s+(?P<name>[\w\.\-]+)\b", _extract_project_args),
        (r"\bcreate\s+(?:a\s+)?venv\s+(?:in|at)\s+(?P<path>[\w\.\-\/~]+)", _extract_project_args),
    ]),

    # -----------------------------------------------------------------------
    # Specialized System Resource & Maintenance Checks
    # -----------------------------------------------------------------------
    (IntentType.SYSTEM_CHECK_CPU, [
        (r"\b(?:check|show|get|view|inspect)\s+(?:my\s+)?(?:cpu|processor)(?:\s+usage|\s+load|\s+status|\s+utilization)?\b", None),
        (r"\bhow\s+is\s+(?:the\s+|my\s+)?cpu\s+(?:doing|load|usage)\b", None),
        (r"^(?:cpu|processor)$", None),
    ]),

    (IntentType.SYSTEM_CHECK_RAM, [
        (r"\b(?:check|show|get|view|inspect)\s+(?:my\s+)?(?:ram|memory|swap)(?:\s+usage|\s+status|\s+free|\s+headroom)?\b", None),
        (r"\bhow\s+much\s+(?:ram|memory)\s+(?:is\s+free|available|used)\b", None),
        (r"^(?:free|ram|mem|memory)$", None),
    ]),

    (IntentType.STORAGE_ANALYSE, [
        (r"\b(?:check|show|get|view|inspect)\s+(?:my\s+)?(?:disk|storage|filesystem|drive)(?:\s+usage|\s+space|\s+status|\s+capacity)?\b", None),
        (r"\bhow\s+much\s+disk\s+(?:space\s+)?(?:is\s+free|available|used)\b", None),
        (r"^(?:df|disk|storage)$", None),
    ]),

    (IntentType.STORAGE_CLEAN_TRASH, [
        (r"\b(?:clean|empty|clear|purge|trash)\s+(?:my\s+)?trash(?:\s+can|\s+bin|\s+folder|\s+directory)?\b", None),
        (r"\bempty\s+the\s+trash\b", None),
    ]),

    (IntentType.SYSTEM_UPDATE, [
        (r"\b(?:update|upgrade)\s+(?:my\s+)?(?:system|os|linux|distro|all\s+packages)\b", None),
        (r"\b(?:run\s+)?system\s+update\b", None),
    ]),

    # -----------------------------------------------------------------------
    # Download Operations
    # -----------------------------------------------------------------------
    (IntentType.DOWNLOAD_URL, [
        (r"\bdownload\s+(?:url\s+|file\s+|archive\s+|from\s+)?(?P<url>https?:\/\/[^\s]+)\s+to\s+(?P<dest>[\w\.\-\/~]+)", _extract_download),
        (r"\bdownload\s+(?:url\s+|file\s+|archive\s+|from\s+)?(?P<url>https?:\/\/[^\s]+)", _extract_download),
        (r"\bfetch\s+(?:url\s+|file\s+|archive\s+|from\s+)?(?P<url>https?:\/\/[^\s]+)\s+to\s+(?P<dest>[\w\.\-\/~]+)", _extract_download),
        (r"\bfetch\s+(?:url\s+|file\s+|archive\s+|from\s+)?(?P<url>https?:\/\/[^\s]+)", _extract_download),
    ]),

    # -----------------------------------------------------------------------
    # File Operations (Move, Copy, Trash)
    # -----------------------------------------------------------------------
    (IntentType.FILE_MOVE, [
        (r"\b(?:move|mv|relocate)\s+(?P<src>[\w\.\-\/~]+)\s+(?:to|into)\s+(?P<dst>[\w\.\-\/~]+)", _extract_move_copy),
        (r"^mv\s+(?P<src>[\w\.\-\/~]+)\s+(?P<dst>[\w\.\-\/~]+)$", _extract_move_copy),
    ]),

    (IntentType.FILE_COPY, [
        (r"\b(?:copy|cp|duplicate)\s+(?P<src>[\w\.\-\/~]+)\s+(?:to|into|as)\s+(?P<dst>[\w\.\-\/~]+)", _extract_move_copy),
        (r"^cp\s+(?:-r\s+)?(?P<src>[\w\.\-\/~]+)\s+(?P<dst>[\w\.\-\/~]+)$", _extract_move_copy),
    ]),

    (IntentType.FILE_TRASH, [
        (r"\b(?:trash|safely\s+delete|move\s+to\s+trash)\s+(?P<path>[\w\.\-\/~]+)", _extract_path),
    ]),

    # -----------------------------------------------------------------------
    # Hardware & Performance Advisory
    # -----------------------------------------------------------------------
    (IntentType.HARDWARE_RECOMMEND_MODEL, [
        (r"\b(which|what)\s+(?:ai\s+|llm\s+|gguf\s+)?model\s+(?:should\s+i|to)\s+(?:download|run|use|get)\b", None),
        (r"\brecommend\s+(?:an?\s+)?(?:ai\s+|llm\s+|gguf\s+)?model\b", None),
        (r"\bmodel\s+recommendation\b", None),
        (r"\bwhat\s+model\s+fits\s+my\s+(?:hardware|gpu|ram|cpu|system)\b", None),
    ]),

    (IntentType.HARDWARE_AUTO_TUNE, [
        (r"\b(?:auto[- ]?tune|benchmark\s+and\s+tune|tune\s+(?:my\s+)?(?:hardware|system|model))\b", None),
        (r"\boptimize\s+(?:ai\s+|model\s+)?settings\s+for\s+my\s+hardware\b", None),
    ]),

    (IntentType.HARDWARE_PROFILE, [
        (r"\b(?:check|profile|benchmark|inspect|test|show|get)\s+(?:my\s+)?(?:gpu|hardware|vram|specs|capabilities)\b", None),
        (r"\bhardware\s+(?:profile|specs|benchmark|info|inspection|audit)\b", None),
        (r"\bhow\s+much\s+(?:vram|ram|gpu\s+memory)\s+do\s+i\s+have\b", None),
        (r"\bwhat\s+(?:gpu|hardware)\s+do\s+i\s+have\b", None),
    ]),

    # -----------------------------------------------------------------------
    # Proactive Health Audit
    # -----------------------------------------------------------------------
    (IntentType.PROACTIVE_AUDIT, [
        (r"\b(?:run\s+|do\s+)?(?:a\s+)?(?:proactive|full\s+system|deep)\s+(?:audit|health\s+check|scan|inspection)\b", None),
        (r"\bproactive\s+(?:audit|health|check)\b", None),
        (r"\b(?:scan|check|inspect)\s+(?:the\s+)?(?:system\s+)?(?:for\s+)?(?:potential\s+)?(?:bottlenecks|risks|issues|problems)\b", None),
        (r"\bfind\s+(?:any\s+)?potential\s+(?:issues|problems|bottlenecks)\b", None),
    ]),

    # -----------------------------------------------------------------------
    # Docker & Containers
    # -----------------------------------------------------------------------
    (IntentType.DOCKER_LIST, [
        (r"\b(?:show|list|get)\s+(?:all\s+)?(?:docker\s+)?containers?\b", None),
        (r"^docker\s+ps\b", None),
        (r"\bwhat\s+containers?\s+(?:are\s+running|exist)\b", None),
    ]),

    (IntentType.DOCKER_LOGS, [
        (r"\b(?:show|get|view|tail|check)\s+(?:docker\s+)?logs?\s+(?:for|of|from)\s+(?:container\s+)?(?P<container>[\w\.\-]+)\b", _extract_container),
        (r"\bdocker\s+logs\s+(?P<container>[\w\.\-]+)\b", _extract_container),
        (r"\b(?:show|get|view|tail)\s+logs?\s+for\s+(?:container\s+|docker\s+container\s+)(?P<container>[\w\.\-]+)\b", _extract_container),
    ]),

    (IntentType.DOCKER_RESTART, [
        (r"\brestart\s+(?:docker\s+)?container\s+(?P<container>[\w\.\-]+)\b", _extract_container),
        (r"^docker\s+restart\s+(?P<container>[\w\.\-]+)\b", _extract_container),
    ]),

    (IntentType.DOCKER_PRUNE, [
        (r"\b(?:clean|prune|purge)\s+(?:up\s+)?(?:all\s+)?(?:unused\s+)?(?:docker|containers?|images?|builder|dangling\s+images?)\b", None),
        (r"^docker\s+system\s+prune\b", None),
        (r"\bprune\s+(?:unused\s+)?docker\b", None),
    ]),

    # -----------------------------------------------------------------------
    # Cron removal
    # -----------------------------------------------------------------------
    (IntentType.CRON_REMOVE, [
        (r"\b(?:remove|delete)\s+cron\s+(?:job|entry)\s+(?P<pattern>.+)\b", _extract_cron_pattern),
        (r"\bdelete\s+scheduled\s+task\s+(?P<pattern>.+)\b", _extract_cron_pattern),
    ]),

    # -----------------------------------------------------------------------
    # System maintenance & Boot
    # -----------------------------------------------------------------------
    (IntentType.SYSTEM_BOOT_ANALYSIS, [
        (r"\b(?:analyze|check|show)\s+(?:boot|startup)\s+(?:time|blame|bottlenecks?|speed)\b", None),
        (r"\bwhy\s+is\s+(?:boot|startup)\s+slow\b", None),
        (r"^systemd-analyze\b", None),
    ]),

    (IntentType.SYSTEM_TRIM_SSD, [
        (r"\b(?:trim|fstrim)\s+(?:ssd|ssds|disks?|drives?)\b", None),
        (r"\boptimize\s+ssd\b", None),
    ]),

    (IntentType.SYSTEM_PACKAGE_CLEAN, [
        (r"\b(?:clean|clear|purge)\s+(?:up\s+)?(?:package\s+cache|apt\s+cache|apt\s+package\s+cache|dnf\s+cache|pacman\s+cache)\b", None),
        (r"\bclean\s+(?:up\s+)?(?:old\s+packages?|apt\s+packages?)\b", None),
    ]),

    (IntentType.SYSTEM_JOURNAL_VACUUM, [
        (r"\b(?:vacuum|shrink)\s+(?:up\s+)?(?:the\s+)?(?:systemd\s+)?(?:journal|journalctl|logs?)\b", None),
        (r"\b(?:clean|vacuum|shrink)\s+(?:up\s+)?(?:the\s+)?systemd\s+(?:journal|logs?)\b", None),
        (r"\bjournalctl\s+--vacuum\b", None),
    ]),

    # -----------------------------------------------------------------------
    # Security & Vulnerability Audits
    # -----------------------------------------------------------------------
    (IntentType.SECURITY_AUDIT, [
        (r"\b(?:run\s+|do\s+)?(?:a\s+)?(?:security|vulnerability)\s+(?:audit|check|scan|inspection|overview)\b", None),
        (r"\baudit\s+(?:system\s+)?security\b", None),
        (r"\bhow\s+secure\s+is\s+(?:my\s+|the\s+)?(?:system|server)\b", None),
    ]),

    (IntentType.SECURITY_SSH_CHECK, [
        (r"\b(?:check|audit|inspect)\s+ssh(?:\s+daemon|\s+server|\s+config|\s+security)?\b", None),
        (r"\bssh\s+security\s+(?:check|audit)\b", None),
    ]),

    (IntentType.SECURITY_BRUTEFORCE, [
        (r"\b(?:check|detect|find|show|scan)\s+(?:for\s+)?(?:ssh\s+)?(?:brute\s*force|failed\s+logins?|attackers?|failed\s+ssh(?:\s+attempts)?)(?:\s+attacks?)?\b", None),
        (r"\bwho\s+is\s+trying\s+to\s+(?:hack|bruteforce|login\s+to)\s+my\s+server\b", None),
        (r"\bbrute\s*force\s+(?:check|audit|scan|attacks?)\b", None),
    ]),

    (IntentType.SECURITY_SUID, [
        (r"\b(?:check|audit|find|list|scan)\s+(?:for\s+)?suid(?:\s+binaries|\s+files|\s+permissions)?\b", None),
        (r"\bsuid\s+(?:audit|check|scan|binaries)\b", None),
    ]),

    # -----------------------------------------------------------------------
    # Backup & Restore
    # -----------------------------------------------------------------------
    (IntentType.BACKUP_RESTORE, [
        (r"\brestore\s+(?:backup\s+)?(?P<path>[\w\.\-\/~]+)\s+to\s+(?P<dest>[\w\.\-\/~]+)\b", _extract_backup_args),
    ]),

    (IntentType.BACKUP_LIST, [
        (r"\b(?:list|show|view|get)\s+(?:all\s+|saved\s+|existing\s+)?backups?\b", None),
        (r"\b(?:saved|existing)\s+backups?\b", None),
    ]),

    (IntentType.BACKUP_CREATE, [
        (r"^(?:backup|snapshot|create\s+backup\s+of)\s+(?P<path>[\w\.\-\/~]+)(?:\s+to\s+(?P<dest>[\w\.\-\/~]+))?\b", _extract_backup_args),
        (r"\bcreate\s+(?:a\s+)?(?:backup|snapshot)\s+of\s+(?P<path>[\w\.\-\/~]+)\b", _extract_backup_args),
        (r"\bbackup\s+(?P<path>[\w\.\-\/~]+)(?:\s+configuration|\s+dir|\s+folder)?\b", _extract_backup_args),
    ]),

    # -----------------------------------------------------------------------
    # Storage — FIND_LARGE must come BEFORE ANALYSE so "eating my disk" wins
    # -----------------------------------------------------------------------
    (IntentType.STORAGE_FIND_LARGE, [
        (r"\b(find|show|list) (large|big|huge|fat|heavy) (files?|dirs?|directories?|folders?)\b", None),
        (r"\bwhat(\'s| is) (large|big|taking|eating) (up |)(space|disk|storage|drive)\b", None),
        (r"\bwhat(\'s| is) eating (my |the |)(disk|space|storage|drive)\b", None),
        (r"\blargest files?\b", None),
        (r"\btop (files?|dirs?) by size\b", None),
    ]),

    (IntentType.STORAGE_ANALYSE, [
        (r"\b(disk usage|disk space|storage usage|how much (disk |space |storage )?am i using)\b", None),
        (r"^(df|du)\b", None),          # only match df/du at start-of-input
        (r"\bwhat(\'s| is) using (my |the )?(disk|space|storage)\b", None),  # 'using' only — not 'eating'
        (r"\b(show|check|view) (disk|storage|space|filesystem)\b", None),
        (r"\bhow (full|much) (is |are )?(my |the )?(disk|drives?|partitions?|filesystem)\b", None),
        (r"\b(storage|disk) (overview|summary|info|information|status)\b", None),
    ]),


    (IntentType.STORAGE_CLEAN, [
        (r"\b(clean|cleanup|clear|purge|free) (up |)(old |stale |)?(logs?|tmp|temp|cache|junk|trash|space)\b", None),
        (r"\bfree (up |some |)(disk |)space\b", None),
        (r"\bremove (old |stale |temp |tmp |)files?\b", None),
        (r"\b(delete|remove) (logs?|tmp|temp|cache)\b", None),
    ]),

    (IntentType.STORAGE_ORGANISE, [
        # Full verb forms — "organis" alone won't match "organise ~/Downloads"
        (r"\b(organise|organize|organising|organizing|tidy up?)\b.{0,60}(?P<path>~[\w/\.\-]+|\/[\w/\.\-]+)?", _extract_path),
        (r"\b(sort|arrange|tidy) (up |)(files?|folder|directory|downloads?|pictures?|documents?|desktop)\b", None),
        (r"\bput files? (in |into |)(order|folders?|directories?)\b", None),
        (r"\bsort files? by (type|extension|date|name)\b", None),
        (r"\b(organise|organize) (my |the |)(downloads?|pictures?|documents?|desktop|files?)\b", None),
    ]),

    # -----------------------------------------------------------------------
    # Processes
    # -----------------------------------------------------------------------
    (IntentType.PROCESS_LIST, [
        (r"\b(show|list|view|what|check|display) (processes?|procs?|tasks?|memory|ram|mem|swap)\b", None),
        (r"\b(memory|ram) (usage|status|info|free|summary)\b", None),
        (r"\bhow much (memory|ram) (is |)(used|free|available)\b", None),
        (r"\bwhat(\'s| is) running\b", None),
        (r"^(top|htop|ps|free)$", None),                   # exact command only
        (r"\b(most) (cpu|memory|ram|mem) (using|usage|consuming)\b", None),
        (r"\brunning processes?\b", None),
    ]),

    (IntentType.PROCESS_KILL, [
        (r"\b(kill|stop|terminate|end) (?:process|proc)\s+(?P<name>[\w\-\.]+)?\s*(?P<pid>\d+)?\b", _extract_pid),
        (r"\b(kill|stop|terminate) (?:pid|process|proc)\s+(?P<pid>\d+)\b", _extract_pid),
        (r"\bkill\s+(?P<pid>\d+)\b", _extract_pid),
        (r"\bkill\s+(?P<name>[\w\-\.]+)\b", _extract_pid),
    ]),

    (IntentType.PROCESS_INFO, [
        (r"\binfo (about |on |for )?process (?P<pid>\d+)\b", _extract_pid),
        (r"\bwhat is process (?P<pid>\d+)\b", _extract_pid),
    ]),

    # -----------------------------------------------------------------------
    # Services
    # -----------------------------------------------------------------------
    (IntentType.SERVICE_STATUS, [
        (r"\b(is|check|status of|state of) (?P<svc>[\w\-\.@]+) (running|active|status|up|down|ok)\b", _extract_service),
        (r"\b(?P<svc>[\w\-\.@]+) (service |unit )?(status|state|running\?|active\?|is (running|active|up|down))\b", _extract_service),
        (r"\bcheck (the |)(?P<svc>[\w\-\.@]+) (service|unit|daemon)\b", _extract_service),
        (r"\bstatus (of |)(the |)(?P<svc>[\w\-\.@]+)\b", _extract_service),
    ]),

    (IntentType.SERVICE_START, [
        (r"\bstart (the |)(?P<svc>[\w\-\.@]+)( (service|unit|daemon))?\b", _extract_service),
        (r"\bbring up (?P<svc>[\w\-\.@]+)\b", _extract_service),
    ]),

    (IntentType.SERVICE_STOP, [
        (r"\bstop (the |)(?P<svc>[\w\-\.@]+)( (service|unit|daemon))?\b", _extract_service),
        (r"\bshut down (?P<svc>[\w\-\.@]+)\b", _extract_service),
    ]),

    (IntentType.SERVICE_RESTART, [
        (r"\b(restart|reboot|bounce) (the |)(?P<svc>[\w\-\.@]+)( (service|unit|daemon))?\b", _extract_service),
        (r"\b(restart|reload) (?P<svc>[\w\-\.@]+)\b", _extract_service),
    ]),

    (IntentType.SERVICE_RELOAD, [
        (r"\b(reload|refresh) (the |)(?P<svc>[\w\-\.@]+)\b", _extract_service),
    ]),

    (IntentType.SERVICE_ENABLE, [
        (r"\b(enable|autostart|start.on.boot) (the |)(?P<svc>[\w\-\.@]+)\b", _extract_service),
    ]),

    (IntentType.SERVICE_DISABLE, [
        (r"\b(disable|stop.autostart|remove.from.boot) (the |)(?P<svc>[\w\-\.@]+)\b", _extract_service),
    ]),

    (IntentType.SERVICE_LOGS, [
        (r"\b(show|view|tail|get) (logs?|journal) (for|of|from) (the |)(?P<svc>[\w\-\.@]+)\b", _extract_service),
        (r"\bjournalctl.*-u\s+(?P<svc>[\w\-\.@]+)\b", _extract_service),
        # Only match "<svcname> logs" if svcname is NOT a generic word
        (r"\b(?P<svc>(?!recent|latest|last|old|all|system|kernel|error|any)\w[\w\-\.@]*) (logs?|journal)\b", _extract_service),
    ]),

    # -----------------------------------------------------------------------
    # Packages
    # -----------------------------------------------------------------------
    (IntentType.PACKAGE_INSTALL, [
        (r"\b(install|add) (the )?package (?P<pkg>[\w\-\.\+]+)\b", _extract_package),
        (r"\binstall (?P<pkg>[\w\-\.\+]+)\b", _extract_package),
        (r"\bdownload package (?P<pkg>[\w\-\.\+]+)\b", _extract_package),
        (r"\b(apt|yum|dnf|pacman|apk)\s+(install|add)\s+(?P<pkg>[\w\-\.\+]+)\b", _extract_package),
    ]),

    (IntentType.PACKAGE_REMOVE, [
        (r"\b(remove|uninstall|purge) (the )?package (?P<pkg>[\w\-\.\+]+)\b", _extract_package),
        (r"\b(uninstall|purge) (?P<pkg>[\w\-\.\+]+)\b", _extract_package),
        (r"\b(apt|yum|dnf|pacman|apk)\s+(remove|purge|uninstall)\s+(?P<pkg>[\w\-\.\+]+)\b", _extract_package),
    ]),

    (IntentType.PACKAGE_UPDATE, [
        (r"\b(update|upgrade) (the |all |)packages?\b", None),
        (r"\b(update|upgrade) (the |)system\b", None),
        (r"\b(apt|yum|dnf|pacman|apk)\s+(update|upgrade)\b", None),
        (r"\b(full|system|package) (upgrade|update)\b", None),
    ]),

    (IntentType.PACKAGE_SEARCH, [
        (r"\b(search|find|look for) package (?P<pkg>[\w\-\.\+]+)\b", _extract_package),
        (r"\bis (?P<pkg>[\w\-\.\+]+) (a package|available|installed)\b", _extract_package),
    ]),

    # -----------------------------------------------------------------------
    # Network
    # -----------------------------------------------------------------------
    (IntentType.NETWORK_STATUS, [
        (r"\b(show|list|check) (network|net) (interfaces?|adapters?|cards?|info|status)\b", None),
        (r"\bwhat(\'s| is) my (ip|ip address|network|interface)\b", None),
        (r"\b(ip addr|ifconfig|network info)\b", None),
        (r"\bnetwork (status|overview|info|summary)\b", None),
    ]),

    (IntentType.NETWORK_PORTS, [
        (r"\b(show|list|check|what) (open |listening |)ports?\b", None),
        (r"\bwhat ports? (are |is |)(open|listening|in use)\b", None),
        (r"\b(ss|netstat|lsof)\b", None),
        (r"\blistening (ports?|sockets?|services?)\b", None),
    ]),

    (IntentType.NETWORK_PING, [
        (r"\bping (?P<host>[\w\.\-]+)\b", _extract_host),
        (r"\b(check|test|is) (if |)(?P<host>[\w\.\-]+) (is |)(alive|reachable|up|down|online|responding)\b", _extract_host),
        (r"\bcan (i |we |you )?reach (?P<host>[\w\.\-]+)\b", _extract_host),
    ]),

    (IntentType.NETWORK_DNS, [
        (r"\b(dns|resolve|lookup|nslookup|dig) (?P<host>[\w\.\-]+)\b", _extract_host),
        (r"\bwhat (ip |address )?does (?P<host>[\w\.\-]+) resolve to\b", _extract_host),
    ]),

    (IntentType.NETWORK_ROUTE, [
        (r"\b(show|print|check) (routing? table|routes?|gateways?)\b", None),
        (r"\bdefault gateway\b", None),
    ]),

    # -----------------------------------------------------------------------
    # Files
    # -----------------------------------------------------------------------
    (IntentType.FILE_FIND, [
        (r"\b(find|locate|search for|where is) (file |)(?P<path>[\w\*\.\-\/~]+)\b", _extract_path),
        (r"\bwhere is (the |my |)(?P<path>[\w\*\.\-\/~]+)(?: (file|config|conf))?\b", _extract_path),
    ]),

    (IntentType.FILE_SHOW, [
        (r"\b(show|cat|print|display|view|read) (me |the |file |content of |)(?P<path>[\/~][\w\*\.\-\/~]+)\b", _extract_path),
        (r"\bcat (?P<path>[\w\*\.\-\/~]+)\b", _extract_path),
    ]),

    (IntentType.FILE_EDIT, [
        (r"\b(edit|open|modify|change) (the |file |)(?P<path>[\/~][\w\*\.\-\/~]+)\b", _extract_path),
        (r"\b(edit|open) (the |)(nginx|apache|ssh|cron|fstab|hosts|sudoers) (config|conf|file)?\b", None),
    ]),

    # -----------------------------------------------------------------------
    # Logs
    # -----------------------------------------------------------------------
    (IntentType.LOGS_SHOW, [
        (r"\b(show|tail|view|get|read) (recent |latest |last |)logs?\b", None),
        (r"\brecent logs?\b", None),
        (r"\bjournalctl\b", None),
    ]),

    # LOGS_KERNEL first — more specific than generic errors
    (IntentType.LOGS_KERNEL, [
        (r"\b(kernel|dmesg|klog) (errors?|logs?|messages?|output)\b", None),
        (r"\bdmesg\b", None),
        (r"\bshow kernel\b", None),
    ]),

    (IntentType.LOGS_ERRORS, [
        (r"\b(show|find|list|get) (me |the |)(recent |today\'?s? |latest |)errors?\b", None),
        (r"\b(show|find|list|get) (recent |today\'?s? |latest |)(errors?|failures?)\b", None),
        (r"\b(error|fail|critical|warning) logs?\b", None),
        (r"\bwhat errors? (are there|occurred|happened)\b", None),
        (r"\b(debug|why|what)(\'s| is) (wrong|failing|broken|the (issue|problem|error))\b", None),
        (r"\b(something is|things are) (wrong|failing|broken|not working)\b", None),
        (r"\bany (recent |)(errors?|failures?|problems?|issues?)\b", None),
        # Catch loose "debug" keyword and "errors happening / occurring"
        (r"^debug$", None),
        (r"\bdebug\b.{0,30}(error|issue|problem|fail|crash|wrong)\b", None),
        (r"\b(error|errors?) (happening|occurring|occurred|exist)\b", None),
        (r"\bwhy (are |is )?(there |)(any |)(errors?|failures?|problems?)\b", None),
        # Lookahead: string contains BOTH "debug" AND an error-related word anywhere
        (r"(?=.*\bdebug\b)(?=.*\b(error|fail|wrong|issue|problem|crash)\b).*", None),
        # Broad: (show|get|find|list) … errors? anywhere in sentence
        (r"\b(show|get|find|list|display|give me|tell me).{0,25}errors?\b", None),
    ]),


    # -----------------------------------------------------------------------
    # Cron
    # -----------------------------------------------------------------------
    (IntentType.CRON_LIST, [
        (r"\b(show|list|view|get) (my |all |)(cron(tab)?|scheduled|cron jobs?|tasks?)\b", None),
        (r"\bcrontab\b", None),
        (r"\bscheduled (tasks?|jobs?)\b", None),
    ]),

    (IntentType.CRON_ADD, [
        (r"\b(add|create|schedule|set up) (a |)(cron|crontab|scheduled) (job|task|entry)\b", None),
        (r"\brun .+ every .+\b", None),
        (r"\bschedule .+ at \b", None),
    ]),

    # -----------------------------------------------------------------------
    # Users
    # -----------------------------------------------------------------------
    (IntentType.USER_WHO, [
        (r"\bwho(\'s| is) (logged|connected|online|on|in)\b", None),
        (r"\b(who|w|last) -?\w*\b", None),
        (r"\bcurrently logged in\b", None),
    ]),

    (IntentType.USER_LIST, [
        (r"\b(show|list|get) (all |)users?\b", None),
        (r"\ball (system |local |)users?\b", None),
        (r"\bcat /etc/passwd\b", None),
    ]),

    # -----------------------------------------------------------------------
    # Firewall
    # -----------------------------------------------------------------------
    (IntentType.FIREWALL_STATUS, [
        (r"\b(show|list|check|view) (firewall|ufw|iptables) (rules?|status|config)\b", None),
        (r"\bfirewall (status|rules?|config|overview)\b", None),
        (r"\b(is port|is|check port) (?P<port>\d+) (open|allowed|blocked|filtered)\b", _extract_port),
    ]),

    (IntentType.FIREWALL_ALLOW, [
        (r"\b(allow|open|permit) port (?P<port>\d+)\b", _extract_port),
        (r"\b(allow|open|permit) (?P<port>\d+)/(tcp|udp)\b", _extract_port),
        (r"\badd firewall rule (to |for |)(allow|open|permit) (?P<port>\d+)\b", _extract_port),
    ]),

    (IntentType.FIREWALL_DENY, [
        (r"\b(deny|block|close|drop) port (?P<port>\d+)\b", _extract_port),
        (r"\bblock (?P<port>\d+)/(tcp|udp)\b", _extract_port),
    ]),


    # -----------------------------------------------------------------------
    # Remediation menu actions (used when in remediation context)
    # -----------------------------------------------------------------------
    (IntentType.REMEDIATION_EXEC_ALL, [
        (r"^(a|all|execute all|run all|do all|apply all)$", None),
        (r"\b(execute|run|apply|do) all\b", None),
    ]),

    (IntentType.REMEDIATION_DRY_RUN, [
        (r"^(d|dry.?run|preview|simulate|test)$", None),
        (r"\b(dry.?run|preview|simulate|test|what would|show me what)\b", None),
    ]),

    (IntentType.REMEDIATION_INSPECT, [
        (r"^(i|inspect|ast|safety|check safety|analyse)$", None),
        (r"\b(inspect|ast|safety (check|analysis|breakdown))\b", None),
    ]),

    (IntentType.REMEDIATION_ROLLBACK, [
        (r"^(r|rollback|undo|revert)$", None),
        (r"\b(rollback|undo|revert|go back|undo (that|last|it))\b", None),
    ]),

    (IntentType.REMEDIATION_SKIP, [
        (r"^(s|skip|no|pass|done|next|ignore|cancel|abort)$", None),
        (r"\b(skip|pass|no thanks?|not now|ignore|cancel|abort|never mind)\b", None),
    ]),

    # -----------------------------------------------------------------------
    # History / rollback / export (REPL meta)
    # -----------------------------------------------------------------------
    (IntentType.HISTORY, [
        (r"^history$", None),
        (r"\b(show|view|get|print) history\b", None),
        (r"\bcommand history\b", None),
    ]),

    (IntentType.ROLLBACK, [
        (r"^(rollback|undo)$", None),
    ]),

    (IntentType.EXPORT, [
        (r"^export\b", lambda m: {}),
    ]),

    # -----------------------------------------------------------------------
    # Extended File & Directory Operations
    # -----------------------------------------------------------------------
    (IntentType.FILE_CREATE, [
        (r"\b(create|make|touch) (a )?(new )?file (?P<path>[^\s]+)( with (content|text) (?P<content>.+))?\b", _extract_file_create),
        (r"\bwrite (?P<content>.+) to (file )?(?P<path>[^\s]+)\b", _extract_file_create),
        (r"\becho ['\"]?(?P<content>.+?)['\"]?\s*>\s*(?P<path>[^\s]+)\b", _extract_file_create),
        (r"^touch (?P<path>[^\s]+)$", _extract_file_create),
    ]),

    (IntentType.FILE_DELETE, [
        (r"\b(delete|remove|erase|del) (the )?file (?P<path>[^\s]+)\b", _extract_file_delete),
        (r"^rm (-f )?(?P<path>[^\s]+)$", _extract_file_delete),
    ]),

    (IntentType.FILE_READ, [
        (r"\b(read|view|cat|display|show content(s)? of) (the )?(file )?(?P<path>[^\s]+)\b", _extract_file_delete),
        (r"^cat (?P<path>[^\s]+)$", _extract_file_delete),
        (r"^head( -n \d+)? (?P<path>[^\s]+)$", _extract_file_delete),
        (r"^tail( -n \d+)? (?P<path>[^\s]+)$", _extract_file_delete),
    ]),

    (IntentType.DIR_CREATE, [
        (r"\b(create|make) (a )?(new )?(folder|directory|dir) (?P<path>[^\s]+)\b", _extract_dir_path),
        (r"^mkdir( -p)? (?P<path>[^\s]+)$", _extract_dir_path),
    ]),

    (IntentType.DIR_DELETE, [
        (r"\b(delete|remove|erase|del) (the )?(folder|directory|dir) (?P<path>[^\s]+)\b", _extract_dir_path),
        (r"^rm -rf? (?P<path>[^\s]+)$", _extract_dir_path),
        (r"^rmdir (?P<path>[^\s]+)$", _extract_dir_path),
    ]),

    (IntentType.DIR_LIST, [
        (r"\b(list|show|view) (all )?(files|directories|contents)( in | for | of )?(?P<path>[^\s]+)?\b", _extract_dir_path),
        (r"^ls( -[a-zA-Z]+)?( (?P<path>[^\s]+))?$", _extract_dir_path),
    ]),

    (IntentType.PERM_CHANGE, [
        (r"\bmake (script |file )?(?P<path>[^\s]+) (an )?executable\b", _extract_perm_change),
        (r"\bchmod (?P<mode>[^\s]+) (?P<path>[^\s]+)\b", _extract_perm_change),
        (r"\bchange (permissions?|perms?|mode) (of|on) (?P<path>[^\s]+) to (?P<mode>[^\s]+)\b", _extract_perm_change),
        (r"\bchown (?P<owner>[^\s]+) (?P<path>[^\s]+)\b", _extract_perm_change),
    ]),

    (IntentType.ARCHIVE_CREATE, [
        (r"\b(compress|archive|tar|zip) (?P<src>[^\s]+)( to (?P<dest>[^\s]+))?\b", _extract_archive),
        (r"\bcreate (a )?(tar|zip|tar\.gz|tgz) (archive|file) (?P<dest>[^\s]+) (from|of) (?P<src>[^\s]+)\b", _extract_archive),
    ]),

    (IntentType.ARCHIVE_EXTRACT, [
        (r"\b(unzip|extract|untar|decompress) (?P<src>[^\s]+)( to (?P<dest>[^\s]+))?\b", _extract_archive),
        (r"^tar -x[a-zA-Z]* (?P<src>[^\s]+)$", _extract_archive),
        (r"^unzip (?P<src>[^\s]+)$", _extract_archive),
    ]),

    (IntentType.NETWORK_CURL, [
        (r"\bcurl (?P<url>https?://[^\s]+)\b", _extract_url),
        (r"\b(http|fetch|get) (?P<url>https?://[^\s]+)\b", _extract_url),
    ]),

    (IntentType.SYSTEM_WHOAMI, [
        (r"^whoami$", None),
        (r"\b(what|which) (user|account) am i\b", None),
        (r"\bcurrent (user|username)\b", None),
    ]),

    (IntentType.SYSTEM_ENV, [
        (r"\b(show|list|print|view|get) (environment variables?|env|env vars?)\b", None),
        (r"^(printenv|env)$", None),
    ]),

    # -----------------------------------------------------------------------
    # Fallthrough → diagnostic engine (existing behaviour)
    # -----------------------------------------------------------------------
    (IntentType.DIAGNOSE, [
        (r"\b(why|what|how) (is |are |was |were )?([\w\-]+) (fail|error|crash|down|not work|broken|slow|hang|freeze|block|kill|oom|dead|stop|reject|deny|timeout|spike|leak)\w*\b", None),
        (r"\bdebug\b", None),
        (r"\bdiagnos\w*\b", None),
        (r"\btroubleshoot\b", None),
        (r"\broot.?cause\b", None),
        (r"\bfix\b", None),
        (r"\bwhat(\'s| is) (wrong|broken|the (issue|problem|cause))\b", None),
        (r"\b(investigate|analyse|analyze)\b", None),
    ]),
]


# ---------------------------------------------------------------------------
# Remediation numeric shortcuts
# ---------------------------------------------------------------------------

_NUMERIC_RE = re.compile(r"^\s*(\d+)\s*$")

_COMMON_SHELL_BINARIES = {
    "ls", "cat", "less", "more", "head", "tail", "grep", "egrep", "fgrep", "awk", "sed",
    "touch", "mkdir", "rm", "rmdir", "cp", "mv", "chmod", "chown", "chgrp", "ln",
    "pwd", "cd", "find", "locate", "which", "whereis", "file", "stat", "du", "df", "free",
    "ps", "top", "htop", "kill", "pkill", "killall", "pgrep", "systemctl", "journalctl",
    "service", "dmesg", "uname", "uptime", "hostname", "whoami", "who", "w", "id",
    "ping", "curl", "wget", "traceroute", "netstat", "ss", "ip", "ifconfig", "route",
    "tar", "zip", "unzip", "gzip", "gunzip", "xz", "git", "docker", "podman",
    "apt", "apt-get", "dpkg", "dnf", "yum", "pacman", "apk", "zypper", "rpm",
    "echo", "printf", "date", "cal", "crontab", "sudo", "su", "env", "printenv",
    "lscpu", "lsblk", "lspci", "lsusb", "timedatectl", "localectl", "hostnamectl",
    "xdg-open", "gio", "tree", "diff", "wc", "sort", "uniq", "cut", "tr", "tee"
}


# ---------------------------------------------------------------------------
# IntentRouter
# ---------------------------------------------------------------------------

class IntentRouter:
    """
    Classifies free-form text into structured Intent objects.

    Usage:
        router = IntentRouter()
        intent = router.classify("show me what's eating my disk")
        # → Intent(storage_find_large, args={}, conf=0.95)
    """

    def __init__(self, llm_provider=None):
        """
        Parameters
        ----------
        llm_provider : LLMProvider or None
            Optional LLM backend for ambiguous fallback classification.
        """
        self._llm = llm_provider
        self._compiled: List[Tuple[IntentType, List[Tuple[re.Pattern, Optional]]]] = []
        for intent_type, patterns in _RULES:
            compiled_patterns = [
                (re.compile(pat, re.IGNORECASE | re.DOTALL), extractor)
                for pat, extractor in patterns
            ]
            self._compiled.append((intent_type, compiled_patterns))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, text: str, remediation_context: bool = False) -> Intent:
        """
        Classify *text* and return the best-matching Intent.

        Parameters
        ----------
        text : str
            Raw user input from the REPL, CLI, or Voice Assistant.
        remediation_context : bool
            When True, numeric inputs like "1", "2" are classified as
            REMEDIATION_EXEC_N rather than passed to the diagnostic engine.
        """
        text = text.strip()
        if not text:
            return Intent(IntentType.UNKNOWN, raw=text, confidence=0.0)

        # Strip optional leading shell prompt prefix
        clean_text = re.sub(r"^\$\s*", "", text)

        # Numeric shortcut (remediation menu)
        if remediation_context:
            nm = _NUMERIC_RE.match(text)
            if nm:
                return Intent(
                    IntentType.REMEDIATION_EXEC_N,
                    args={"n": int(nm.group(1))},
                    raw=text,
                    confidence=1.0,
                )

        # Stage 1: deterministic regex pass
        intent = self._regex_classify(clean_text)
        if intent.type != IntentType.UNKNOWN and intent.confidence >= 0.7:
            return intent

        # Stage 1.5: Natural Language Compiler semantic pass
        try:
            from ops_assistant.nlp.nl_compiler import NaturalLanguageCompiler
            nl_compiled = NaturalLanguageCompiler.compile(clean_text)
            if nl_compiled:
                target_intent_type = IntentType(nl_compiled.get("intent", "generic_command"))
                return Intent(
                    target_intent_type,
                    args=nl_compiled,
                    raw=text,
                    confidence=0.98
                )
        except Exception:
            pass

        # Stage 2: LLM fallback (if provider loaded)
        if self._llm is not None:
            llm_intent = self._llm_classify(text)
            if llm_intent is not None:
                return llm_intent

        # Stage 3: Diagnostic query heuristic pass
        if self._looks_diagnostic(clean_text):
            return Intent(IntentType.DIAGNOSE, raw=text, confidence=0.85)

        # Stage 4: Check if clean_text is a direct shell command
        tokens = clean_text.split()
        first_word = tokens[0].lower() if tokens else ""
        if first_word in _COMMON_SHELL_BINARIES or (first_word == "sudo" and len(tokens) > 1 and tokens[1].lower() in _COMMON_SHELL_BINARIES) or any(sym in clean_text for sym in ("|", "&&", ";", ">", ">>")):
            return Intent(
                IntentType.SHELL_RUN,
                args={"command": clean_text},
                raw=text,
                confidence=0.95
            )

        # Stage 5: Synthesize as general natural language Linux command
        return Intent(
            IntentType.GENERIC_COMMAND,
            args={"command": clean_text, "raw_query": text},
            raw=text,
            confidence=0.85
        )

    def classify_remediation_action(self, text: str, n_commands: int) -> Intent:
        """
        Specialised classifier for the remediation menu prompt.
        Accepts numeric indices, letter shortcuts, and NL expressions.
        """
        text = text.strip()

        # Numeric
        nm = _NUMERIC_RE.match(text)
        if nm:
            n = int(nm.group(1))
            if 1 <= n <= n_commands:
                return Intent(IntentType.REMEDIATION_EXEC_N, args={"n": n}, raw=text)
            return Intent(IntentType.UNKNOWN, raw=text, confidence=0.3,
                          args={"hint": f"Enter a number between 1 and {n_commands}"})

        # Classify with remediation context
        return self.classify(text, remediation_context=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _regex_classify(self, text: str) -> Intent:
        best_intent = Intent(IntentType.UNKNOWN, raw=text, confidence=0.0)
        for intent_type, patterns in self._compiled:
            for compiled_pat, extractor in patterns:
                m = compiled_pat.search(text)
                if m:
                    args: Dict[str, Any] = {}
                    if extractor is not None:
                        try:
                            extracted = extractor(m)
                            if extracted:
                                args.update(extracted)
                        except Exception:
                            pass
                    return Intent(
                        type=intent_type,
                        args=args,
                        raw=text,
                        confidence=0.9,
                    )
        return best_intent

    def _llm_classify(self, text: str) -> Optional[Intent]:
        """Ask the LLM to classify ambiguous input. Returns None on failure."""
        intent_names = [t.value for t in IntentType if t not in (
            IntentType.UNKNOWN, IntentType.REMEDIATION_EXEC_N)]
        prompt = (
            "You are a Linux assistant intent classifier. "
            "Given the user input below, return ONLY a JSON object with two fields: "
            "'intent' (one of the values below) and 'args' (dict of extracted arguments or {}).\n"
            f"Valid intents: {', '.join(intent_names)}\n"
            f"User input: \"{text}\"\n"
            "Respond ONLY with valid JSON, no explanation."
        )
        try:
            result = self._llm.generate_diagnosis(text, {"intent_classification": True, "prompt": prompt})
            if result and "intent" in result:
                intent_val = result["intent"]
                args = result.get("args", {})
                for t in IntentType:
                    if t.value == intent_val:
                        return Intent(type=t, args=args, raw=text, confidence=0.75)
        except Exception:
            pass
        return None

    def _looks_diagnostic(self, text: str) -> bool:
        """Heuristic: does this look like a diagnostic query rather than a command?"""
        diagnostic_words = {
            "why", "what", "how", "fail", "crash", "slow", "debug", "diagnos",
            "issue", "problem", "not working", "broken", "down", "died", "killed",
            "high cpu", "high memory", "memory leak", "oom", "timeout",
            "out of memory", "permission denied", "connection refused", "cannot", "unable"
        }
        text_lower = text.lower()
        return any(w in text_lower for w in diagnostic_words)
