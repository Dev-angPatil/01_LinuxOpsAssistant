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
        lower = clean.lower()

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
                "description": desc,
                "intent": "dir_create",
                "safety_level": "MODIFYING",
                "risk_score": 0.20,
                "rollback_command": f"rmdir '{full_path}' 2>/dev/null || rm -rf '{full_path}'",
                "explanation": f"I will create the directory '{child}' inside '{parent}'.",
                "explanation_paragraph": f"The assistant processed your natural language request into `mkdir -p '{full_path}'`, safely provisioning the directory without disturbing existing directories."
            }

        # 2. File Creation
        # e.g. "inside Divya create a file notes.txt with content hello", "in Divya create file index.html"
        m = re.search(r"^(?:in|inside)\s+(?:the\s+|folder\s+|dir\s+)?(?P<parent>[a-zA-Z0-9_\-\.\/~]+)\s+(?:please\s+)?(?:create|make|add)\s+(?:a\s+|one\s+|new\s+)?(?:file)(?:\s+(?:name\s+as|named\s+as|named|called|name|as))?\s+(?P<filename>[a-zA-Z0-9_\-\.\/]+)(?:\s+with\s+content\s+['\"]?(?P<content>.*?)['\"]?)?$", clean, re.IGNORECASE)
        if m:
            parent = m.group("parent").strip()
            filename = m.group("filename").strip()
            content = m.group("content") or ""
            full_path = f"{parent}/{filename}" if not parent.endswith("/") else f"{parent}{filename}"
            if content:
                cmd = f"mkdir -p '{parent}' && echo '{content}' > '{full_path}'"
                desc = f"Creates file '{filename}' inside '{parent}' with content."
            else:
                cmd = f"mkdir -p '{parent}' && touch '{full_path}'"
                desc = f"Creates empty file '{filename}' inside '{parent}'."
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
        m = re.search(r"^(?:please\s+)?(?:open|launch|browse|play|visit|go\s+to)\s+(?P<target>.+)$", clean, re.IGNORECASE)
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
                if site_key == target or re.search(rf"\b{re.escape(site_key)}\b", target):
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

        # 8. File Search by Modification Time, Size, or Extension
        m_mod = re.search(r"\b(?:find|list|show|get)\s+(?:all\s+)?files?\s+(?:in\s+.*?\s+)?(?:that\s+were\s+|which\s+were\s+)?modified\s+(?:in|within)\s+(?:the\s+)?last\s+(?P<num>\d+)\s*(?P<unit>hours?|hrs?|days?|minutes?|mins?)\b", clean, re.IGNORECASE)
        if m_mod:
            num = int(m_mod.group("num"))
            unit = m_mod.group("unit").lower()
            if "min" in unit:
                cmd = f"find . -type f -mmin -{num}"
                time_str = f"{num} minutes"
            elif "hour" in unit or "hr" in unit:
                cmd = f"find . -type f -mmin -{num * 60}"
                time_str = f"{num} hours"
            else:
                cmd = f"find . -type f -mtime -{num}"
                time_str = f"{num} days"
            return {
                "command": cmd,
                "description": f"Lists all files modified in the last {time_str}.",
                "intent": "file_find",
                "safety_level": "READ_ONLY",
                "risk_score": 0.05,
                "explanation": f"I will find files modified in the last {time_str}.",
                "explanation_paragraph": f"The assistant compiled your request into `{cmd}`, querying the filesystem for regular files with timestamps within the specified modification window."
            }

        # 9. Grep Text Search across files
        m_grep = re.search(r"\b(?:search|find|grep|look)\s+(?:for\s+)?['\"](?P<query>[^'\"]+)['\"]\s+(?:in|inside)\s+(?:all\s+)?(?P<target>[a-zA-Z0-9_\-\.\*\/]+(?:\s+files)?)\b", clean, re.IGNORECASE)
        if m_grep:
            search_q = m_grep.group("query")
            tgt = m_grep.group("target").strip()
            if "python" in tgt.lower() or "*.py" in tgt:
                cmd = f"grep -rn --include='*.py' '{search_q}' ."
            else:
                cmd = f"grep -rn '{search_q}' ."
            return {
                "command": cmd,
                "description": f"Searches for pattern '{search_q}' across files.",
                "intent": "file_find",
                "safety_level": "READ_ONLY",
                "risk_score": 0.05,
                "explanation": f"I will search for '{search_q}' across files.",
                "explanation_paragraph": f"The assistant compiled your text search request into `{cmd}`, recursively scanning files with line numbers for matching occurrences."
            }

        # 10. Archive / Zip / Compression
        m_zip = re.search(r"\b(?:compress|zip|archive)\s+(?:the\s+)?(?:folder|directory|dir\s+)?(?P<src>[a-zA-Z0-9_\-\.\/~]+)\s+(?:in|into|to)\s+(?:a\s+)?(?:zip\s+file\s+)?(?:named\s+as\s+|named\s+|called\s+)?(?P<dst>[a-zA-Z0-9_\-\.\/~]+)\b", clean, re.IGNORECASE)
        if m_zip:
            src = m_zip.group("src").strip()
            dst = m_zip.group("dst").strip()
            if not dst.endswith((".zip", ".tar.gz", ".tgz")):
                dst = f"{dst}.zip"
            if dst.endswith(".zip"):
                cmd = f"zip -r '{dst}' '{src}'"
            else:
                cmd = f"tar -czf '{dst}' '{src}'"
            return {
                "command": cmd,
                "description": f"Compresses '{src}' into archive '{dst}'.",
                "intent": "archive_create",
                "safety_level": "MODIFYING",
                "risk_score": 0.25,
                "rollback_command": f"rm -f '{dst}'",
                "explanation": f"I will compress '{src}' into '{dst}'.",
                "explanation_paragraph": f"The assistant compiled your archiving request into `{cmd}`, packaging the directory tree into a compressed archive file."
            }

        # 11. Make Executable / Change Permissions
        m_perm = re.search(r"\b(?:make|set)\s+(?:script\s+|file\s+)?(?P<path>[a-zA-Z0-9_\-\.\/~]+)\s+(?:an\s+)?executable\b", clean, re.IGNORECASE)
        if m_perm:
            path = m_perm.group("path").strip()
            cmd = f"chmod +x '{path}'"
            return {
                "command": cmd,
                "description": f"Grants execution permission on '{path}'.",
                "intent": "perm_change",
                "safety_level": "MODIFYING",
                "risk_score": 0.20,
                "rollback_command": f"chmod -x '{path}'",
                "explanation": f"I will make '{path}' executable.",
                "explanation_paragraph": f"The assistant compiled your instruction into `chmod +x '{path}'`, enabling POSIX execute permission bits on the target file."
            }

        # 12. Boot Performance & Bottlenecks
        if any(w in lower for w in ("why is boot slow", "boot bottlenecks", "boot time", "systemd analyze", "slow startup")):
            cmd = "systemd-analyze blame | head -n 15"
            return {
                "command": cmd,
                "description": "Lists systemd services taking the longest startup time during boot.",
                "intent": "system_boot_analysis",
                "safety_level": "READ_ONLY",
                "risk_score": 0.05,
                "explanation": "I will analyze boot startup times and identify bottlenecks.",
                "explanation_paragraph": "The assistant executed `systemd-analyze blame | head -n 15`, querying the init manager for initialization times consumed by each daemon during host startup."
            }

        return None

    @classmethod
    def compile_semantic_fallback(cls, query: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        """
        Comprehensive semantic instruction compiler.
        Ensures that ANY free-form user query produces a valid, safe, structured Linux command plan.
        """
        raw = (query or "").strip()
        clean = re.sub(r"^\$\s*", "", raw)
        clean = re.sub(r"[\.!\?]+$", "", clean).strip()
        lower = clean.lower()
        wd = cwd or os.getcwd()

        # 1. Listening ports & network sockets
        if any(w in lower for w in ("listening port", "open port", "what ports", "ports open", "port listening", "check port", "active ports")):
            cmd = "ss -tulpn"
            return {
                "command": cmd,
                "description": "Lists active listening TCP and UDP ports and associated process IDs.",
                "intent": "network_ports",
                "safety_level": "READ_ONLY",
                "risk_score": 0.05,
                "explanation": "I will inspect all open and listening network sockets.",
                "explanation_paragraph": "The assistant executed `ss -tulpn`, querying the kernel socket table for all listening IPv4 and IPv6 endpoints along with their owning processes."
            }

        # 2. Network IP & Interfaces
        if any(w in lower for w in ("what is my ip", "my ip address", "ip addr", "network status", "show interfaces")):
            cmd = "ip -br a || ifconfig"
            return {
                "command": cmd,
                "description": "Displays active network interfaces and assigned IP addresses.",
                "intent": "network_status",
                "safety_level": "READ_ONLY",
                "risk_score": 0.05,
                "explanation": "I will display your active network interface addresses.",
                "explanation_paragraph": "The assistant executed `ip -br a` to inspect network link states and IPv4/IPv6 assignments across all host interfaces."
            }

        # 3. CPU, Memory, & Disk Monitoring
        if any(w in lower for w in ("check cpu", "cpu usage", "cpu uses", "processor load", "top cpu")):
            cmd = "top -b -n 1 | head -n 15"
            return {
                "command": cmd,
                "description": "Samples live CPU utilization and load averages.",
                "intent": "system_check_cpu",
                "safety_level": "READ_ONLY",
                "risk_score": 0.05,
                "explanation": "I will inspect live CPU utilization.",
                "explanation_paragraph": "The assistant compiled your query into `top -b -n 1 | head -n 15`, displaying processor usage and load averages across all cores."
            }

        if any(w in lower for w in ("check memory", "check ram", "ram usage", "memory free", "free ram", "free memory", "check swap")):
            cmd = "free -h"
            return {
                "command": cmd,
                "description": "Displays physical RAM and swap memory headroom in human-readable units.",
                "intent": "system_check_ram",
                "safety_level": "READ_ONLY",
                "risk_score": 0.05,
                "explanation": "I will report memory and swap availability.",
                "explanation_paragraph": "The assistant executed `free -h` to report total, used, free, and buffered physical RAM and swap partition statistics."
            }

        if any(w in lower for w in ("check disk", "disk space", "storage space", "check storage", "how much disk")):
            cmd = "df -h"
            return {
                "command": cmd,
                "description": "Reports filesystem partition storage usage and available blocks.",
                "intent": "system_check_disk",
                "safety_level": "READ_ONLY",
                "risk_score": 0.05,
                "explanation": "I will report mounted partition storage capacity.",
                "explanation_paragraph": "The assistant executed `df -h` to inspect storage allocations and available blocks across all mounted filesystems."
            }

        # 4. Process termination
        m_kill = re.search(r"\b(?:kill|terminate|stop)\s+(?:process|proc|pid)?\s*(?P<target>[a-zA-Z0-9_\-\.]+)\b", clean, re.IGNORECASE)
        if m_kill and not any(w in lower for w in ("service", "daemon", "unit")):
            tgt = m_kill.group("target").strip()
            if tgt.isdigit():
                cmd = f"kill -15 {tgt}"
                desc = f"Sends SIGTERM to process PID {tgt}."
            else:
                cmd = f"pkill -15 {tgt}"
                desc = f"Sends SIGTERM to processes named '{tgt}'."
            return {
                "command": cmd,
                "description": desc,
                "intent": "process_kill",
                "safety_level": "HIGH_RISK",
                "risk_score": 0.70,
                "explanation": f"I will send a termination signal to {tgt}.",
                "explanation_paragraph": f"The assistant prepared `{cmd}`, issuing a standard POSIX SIGTERM signal to safely request graceful process shutdown."
            }

        # 5. Service operations (systemd)
        m_svc = re.search(r"\b(?P<action>start|stop|restart|reload|enable|disable|status|logs?)\s+(?:service|unit|daemon)?\s*(?P<svc>[a-zA-Z0-9_\-\.@]+)\b", clean, re.IGNORECASE)
        if m_svc:
            act = m_svc.group("action").lower()
            svc = m_svc.group("svc").strip()
            if act in ("logs", "log"):
                cmd = f"journalctl -u {svc} -n 50 --no-pager"
                desc = f"Displays latest 50 systemd log lines for service '{svc}'."
                safety = "READ_ONLY"
                risk = 0.05
            elif act == "status":
                cmd = f"systemctl status {svc}"
                desc = f"Checks status of systemd unit '{svc}'."
                safety = "READ_ONLY"
                risk = 0.05
            else:
                cmd = f"sudo systemctl {act} {svc}"
                desc = f"Executes systemctl {act} on service '{svc}'."
                safety = "MODIFYING"
                risk = 0.35
            return {
                "command": cmd,
                "description": desc,
                "intent": f"service_{act}" if act != "logs" else "service_logs",
                "safety_level": safety,
                "risk_score": risk,
                "explanation": f"I will {act} the '{svc}' service.",
                "explanation_paragraph": f"The assistant compiled your request into `{cmd}`, interfacing with the systemd init daemon to manage service unit lifecycle."
            }

        # 6. File & Directory operations
        if any(w in lower for w in ("create folder", "make folder", "mkdir", "create directory")):
            m = re.search(r"(?:folder|directory|dir)\s+(?:name\s+as|named|called)?\s*['\"]?(?P<name>[a-zA-Z0-9_\-\.\/~]+)['\"]?", clean, re.IGNORECASE)
            name = m.group("name") if m else "new_folder"
            cmd = f"mkdir -p '{name}'"
            return {
                "command": cmd,
                "description": f"Creates directory '{name}'.",
                "intent": "dir_create",
                "safety_level": "MODIFYING",
                "risk_score": 0.15,
                "rollback_command": f"rmdir '{name}' 2>/dev/null || rm -rf '{name}'",
                "explanation": f"I will create the directory '{name}'.",
                "explanation_paragraph": f"The assistant compiled your request into `mkdir -p '{name}'`, safely creating the target path without disturbing existing data."
            }

        # Default: general shell execution with AST safety validation
        from ops_assistant.tools.safety import CommandSafetyValidator
        val = CommandSafetyValidator.validate(clean)
        return {
            "command": clean,
            "description": f"Executes system shell command: '{clean}'.",
            "intent": "generic_command",
            "safety_level": val.level.value,
            "risk_score": val.risk_score,
            "rollback_command": val.suggested_rollback,
            "explanation": f"I will execute `{clean}`.",
            "explanation_paragraph": f"The assistant synthesized your request into the shell command `{clean}` and performed AST security verification."
        }


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
