"""Systemd Collector for inspecting unit states and failed services."""

import shutil
import subprocess
from typing import List, Optional, Dict
from ops_assistant.models import SystemdUnitState

class SystemdCollector:
    def __init__(self):
        self.has_systemctl = shutil.which("systemctl") is not None

    def get_failed_units(self) -> List[SystemdUnitState]:
        if not self.has_systemctl:
            return []

        failed: List[SystemdUnitState] = []
        try:
            cmd = ["systemctl", "list-units", "--state=failed", "--no-legend", "--no-pager"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and res.stdout.strip():
                for line in res.stdout.strip().split("\n"):
                    parts = line.split()
                    if len(parts) >= 4:
                        unit_name = parts[0].lstrip("●").strip()
                        load_state = parts[1]
                        active_state = parts[2]
                        sub_state = parts[3]
                        desc = " ".join(parts[4:]) if len(parts) > 4 else ""
                        failed.append(SystemdUnitState(
                            unit_name=unit_name,
                            load_state=load_state,
                            active_state=active_state,
                            sub_state=sub_state,
                            description=desc
                        ))
        except Exception:
            pass

        return failed

    def inspect_unit(self, unit_name: str) -> Optional[SystemdUnitState]:
        if not self.has_systemctl:
            return None

        # Append .service if missing
        if not ("." in unit_name):
            unit_name = f"{unit_name}.service"

        try:
            cmd = ["systemctl", "show", unit_name, "-p", "LoadState,ActiveState,SubState,Description", "--no-pager"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and res.stdout.strip():
                data: Dict[str, str] = {}
                for line in res.stdout.strip().split("\n"):
                    if "=" in line:
                        k, v = line.split("=", 1)
                        data[k.strip()] = v.strip()

                return SystemdUnitState(
                    unit_name=unit_name,
                    load_state=data.get("LoadState", "unknown"),
                    active_state=data.get("ActiveState", "unknown"),
                    sub_state=data.get("SubState", "unknown"),
                    description=data.get("Description", "")
                )
        except Exception:
            pass

        return None
