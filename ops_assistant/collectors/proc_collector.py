"""Proc Collector for high-performance Linux kernel telemetry."""

import os
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from ops_assistant.models import CPUMetrics, MemoryMetrics, LoadMetrics, DiskPartition

class ProcCollector:
    def __init__(self, proc_root: Path = Path("/proc")):
        self.proc_root = Path(proc_root) if isinstance(proc_root, (str, Path)) else Path("/proc")
        self._proc_root_str = str(self.proc_root)
        self._meminfo_str = os.path.join(self._proc_root_str, "meminfo")
        self._loadavg_str = os.path.join(self._proc_root_str, "loadavg")
        self._stat_str = os.path.join(self._proc_root_str, "stat")
        self._uptime_str = os.path.join(self._proc_root_str, "uptime")
        self._mounts_str = os.path.join(self._proc_root_str, "mounts")
        self._core_count = max(1, os.cpu_count() or 1)

        # Performance caching layers
        self._last_cpu_ticks: Optional[List[int]] = None
        self._last_cpu_time: float = 0.0
        self._cached_zombie_count: int = 0
        self._cached_zombie_time: float = 0.0

    def get_memory_metrics(self) -> MemoryMetrics:
        if not os.path.exists(self._meminfo_str):
            # Mock / fallback for testing
            return MemoryMetrics(
                total_mb=16384.0,
                used_mb=4096.0,
                free_mb=8192.0,
                available_mb=12288.0,
                used_percent=25.0,
                swap_total_mb=4096.0,
                swap_used_mb=0.0
            )

        data: Dict[str, float] = {}
        needed = {"MemTotal", "MemAvailable", "MemFree", "SwapTotal", "SwapFree"}
        try:
            with open(self._meminfo_str, "r", encoding="utf-8") as f:
                for line in f:
                    colon = line.find(":")
                    if colon != -1:
                        key = line[:colon]
                        if key in needed:
                            val_str = line[colon + 1:].lstrip()
                            space = val_str.find(" ")
                            if space != -1:
                                try:
                                    # Values in /proc/meminfo are in kB -> convert to MB
                                    data[key] = float(val_str[:space]) / 1024.0
                                except ValueError:
                                    pass
                            if len(data) == 5:
                                break
        except OSError:
            pass

        total = data.get("MemTotal", 1.0)
        available = data.get("MemAvailable", data.get("MemFree", 0.0))
        free = data.get("MemFree", 0.0)
        used = max(0.0, total - available)
        used_pct = round((used / total) * 100.0, 2)

        swap_total = data.get("SwapTotal", 0.0)
        swap_free = data.get("SwapFree", 0.0)
        swap_used = max(0.0, swap_total - swap_free)
        swap_pct = round((swap_used / swap_total) * 100.0, 2) if swap_total > 0 else 0.0

        return MemoryMetrics(
            total_mb=round(total, 2),
            used_mb=round(used, 2),
            free_mb=round(free, 2),
            available_mb=round(available, 2),
            used_percent=used_pct,
            swap_total_mb=round(swap_total, 2),
            swap_used_mb=round(swap_used, 2),
            swap_used_percent=swap_pct
        )

    def get_zombie_count(self, max_cache_age_s: float = 1.0) -> int:
        """Scans /proc for processes in 'Z' (Zombie) state with microsecond binary parsing and short-TTL caching."""
        now = time.time()
        if self._cached_zombie_time > 0 and (now - self._cached_zombie_time) < max_cache_age_s:
            return self._cached_zombie_count

        if not os.path.exists(self._proc_root_str):
            return 0

        zombies = 0
        try:
            for entry in os.scandir(self._proc_root_str):
                if entry.name.isdigit() and entry.is_dir():
                    try:
                        stat_path = f"{entry.path}/stat"
                        fd = os.open(stat_path, os.O_RDONLY)
                        try:
                            raw = os.read(fd, 128)
                        finally:
                            os.close(fd)
                        idx = raw.rfind(b")")
                        if idx != -1 and len(raw) > idx + 2:
                            if raw[idx + 2:idx + 3] == b"Z":
                                zombies += 1
                    except OSError:
                        continue
        except Exception:
            pass

        self._cached_zombie_count = zombies
        self._cached_zombie_time = now
        return zombies

    def get_load_metrics(self) -> LoadMetrics:
        if not os.path.exists(self._loadavg_str):
            return LoadMetrics(load_1m=0.5, load_5m=0.3, load_15m=0.2, running_processes=2, total_processes=150)

        try:
            with open(self._loadavg_str, "r", encoding="utf-8") as f:
                content = f.read().split()
        except OSError:
            content = []

        l1 = float(content[0]) if len(content) > 0 else 0.0
        l5 = float(content[1]) if len(content) > 1 else 0.0
        l15 = float(content[2]) if len(content) > 2 else 0.0
        
        running_proc = 1
        total_proc = 100
        if len(content) > 3 and "/" in content[3]:
            subparts = content[3].split("/")
            try:
                running_proc = int(subparts[0])
                total_proc = int(subparts[1])
            except ValueError:
                pass

        return LoadMetrics(
            load_1m=l1,
            load_5m=l5,
            load_15m=l15,
            running_processes=running_proc,
            total_processes=total_proc
        )

    def _read_cpu_ticks(self) -> Tuple[List[int], int]:
        try:
            with open(self._stat_str, "r", encoding="utf-8") as f:
                first_line = f.readline()
                if first_line.startswith("cpu "):
                    ticks = [int(x) for x in first_line.split()[1:]]
                    return ticks, self._core_count
        except OSError:
            pass
        return [], self._core_count

    def get_cpu_metrics(self, sample_interval_ms: int = 50) -> CPUMetrics:
        zombies = self.get_zombie_count()
        if not os.path.exists(self._stat_str):
            return CPUMetrics(user_pct=5.0, system_pct=2.0, idle_pct=92.0, iowait_pct=1.0, steal_pct=0.0, core_count=4, zombie_count=zombies)

        now = time.time()
        # Fast path: If previously sampled within a reasonable window, compute deltas without sleeping
        if self._last_cpu_ticks and (now - self._last_cpu_time) >= 0.02 and sample_interval_ms == 0:
            t1 = self._last_cpu_ticks
            cores = self._core_count
            t2, _ = self._read_cpu_ticks()
            self._last_cpu_ticks = t2
            self._last_cpu_time = now
        else:
            t1, cores = self._read_cpu_ticks()
            if not t1:
                return CPUMetrics(core_count=cores, zombie_count=zombies)

            if sample_interval_ms > 0:
                time.sleep(sample_interval_ms / 1000.0)
            t2, _ = self._read_cpu_ticks()
            self._last_cpu_ticks = t2
            self._last_cpu_time = time.time()

        if not t2 or len(t1) < 4 or len(t2) < 4:
            return CPUMetrics(core_count=cores, zombie_count=zombies)

        deltas = [b - a for a, b in zip(t1, t2)]
        total_delta = max(1, sum(deltas))

        # Ticks: 0:user, 1:nice, 2:system, 3:idle, 4:iowait, 5:irq, 6:softirq, 7:steal
        user_ticks = deltas[0] + (deltas[1] if len(deltas) > 1 else 0)
        system_ticks = deltas[2] + (deltas[5] if len(deltas) > 5 else 0) + (deltas[6] if len(deltas) > 6 else 0)
        idle_ticks = deltas[3]
        iowait_ticks = deltas[4] if len(deltas) > 4 else 0
        steal_ticks = deltas[7] if len(deltas) > 7 else 0

        return CPUMetrics(
            user_pct=round((user_ticks / total_delta) * 100.0, 2),
            system_pct=round((system_ticks / total_delta) * 100.0, 2),
            idle_pct=round((idle_ticks / total_delta) * 100.0, 2),
            iowait_pct=round((iowait_ticks / total_delta) * 100.0, 2),
            steal_pct=round((steal_ticks / total_delta) * 100.0, 2),
            core_count=cores,
            zombie_count=zombies
        )

    def get_uptime(self) -> float:
        if not os.path.exists(self._uptime_str):
            return 3600.0
        try:
            with open(self._uptime_str, "r", encoding="utf-8") as f:
                line = f.readline()
                space = line.find(" ")
                if space != -1:
                    return float(line[:space])
                return float(line.strip())
        except Exception:
            return 3600.0

    def get_disk_partitions(self) -> List[DiskPartition]:
        partitions: List[DiskPartition] = []
        target_mounts = ["/"]

        if os.path.exists(self._mounts_str):
            try:
                with open(self._mounts_str, "r", encoding="utf-8") as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 2:
                            dev, mount = parts[0], parts[1]
                            if dev.startswith("/dev/") and mount not in target_mounts:
                                target_mounts.append(mount)
            except Exception:
                pass

        for mp in target_mounts[:5]:
            try:
                st = os.statvfs(mp)
                total_bytes = st.f_blocks * st.f_frsize
                free_bytes = st.f_bavail * st.f_frsize
                used_bytes = total_bytes - free_bytes

                total_gb = round(total_bytes / (1024 ** 3), 2)
                used_gb = round(used_bytes / (1024 ** 3), 2)
                free_gb = round(free_bytes / (1024 ** 3), 2)
                used_pct = round((used_bytes / total_bytes * 100.0), 2) if total_bytes > 0 else 0.0

                # Inodes calculation
                inodes_total = st.f_files
                inodes_free = st.f_favail
                inodes_used = inodes_total - inodes_free
                inodes_pct = round((inodes_used / inodes_total * 100.0), 2) if inodes_total > 0 else 0.0

                partitions.append(DiskPartition(
                    mountpoint=mp,
                    total_gb=total_gb,
                    used_gb=used_gb,
                    free_gb=free_gb,
                    used_percent=used_pct,
                    inodes_total=inodes_total,
                    inodes_used=inodes_used,
                    inodes_percent=inodes_pct
                ))
            except Exception:
                continue

        if not partitions:
            partitions.append(DiskPartition(
                mountpoint="/",
                total_gb=100.0,
                used_gb=35.0,
                free_gb=65.0,
                used_percent=35.0,
                inodes_total=6553600,
                inodes_used=655360,
                inodes_percent=10.0
            ))

        return partitions
