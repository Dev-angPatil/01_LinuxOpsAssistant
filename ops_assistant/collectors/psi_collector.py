"""Pressure Stall Information (PSI) Collector for Linux Kernel Telemetry."""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class PSIStallValues:
    avg10: float = 0.0
    avg60: float = 0.0
    avg300: float = 0.0
    total_us: int = 0

@dataclass
class PSIMetrics:
    cpu_some: PSIStallValues
    memory_some: PSIStallValues
    memory_full: PSIStallValues
    io_some: PSIStallValues
    io_full: PSIStallValues
    is_available: bool = True
    pressure_level: str = "NORMAL"  # NORMAL, MODERATE, CRITICAL

class PSICollector:
    """Reads and parses /proc/pressure/{cpu,memory,io} kernel interfaces."""

    def __init__(self, pressure_dir: str = "/proc/pressure"):
        self.pressure_dir = pressure_dir
        self.cpu_path = os.path.join(pressure_dir, "cpu")
        self.mem_path = os.path.join(pressure_dir, "memory")
        self.io_path = os.path.join(pressure_dir, "io")

    def _parse_psi_file(self, file_path: str) -> Dict[str, PSIStallValues]:
        res: Dict[str, PSIStallValues] = {}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if not parts:
                        continue
                    stall_type = parts[0]  # 'some' or 'full'
                    avg10, avg60, avg300, total = 0.0, 0.0, 0.0, 0
                    for p in parts[1:]:
                        if p.startswith("avg10="):
                            avg10 = float(p[6:])
                        elif p.startswith("avg60="):
                            avg60 = float(p[6:])
                        elif p.startswith("avg300="):
                            avg300 = float(p[7:])
                        elif p.startswith("total="):
                            total = int(p[6:])
                    res[stall_type] = PSIStallValues(avg10=avg10, avg60=avg60, avg300=avg300, total_us=total)
        except OSError:
            pass
        return res

    def collect(self) -> PSIMetrics:
        cpu_data = self._parse_psi_file(self.cpu_path)
        mem_data = self._parse_psi_file(self.mem_path)
        io_data = self._parse_psi_file(self.io_path)

        if not cpu_data and not mem_data and not io_data:
            return PSIMetrics(
                cpu_some=PSIStallValues(),
                memory_some=PSIStallValues(),
                memory_full=PSIStallValues(),
                io_some=PSIStallValues(),
                io_full=PSIStallValues(),
                is_available=False,
                pressure_level="UNKNOWN"
            )

        cpu_some = cpu_data.get("some", PSIStallValues())
        mem_some = mem_data.get("some", PSIStallValues())
        mem_full = mem_data.get("full", PSIStallValues())
        io_some = io_data.get("some", PSIStallValues())
        io_full = io_data.get("full", PSIStallValues())

        # Determine overall pressure state
        max_avg10 = max(cpu_some.avg10, mem_some.avg10, mem_full.avg10, io_some.avg10, io_full.avg10)
        if max_avg10 >= 40.0:
            pressure_level = "CRITICAL"
        elif max_avg10 >= 10.0:
            pressure_level = "MODERATE"
        else:
            pressure_level = "NORMAL"

        return PSIMetrics(
            cpu_some=cpu_some,
            memory_some=mem_some,
            memory_full=mem_full,
            io_some=io_some,
            io_full=io_full,
            is_available=True,
            pressure_level=pressure_level
        )
