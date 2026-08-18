# Linux Failure Taxonomy & Diagnostic Playbook — `ops-assistant`

> **Scope**: 16+ Core Linux Failure Taxonomy Classes  
> **Reference**: C-DAC AI OS Hackathon 2026 — Track 1 / Problem Statement 2  

---

## 📚 Failure Taxonomy Overview

`ops-assistant` is pre-trained with deterministic causality models across 16 core Linux failure taxonomy classes. For each class, the engine correlates kernel and userspace telemetry, isolates the originating root cause, computes risk scores, and synthesizes reversible remediations.

---

## 🛠️ Taxonomy Class Reference

### 1. `PORT_CONFLICT` (`EADDRINUSE`)
- **Signature Patterns**: `Address already in use`, `bind() to 0.0.0.0:80 failed`, `failed to listen on port`
- **Telemetry Correlated**: `ss -tulpn`, `lsof -i`, journald daemon error logs
- **Root Cause Isolation**: Identifies offending PID and process binary occupying the socket.
- **Recommended Action**: Terminate offending process or rebind service.
- **Rollback Action**: Restart previous service binding if required.

---

### 2. `PERMISSION_DENIED` (`EACCES` / `EPERM`)
- **Signature Patterns**: `Permission denied`, `Failed to open /var/log/...`, `Operation not permitted`
- **Telemetry Correlated**: `stat` file mode, POSIX ownership (`uid:gid`), SELinux/AppArmor audit logs
- **Root Cause Isolation**: Pinpoints exact file path, current user/group, and missing capability.
- **Recommended Action**: `chown <user>:<group> <path>` or `chmod u+rw <path>`.
- **Rollback Action**: `chmod <old_perm> <path>` / `chown <old_owner> <path>`.

---

### 3. `OOM_KILL` (Kernel Out-Of-Memory)
- **Signature Patterns**: `Out of memory: Kill process`, `invoked oom-killer`, `score_adj`
- **Telemetry Correlated**: `/proc/pressure/memory`, `dmesg -T`, `/proc/meminfo` (SwapFree, Active/Inactive)
- **Root Cause Isolation**: Identifies killed PID, memory footprint (anon-rss, file-rss), and trigger process.
- **Recommended Action**: Adjust memory limits (`systemd MemoryMax`), add swapfile, or restart worker pools.
- **Rollback Action**: Revert cgroup memory configuration.

---

### 4. `DISK_EXHAUSTION` (`ENOSPC`)
- **Signature Patterns**: `No space left on device`, `write error: disk full`
- **Telemetry Correlated**: `statvfs` block counts, `df -h`, journald log truncation warnings
- **Root Cause Isolation**: Identifies filesystem mount point with $\ge 95\%$ block allocation.
- **Recommended Action**: Clean journald vacuum logs (`journalctl --vacuum-size=200M`), purge package caches (`apt clean`, `pacman -Sc`, `dnf clean all`).
- **Rollback Action**: None required (safe cleanup).

---

### 5. `INODE_EXHAUSTION` (0 Free Inodes)
- **Signature Patterns**: `No space left on device` (with $>20\%$ disk blocks free), `inode table full`
- **Telemetry Correlated**: `df -i`, `statvfs.f_ffree`
- **Root Cause Isolation**: Detects millions of small temporary files in `/tmp` or session directories.
- **Recommended Action**: Prune orphaned temporary files (`find /tmp -type f -mtime +7 -delete`).
- **Rollback Action**: N/A.

---

### 6. `CONFIG_SYNTAX_ERROR`
- **Signature Patterns**: `syntax error on line`, `directive is not allowed here`, `unknown directive`
- **Telemetry Correlated**: `/etc/<daemon>/<config>`, config test binaries (`nginx -t`, `apachectl configtest`, `sshd -t`)
- **Root Cause Isolation**: Extracts exact file path and invalid line number.
- **Recommended Action**: Correct syntax error or restore configuration backup.
- **Rollback Action**: Revert edit via `.bak` file.

---

### 7. `SSL_CERT_ERROR`
- **Signature Patterns**: `certificate has expired`, `SSL: CERTIFICATE_VERIFY_FAILED`, `handshake failed`
- **Telemetry Correlated**: TLS socket handshakes, certbot renewal logs, `/etc/ssl/certs/`
- **Root Cause Isolation**: Computes certificate expiration timestamp and domain mismatch.
- **Recommended Action**: Renew certificate via ACME/certbot (`certbot renew --force-renewal`).
- **Rollback Action**: N/A.

---

### 8. `DNS_RESOLUTION_FAILURE`
- **Signature Patterns**: `Temporary failure in name resolution`, `Could not resolve host`, `SERVFAIL`
- **Telemetry Correlated**: `/etc/resolv.conf`, `systemd-resolved` status, `/run/systemd/resolve/resolv.conf`
- **Root Cause Isolation**: Unreachable nameserver or inactive resolver daemon.
- **Recommended Action**: Restart `systemd-resolved` or configure fallback nameservers (`1.1.1.1`, `8.8.8.8`).
- **Rollback Action**: Restore previous `/etc/resolv.conf`.

---

### 9. `DPKG_LOCK_BLOCKED`
- **Signature Patterns**: `Could not get lock /var/lib/dpkg/lock-frontend`, `database is locked`
- **Telemetry Correlated**: `fuser /var/lib/dpkg/lock*`, `lsof`, process tree (unattended-upgrades, apt)
- **Root Cause Isolation**: Identifies colliding background package updater PID.
- **Recommended Action**: Wait for process completion or cleanly terminate background lock holder.
- **Rollback Action**: N/A.

---

### 10. `SYSTEMD_CRASH_LOOP`
- **Signature Patterns**: `Start request repeated too quickly`, `failed with result 'exit-code'`, `Job for unit failed`
- **Telemetry Correlated**: `systemctl status <unit>`, journalctl unit history, `StartLimitIntervalSec`
- **Root Cause Isolation**: Identifies missing environment variable, missing dependency, or crash loop.
- **Recommended Action**: Reset failed counter (`systemctl reset-failed <unit>`) and inspect upstream dependency.
- **Rollback Action**: Stop service.

---

### 11. `DB_CONN_EXHAUSTION`
- **Signature Patterns**: `FATAL: remaining connection slots are reserved`, `Too many connections`
- **Telemetry Correlated**: DB server logs, client connection counts via `ss -an`
- **Root Cause Isolation**: Detects connection leak or inadequate connection pooling.
- **Recommended Action**: Increase `max_connections` or enable connection pooling (PgBouncer/ProxySQL).
- **Rollback Action**: Revert configuration parameter.

---

### 12. `FIREWALL_PORT_BLOCKED`
- **Signature Patterns**: `Connection refused`, `Connection timed out`, `UFW BLOCK`, `kernel: [UFW DROP]`
- **Telemetry Correlated**: `dmesg` netfilter drops, `ufw status`, `iptables -L -n -v`, `nft list ruleset`
- **Root Cause Isolation**: Distinguishes between closed port (no daemon) vs dropped packet (firewall rule).
- **Recommended Action**: Open port in distro firewall (`ufw allow <port>`, `firewall-cmd --add-port=<port>`).
- **Rollback Action**: `ufw delete allow <port>`, `firewall-cmd --remove-port=<port>`.

---

### 13. `ZOMBIE_PROCESS_ACCUMULATION`
- **Signature Patterns**: `defunct`, large process table growth, PID exhaustion
- **Telemetry Correlated**: `/proc/[pid]/stat` state `Z`, parent PID lookups
- **Root Cause Isolation**: Identifies faulty parent process failing to call `wait()`/`waitpid()`.
- **Recommended Action**: Signal parent process (`kill -HUP <ppid>`) or restart parent daemon.
- **Rollback Action**: Restart parent service.

---

### 14. `IOWAIT_BOTTLENECK`
- **Signature Patterns**: `high iowait`, disk queue backlog, thread uninterruptible sleep `D`
- **Telemetry Correlated**: `/proc/pressure/io`, `/proc/stat` iowait counter, `iotop` / `vmstat`
- **Root Cause Isolation**: Identifies high-throughput disk write process saturating controller.
- **Recommended Action**: Renice process I/O priority (`ionice -c 3 -p <pid>`) or optimize write buffering.
- **Rollback Action**: Reset ionice priority.

---

### 15. `SELINUX_APPARMOR_DENIAL`
- **Signature Patterns**: `AVC apparmor="DENIED"`, `type=AVC msg=audit`, `comm="nginx"`
- **Telemetry Correlated**: `/var/log/audit/audit.log`, `/var/log/syslog`, `aa-status`, `sestatus`
- **Root Cause Isolation**: Identifies profile denial violating Mandatory Access Control.
- **Recommended Action**: Generate policy rule (`audit2allow -a -M mypolicy`) or update AppArmor profile.
- **Rollback Action**: Remove custom policy module.

---

### 16. `NTP_CLOCK_DRIFT`
- **Signature Patterns**: `System clock unsynchronized`, `NTP synchronization lost`, `skew detected`
- **Telemetry Correlated**: `timedatectl`, `chronyc tracking`, `systemd-timesyncd`
- **Root Cause Isolation**: Identifies unreachable NTP stratum servers or stopped sync service.
- **Recommended Action**: Enable and start time sync (`timedatectl set-ntp true`).
- **Rollback Action**: `timedatectl set-ntp false`.
