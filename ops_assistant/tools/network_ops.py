"""
Network Operations — interface status, listening ports, ping, DNS, routing,
and firewall management (ufw/iptables-aware).
"""

from __future__ import annotations

import subprocess
from typing import Any, Dict, List, Optional, Tuple


def _run(cmd: List[str], timeout: int = 10) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"Timed out after {timeout}s"


# ---------------------------------------------------------------------------
# Network status / interfaces
# ---------------------------------------------------------------------------

def show_interfaces() -> Dict[str, Any]:
    """Return network interface info using `ip addr show`."""
    rc, stdout, stderr = _run(["ip", "-br", "addr", "show"])
    if rc != 0:
        # Fallback to ip addr
        rc, stdout, stderr = _run(["ip", "addr", "show"])

    interfaces: List[Dict[str, str]] = []
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and not line.startswith(" "):
            interfaces.append({
                "interface": parts[0],
                "state": parts[1] if len(parts) > 1 else "",
                "addresses": " ".join(parts[2:]) if len(parts) > 2 else "",
            })

    # Also grab default gateway
    _, gw_out, _ = _run(["ip", "route", "show", "default"])
    gateway = ""
    for line in gw_out.splitlines():
        if line.startswith("default"):
            parts = line.split()
            if "via" in parts:
                gateway = parts[parts.index("via") + 1]
            break

    return {
        "interfaces": interfaces,
        "gateway": gateway,
        "raw": stdout,
        "error": stderr if rc != 0 else None,
    }


def show_listening_ports() -> Dict[str, Any]:
    """Return listening TCP/UDP ports using `ss -tlnup`."""
    rc, stdout, stderr = _run(["ss", "-tlnup"])
    if rc != 0:
        # fallback to netstat
        rc, stdout, stderr = _run(["netstat", "-tlnup"])

    ports: List[Dict[str, str]] = []
    for line in stdout.splitlines()[1:]:  # skip header
        parts = line.split()
        if len(parts) >= 5:
            ports.append({
                "proto": parts[0],
                "state": parts[1] if parts[0].startswith("tcp") else "",
                "local_addr": parts[4] if parts[0].startswith("tcp") else parts[3],
                "process": parts[-1] if "pid" in parts[-1].lower() or "users:" in parts[-1].lower() else "",
                "raw": line,
            })

    return {
        "ports": ports,
        "raw": stdout,
        "error": stderr if rc != 0 else None,
    }


def ping_host(host: str, count: int = 4) -> Dict[str, Any]:
    """Ping a host and return structured results."""
    rc, stdout, stderr = _run(
        ["ping", "-c", str(count), "-W", "2", host], timeout=count * 3 + 5
    )
    # Parse summary line e.g. "4 packets transmitted, 4 received, 0% packet loss, time 3003ms"
    packet_loss = None
    rtt_avg = None
    for line in stdout.splitlines():
        if "packet loss" in line:
            parts = line.split(",")
            for p in parts:
                if "packet loss" in p:
                    packet_loss = p.strip().split()[0]
        if line.startswith("rtt") or line.startswith("round-trip"):
            # rtt min/avg/max/mdev = 1.234/2.345/3.456/0.123 ms
            try:
                vals = line.split("=")[1].strip().split("/")
                rtt_avg = vals[1] + " ms"
            except (IndexError, ValueError):
                pass

    return {
        "host": host,
        "reachable": rc == 0,
        "packet_loss": packet_loss,
        "rtt_avg": rtt_avg,
        "raw": stdout,
        "error": stderr if rc != 0 else None,
    }


def dns_lookup(host: str) -> Dict[str, Any]:
    """Resolve a hostname to IP addresses."""
    # Try dig first, fall back to host, then nslookup
    rc, stdout, stderr = _run(["dig", "+short", host])
    if rc == 0 and stdout.strip():
        addresses = [l.strip() for l in stdout.splitlines() if l.strip()]
        return {"host": host, "addresses": addresses, "tool": "dig", "raw": stdout}

    rc, stdout, stderr = _run(["host", host])
    if rc == 0:
        addresses = []
        for line in stdout.splitlines():
            if "has address" in line or "has IPv6" in line:
                addresses.append(line.split()[-1])
        return {"host": host, "addresses": addresses, "tool": "host", "raw": stdout}

    rc, stdout, stderr = _run(["nslookup", host])
    return {"host": host, "addresses": [], "tool": "nslookup",
            "raw": stdout, "error": stderr if rc != 0 else None}


def show_routes() -> Dict[str, Any]:
    """Show routing table."""
    rc, stdout, stderr = _run(["ip", "route", "show"])
    routes: List[Dict[str, str]] = []
    for line in stdout.splitlines():
        parts = line.split()
        if parts:
            r: Dict[str, str] = {"destination": parts[0]}
            for i, p in enumerate(parts):
                if p == "via" and i + 1 < len(parts):
                    r["gateway"] = parts[i + 1]
                if p == "dev" and i + 1 < len(parts):
                    r["interface"] = parts[i + 1]
                if p == "src" and i + 1 < len(parts):
                    r["src"] = parts[i + 1]
            routes.append(r)
    return {"routes": routes, "raw": stdout, "error": stderr if rc != 0 else None}


# ---------------------------------------------------------------------------
# Firewall operations
# ---------------------------------------------------------------------------

def _detect_firewall() -> str:
    """Detect the active firewall tool: 'ufw', 'firewalld', or 'iptables'."""
    rc, out, _ = _run(["which", "ufw"])
    if rc == 0:
        rc2, status, _ = _run(["ufw", "status"])
        if "inactive" not in status.lower():
            return "ufw"
    rc, out, _ = _run(["which", "firewall-cmd"])
    if rc == 0:
        return "firewalld"
    return "iptables"


def show_firewall_rules() -> Dict[str, Any]:
    """Return current firewall rules, auto-detecting the active tool."""
    fw = _detect_firewall()
    if fw == "ufw":
        rc, stdout, stderr = _run(["ufw", "status", "verbose"])
    elif fw == "firewalld":
        rc, stdout, stderr = _run(["firewall-cmd", "--list-all"])
    else:
        rc, stdout, stderr = _run(["iptables", "-L", "-n", "--line-numbers"])

    return {
        "firewall": fw,
        "raw": stdout,
        "error": stderr if rc != 0 else None,
    }


def allow_port(port: str, protocol: str = "tcp") -> Dict[str, Any]:
    """Allow inbound traffic on *port*/*protocol*. Returns the command to execute."""
    fw = _detect_firewall()
    if fw == "ufw":
        cmd = ["ufw", "allow", f"{port}/{protocol}"]
    elif fw == "firewalld":
        cmd = ["firewall-cmd", "--permanent", f"--add-port={port}/{protocol}"]
    else:
        cmd = ["iptables", "-A", "INPUT", "-p", protocol, "--dport", port, "-j", "ACCEPT"]

    rc, stdout, stderr = _run(cmd)
    return {
        "firewall": fw,
        "command": " ".join(cmd),
        "success": rc == 0,
        "stdout": stdout,
        "stderr": stderr,
    }


def deny_port(port: str, protocol: str = "tcp") -> Dict[str, Any]:
    """Block inbound traffic on *port*/*protocol*. Returns the command to execute."""
    fw = _detect_firewall()
    if fw == "ufw":
        cmd = ["ufw", "deny", f"{port}/{protocol}"]
    elif fw == "firewalld":
        cmd = ["firewall-cmd", "--permanent", f"--remove-port={port}/{protocol}"]
    else:
        cmd = ["iptables", "-A", "INPUT", "-p", protocol, "--dport", port, "-j", "DROP"]

    rc, stdout, stderr = _run(cmd)
    return {
        "firewall": fw,
        "command": " ".join(cmd),
        "success": rc == 0,
        "stdout": stdout,
        "stderr": stderr,
    }


# Convenience aliases
list_listening_ports = show_listening_ports
get_firewall_status = show_firewall_rules
list_interfaces = show_interfaces
