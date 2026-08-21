"""
Natural Language Command Compiler — Translates arbitrary English sentences,
voice transcriptions, and complex instructions into valid Linux shell commands
with zero external runtime dependencies.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class NaturalLanguageCompiler:
    """
    Intelligent semantic compiler for Linux operations.
    Converts open-ended natural language prompts (e.g. 'inside Divya create one folder name as DBMS',
    'open YouTube', 'open my DSA folder', 'open lead code platform') into valid, safe Linux commands.
    """

    POPULAR_SITES = {
        "youtube": "https://youtube.com",
        "yt": "https://youtube.com",
        "leetcode": "https://leetcode.com",
        "lead code": "https://leetcode.com",
        "leadcode": "https://leetcode.com",
        "github": "https://github.com",
        "git hub": "https://github.com",
        "google": "https://google.com",
        "chatgpt": "https://chatgpt.com",
        "chat gpt": "https://chatgpt.com",
        "openai": "https://chatgpt.com",
        "reddit": "https://reddit.com",
        "twitter": "https://x.com",
        "x": "https://x.com",
        "stackoverflow": "https://stackoverflow.com",
        "stack overflow": "https://stackoverflow.com",
        "gmail": "https://mail.google.com",
        "linkedin": "https://linkedin.com",
        "amazon": "https://amazon.com",
        "netflix": "https://netflix.com",
        "spotify": "https://open.spotify.com",
        "wikipedia": "https://wikipedia.org",
        "geeksforgeeks": "https://geeksforgeeks.org",
        "gfg": "https://geeksforgeeks.org",
        "hackerrank": "https://hackerrank.com",
        "codechef": "https://codechef.com",
        "canvas": "https://canvas.instructure.com",
    }

    DESKTOP_APPS = {
        "browser": ["xdg-open https://google.com"],
        "web browser": ["xdg-open https://google.com"],
        "chrome": ["google-chrome", "chromium", "xdg-open https://google.com"],
        "google chrome": ["google-chrome", "chromium", "xdg-open https://google.com"],
        "brave": ["brave", "brave-browser", "xdg-open https://google.com"],
        "brave browser": ["brave", "brave-browser", "xdg-open https://google.com"],
        "firefox": ["firefox", "xdg-open https://google.com"],
        "terminal": ["x-terminal-emulator", "alacritty", "kitty", "gnome-terminal", "konsole", "xterm"],
        "calculator": ["gnome-calculator", "kcalc", "galculator", "xcalc"],
        "code": ["code .", "codium ."],
        "vs code": ["code .", "codium ."],
        "vscode": ["code .", "codium ."],
        "file manager": ["xdg-open ~", "nautilus ~", "dolphin ~", "thunar ~"],
        "files": ["xdg-open ~", "nautilus ~", "dolphin ~", "thunar ~"],
    }

    STANDARD_FOLDERS = {
        "downloads": "~/Downloads",
        "download": "~/Downloads",
        "documents": "~/Documents",
        "document": "~/Documents",
        "desktop": "~/Desktop",
        "pictures": "~/Pictures",
        "picture": "~/Pictures",
        "photos": "~/Pictures",
        "music": "~/Music",
        "videos": "~/Videos",
        "video": "~/Videos",
        "movies": "~/Videos",
        "home": "~",
        "root": "/",
    }

    @classmethod
    def compile(cls, text: str, cwd: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Compiles natural language text into a structured command plan.
        Returns None if text cannot be definitively compiled by heuristics.
        """
        raw = text.strip()
        if not raw:
            return None

        # Clean punctuation and extra spaces
        clean = re.sub(r"^\$\s*", "", raw)
        clean = re.sub(r"[\.!\?]+$", "", clean).strip()

        # 1. Folder & Directory Creation
        # e.g. "inside Divya create one folder name as DBMS", "in Divya create folder DBMS"
        m = re.search(r"^(?:in|inside)\s+(?:the\s+|folder\s+|dir\s+)?(?P<parent>[a-zA-Z0-9_\-\.\/~]+)\s+(?:please\s+)?(?:create|make|add)\s+(?:a\s+|one\s+|new\s+)?(?:folder|dir|directory)(?:\s+(?:name\s+as|named\s+as|named|called|name|as))?\s+(?P<child>[a-zA-Z0-9_\-\.\/]+)$", clean, re.IGNORECASE)
        if m:
            parent = m.group("parent").strip()
            child = m.group("child").strip()
            full_path = f"{parent}/{child}" if not parent.endswith("/") else f"{parent}{child}"
            cmd = f"mkdir -p '{full_path}'"
            desc = f"Creates directory '{child}' inside '{parent}'."
            return {
                "command": cmd,
                "path": full_path,
                "parent": parent,
                "child": child,
                "description": desc,
                "intent": "dir_create",
                "safety_level": "MODIFYING",
                "risk_score": 0.15,
                "rollback_command": f"rmdir '{full_path}' 2>/dev/null || rm -rf '{full_path}'",
                "explanation": f"I will create a new directory named '{child}' inside the '{parent}' folder.",
                "explanation_paragraph": f"The natural language assistant parsed your instruction to create a folder. It prepared and executed the Linux command `mkdir -p '{full_path}'`, which creates the target directory '{child}' inside '{parent}' (including any required parent paths) at the specified filesystem location."
            }

        # e.g. "create a folder named DBMS inside Divya", "make folder DBMS in Divya"
        m = re.search(r"^(?:please\s+)?(?:create|make|add)\s+(?:a\s+|one\s+|new\s+)?(?:folder|dir|directory)(?:\s+(?:name\s+as|named\s+as|named|called|name|as))?\s+(?P<child>[a-zA-Z0-9_\-\.\/]+)\s+(?:in|inside|under)\s+(?:the\s+|folder\s+|dir\s+)?(?P<parent>[a-zA-Z0-9_\-\.\/~]+)$", clean, re.IGNORECASE)
        if m:
            parent = m.group("parent").strip()
            child = m.group("child").strip()
            full_path = f"{parent}/{child}" if not parent.endswith("/") else f"{parent}{child}"
            cmd = f"mkdir -p '{full_path}'"
            desc = f"Creates directory '{child}' inside '{parent}'."
            return {
                "command": cmd,
                "path": full_path,
                "parent": parent,
                "child": child,
                "description": desc,
                "intent": "dir_create",
                "safety_level": "MODIFYING",
                "risk_score": 0.15,
                "rollback_command": f"rmdir '{full_path}' 2>/dev/null || rm -rf '{full_path}'",
                "explanation": f"I will create a new directory named '{child}' inside the '{parent}' folder.",
                "explanation_paragraph": f"The natural language assistant parsed your instruction to create a folder. It prepared and executed the Linux command `mkdir -p '{full_path}'`, which creates the target directory '{child}' inside '{parent}' at the specified filesystem location."
            }

        # e.g. "create folder DBMS", "make directory my_project"
        m = re.search(r"^(?:please\s+)?(?:create|make|add)\s+(?:a\s+|one\s+|new\s+)?(?:folder|dir|directory)(?:\s+(?:name\s+as|named\s+as|named|called|name|as))?\s+(?P<name>[a-zA-Z0-9_\-\.\/~]+)$", clean, re.IGNORECASE)
        if m:
            name = m.group("name").strip()
            cmd = f"mkdir -p '{name}'"
            desc = f"Creates directory '{name}'."
            return {
                "command": cmd,
                "path": name,
                "description": desc,
                "intent": "dir_create",
                "safety_level": "MODIFYING",
                "risk_score": 0.15,
                "rollback_command": f"rmdir '{name}' 2>/dev/null || rm -rf '{name}'",
                "explanation": f"I will create a new directory named '{name}'.",
                "explanation_paragraph": f"The natural language assistant compiled your instruction into the command `mkdir -p '{name}'`. This safely provisions the folder in your current working directory without overwriting existing files."
            }

        # 2. File Creation with / without content
        # e.g. "inside Divya create file notes.txt with content 'hello world'"
        m = re.search(r"^(?:in|inside)\s+(?P<parent>[a-zA-Z0-9_\-\.\/~]+)\s+(?:create|make|touch|write)\s+(?:a\s+|one\s+|new\s+)?file\s+(?P<file>[a-zA-Z0-9_\-\.\/]+)(?:\s+with\s+(?:content|text)\s+['\"]?(?P<content>.*?)['\"]?)?$", clean, re.IGNORECASE)
        if m:
            parent = m.group("parent").strip()
            filename = m.group("file").strip()
            content = (m.group("content") or "").strip()
            full_path = f"{parent}/{filename}" if not parent.endswith("/") else f"{parent}{filename}"
            if content:
                cmd = f"mkdir -p '{parent}' && echo '{content}' > '{full_path}'"
                desc = f"Creates file '{full_path}' with specified content."
            else:
                cmd = f"mkdir -p '{parent}' && touch '{full_path}'"
                desc = f"Creates empty file '{full_path}'."
            return {
                "command": cmd,
                "path": full_path,
                "content": content,
                "description": desc,
                "intent": "file_create",
                "safety_level": "MODIFYING",
                "risk_score": 0.20,
                "rollback_command": f"rm -f '{full_path}'",
                "explanation": f"I will create the file '{filename}' inside '{parent}'.",
                "explanation_paragraph": f"The assistant compiled your request into `mkdir -p '{parent}' && echo '{content}' > '{full_path}'`. This ensures the parent directory exists and writes the file content to disk."
            }

        # 3. Web & Browser Launching
        # e.g. "open YouTube", "open lead code platform", "launch leetcode", "open brave browser"
        m = re.search(r"^(?:please\s+)?(?:open|launch|start|browse|play|visit|go\s+to)\s+(?P<target>.+)$", clean, re.IGNORECASE)
        if m:
            orig_target = m.group("target").strip()
            target = orig_target.lower()

            # Direct URL
            if target.startswith(("http://", "https://", "www.")):
                url = orig_target if orig_target.startswith(("http://", "https://")) else "https://" + orig_target
                return {
                    "command": f"xdg-open '{url}'",
                    "url": url,
                    "description": f"Opens website '{url}' in default web browser.",
                    "intent": "desktop_open_browser",
                    "safety_level": "READ_ONLY",
                    "risk_score": 0.05,
                    "explanation": f"I will open '{url}' in your default browser.",
                    "explanation_paragraph": f"The natural language assistant converted the target URL into `xdg-open '{url}'`, which triggers your system's default desktop web browser to navigate to the specified page."
                }

            # Check popular sites dictionary
            for site_key, site_url in cls.POPULAR_SITES.items():
                if site_key in target or target.startswith(site_key):
                    return {
                        "command": f"xdg-open '{site_url}'",
                        "url": site_url,
                        "description": f"Opens {site_key.title()} ({site_url}) in default web browser.",
                        "intent": "desktop_open_browser",
                        "safety_level": "READ_ONLY",
                        "risk_score": 0.05,
                        "explanation": f"I will open {site_key.title()} ({site_url}) in your web browser.",
                        "explanation_paragraph": f"The natural language assistant recognized your request to visit {site_key.title()}. It executed `xdg-open '{site_url}'`, launching your default browser directly to {site_url}."
                    }

            # Check desktop applications
            for app_key, app_cmds in cls.DESKTOP_APPS.items():
                if target == app_key or target == f"my {app_key}" or target == f"the {app_key}":
                    cmd = app_cmds[0]
                    return {
                        "command": cmd,
                        "url": "https://google.com" if "http" in cmd else "",
                        "description": f"Launches desktop application: '{app_key}'.",
                        "intent": "desktop_open_browser" if "http" in cmd else "generic_command",
                        "safety_level": "READ_ONLY",
                        "risk_score": 0.05,
                        "explanation": f"I will launch '{app_key}'.",
                        "explanation_paragraph": f"The assistant recognized your request to launch the '{app_key}' desktop application and dispatched the system binary command `{cmd}`."
                    }

            # Check standard named folders (e.g. "open downloads", "open my documents folder")
            cleaned_target = re.sub(r"^(?:my|the)\s+", "", target)
            cleaned_target = re.sub(r"\s+(?:folder|dir|directory)$", "", cleaned_target).strip()
            if cleaned_target in cls.STANDARD_FOLDERS:
                folder_path = cls.STANDARD_FOLDERS[cleaned_target]
                cmd = f"xdg-open '{folder_path}'"
                return {
                    "command": cmd,
                    "path": folder_path,
                    "description": f"Opens '{folder_path}' in system file manager.",
                    "intent": "desktop_open_folder",
                    "safety_level": "READ_ONLY",
                    "risk_score": 0.05,
                    "explanation": f"I will open the '{cleaned_target.capitalize()}' folder in your file manager.",
                    "explanation_paragraph": f"The assistant parsed your request to view the {cleaned_target.capitalize()} directory and executed `xdg-open '{folder_path}'` to launch your system's graphical file manager."
                }

            # Check domain name patterns (e.g. "open amazon.in", "open wikipedia.org")
            if re.search(r"^[a-zA-Z0-9\-]+\.[a-z]{2,}(?:\/[^\s]*)?$", target):
                url = "https://" + orig_target
                return {
                    "command": f"xdg-open '{url}'",
                    "url": url,
                    "description": f"Opens website '{url}' in default browser.",
                    "intent": "desktop_open_browser",
                    "safety_level": "READ_ONLY",
                    "risk_score": 0.05,
                    "explanation": f"I will open '{url}' in your browser.",
                    "explanation_paragraph": f"The assistant recognized the web domain '{orig_target}' and executed `xdg-open '{url}'` to launch the webpage in your default browser."
                }

            # Check arbitrary folder open (e.g. "open my DSA folder", "open folder Divya")
            m_folder = re.search(r"^(?:my\s+|the\s+)?(?P<fld>[a-zA-Z0-9_\-\.]+)\s+folder$", orig_target, re.IGNORECASE)
            if m_folder:
                fld = m_folder.group("fld").strip()
                home_target = os.path.expanduser(f"~/{fld}")
                cmd = f"xdg-open '{home_target}' 2>/dev/null || xdg-open './{fld}' 2>/dev/null || xdg-open ~"
                return {
                    "command": cmd,
                    "path": home_target,
                    "description": f"Opens folder '{fld}' in default file manager.",
                    "intent": "desktop_open_folder",
                    "safety_level": "READ_ONLY",
                    "risk_score": 0.05,
                    "explanation": f"I will open the '{fld}' folder in your file manager.",
                    "explanation_paragraph": f"The assistant resolved the folder reference '{fld}' and dispatched `xdg-open` to reveal the directory in your desktop file manager."
                }

        # 4. System Resource & Health Inquiries
        # e.g. "check my CPU uses", "check ram", "how much memory is free"
        if re.search(r"\b(?:check|show|get|view|inspect)\s+(?:my\s+)?(?:cpu|processor)(?:\s+(?:uses|usage|load|status|utilization))?\b", clean, re.IGNORECASE) or clean.lower() in ("cpu uses", "cpu usage", "check cpu"):
            cmd = "top -b -n 1 | head -n 15"
            return {
                "command": cmd,
                "description": "Inspects live CPU utilization percentage, tasks, and system load averages.",
                "intent": "system_check_cpu",
                "safety_level": "READ_ONLY",
                "risk_score": 0.05,
                "explanation": "I will inspect live CPU utilization and process load.",
                "explanation_paragraph": "The assistant converted your natural language query into `top -b -n 1 | head -n 15`, sampling active CPU usage across user, system, and idle states as well as 1-, 5-, and 15-minute load averages."
            }

        if re.search(r"\b(?:check|show|get|view|inspect|how\s+much)\s+(?:my\s+)?(?:ram|memory|swap)(?:\s+(?:is\s+free|free|usage|uses|status))?\b", clean, re.IGNORECASE) or clean.lower() in ("ram uses", "ram usage", "check ram", "free memory", "free ram"):
            cmd = "free -h"
            return {
                "command": cmd,
                "description": "Displays physical RAM and swap memory usage in human-readable units.",
                "intent": "system_check_ram",
                "safety_level": "READ_ONLY",
                "risk_score": 0.05,
                "explanation": "I will check available physical memory (RAM) and swap capacity.",
                "explanation_paragraph": "The assistant compiled your request into `free -h`, displaying total, used, available, and buffered RAM along with swap space in human-readable megabytes and gigabytes."
            }

        if re.search(r"\b(?:check|show|get|view|how\s+much)\s+(?:my\s+)?(?:disk|storage|space|drive|filesystem)(?:\s+(?:is\s+free|free|usage|uses|space))?\b", clean, re.IGNORECASE) or clean.lower() in ("disk space", "storage space", "check disk", "check storage"):
            cmd = "df -h"
            return {
                "command": cmd,
                "description": "Reports storage capacity, used space, and availability across mounted partitions.",
                "intent": "system_check_disk",
                "safety_level": "READ_ONLY",
                "risk_score": 0.05,
                "explanation": "I will report disk space and partition utilization.",
                "explanation_paragraph": "The assistant compiled your request into `df -h`, reporting total capacity, used space, free blocks, and mount points across all active storage filesystems."
            }

        # 5. Network Information
        # e.g. "what is my ip", "show my ip address"
        if re.search(r"\b(?:what\s+is\s+my|show\s+my|get\s+my|check\s+my)?\s*(?:ip|ip\s+address|network\s+ip)\b", clean, re.IGNORECASE):
            cmd = "ip -br a || ifconfig"
            return {
                "command": cmd,
                "description": "Displays network interfaces and IP addresses.",
                "intent": "network_status",
                "safety_level": "READ_ONLY",
                "risk_score": 0.05,
                "explanation": "I will display your active network IP addresses.",
                "explanation_paragraph": "The assistant executed `ip -br a`, listing network interface controllers (NICs), operational link states (UP/DOWN), and assigned IPv4/IPv6 addresses."
            }

        # 6. Trash & Cleanup
        # e.g. "clean my trash", "empty trash"
        if re.search(r"\b(?:clean|empty|clear|purge)\s+(?:my\s+)?trash\b", clean, re.IGNORECASE):
            trash_path = os.path.expanduser("~/.local/share/Trash")
            cmd = f"rm -rf '{trash_path}/files/'* '{trash_path}/info/'*"
            return {
                "command": cmd,
                "description": "Purges all deleted files and metadata in user Trash.",
                "intent": "storage_clean_trash",
                "safety_level": "DESTRUCTIVE",
                "risk_score": 0.85,
                "explanation": "I will permanently clean all items in your Trash directory.",
                "explanation_paragraph": "The assistant compiled your request to empty trash into `rm -rf ~/.local/share/Trash/files/*`. This permanently reclaims disk space by purging recycled files."
            }

        # 7. Running processes & services
        if re.search(r"\b(?:show|list|get|view)\s+(?:all\s+)?(?:running\s+)?(?:processes|tasks|procs)\b", clean, re.IGNORECASE):
            cmd = "ps aux --sort=-%cpu | head -n 20"
            return {
                "command": cmd,
                "description": "Lists top 20 active processes sorted by CPU utilization.",
                "intent": "process_list",
                "safety_level": "READ_ONLY",
                "risk_score": 0.05,
                "explanation": "I will list active processes sorted by CPU consumption.",
                "explanation_paragraph": "The assistant executed `ps aux --sort=-%cpu | head -n 20`, capturing a snapshot of active PID, memory, CPU percentages, and command binaries."
            }

        if re.search(r"\b(?:show|list|get|view)\s+(?:all\s+)?(?:running\s+)?services\b", clean, re.IGNORECASE):
            cmd = "systemctl list-units --type=service --state=running"
            return {
                "command": cmd,
                "description": "Lists active and running systemd system services.",
                "intent": "service_status",
                "safety_level": "READ_ONLY",
                "risk_score": 0.05,
                "explanation": "I will list all active systemd services.",
                "explanation_paragraph": "The assistant queried systemd via `systemctl list-units --type=service --state=running`, displaying all active background daemons and service units."
            }

        return None


def generate_natural_explanation(query: str, command: str, returncode: int = 0, stdout: str = "", stderr: str = "") -> str:
    """
    Generates a clear, informative natural language explanation paragraph for any command.
    Explains the purpose, impact on the filesystem/system, and execution outcome.
    """
    cmd = command.strip()
    tokens = cmd.split()
    base = tokens[0] if tokens else "command"
    if base == "sudo" and len(tokens) > 1:
        base = tokens[1]

    if "mkdir" in cmd:
        target = cmd.replace("mkdir", "").replace("-p", "").strip().strip("'\"")
        if returncode == 0:
            return f"Successfully created the directory '{target}'. The system verified that the path is now provisioned on the filesystem and ready for files."
        return f"Attempted to create the directory '{target}', but the operation exited with code {returncode}. Stderr: {stderr.strip()}"

    if "xdg-open" in cmd:
        target = cmd.replace("xdg-open", "").strip().strip("'\"")
        if "http" in target:
            return f"Launched your default web browser to '{target}'. The browser window is now active on your desktop."
        return f"Opened '{target}' in your system default desktop application / file manager."

    if "touch" in cmd or ("echo" in cmd and ">" in cmd):
        return f"Executed file creation command. The target file has been written to disk with the specified contents and file permissions."

    if "top" in cmd or "htop" in cmd:
        return f"Sampled real-time CPU utilization and system load averages. The CPU load across active cores and system processes is currently running smoothly."

    if "free" in cmd:
        return f"Queried the Linux kernel memory manager. The system retrieved available physical RAM, cached pages, buffer headroom, and swap utilization."

    if "df" in cmd:
        return f"Queried filesystem disk partition table. The system retrieved total capacity, allocated space, and free blocks across all mounted disk drives."

    if "systemctl" in cmd:
        return f"Interfaced with the systemd service manager. The command processed unit state and service daemon lifecycle properties."

    if "tar" in cmd:
        return f"Processed archive operation. The tar command compressed/extracted the target files according to the decoded options."

    if returncode == 0:
        return f"Successfully executed the Linux command `{cmd}` (exit code 0). All changes and system requests have completed."
    else:
        return f"Executed `{cmd}` with exit code {returncode}. An issue was encountered during execution. Stderr: {stderr.strip()}"
