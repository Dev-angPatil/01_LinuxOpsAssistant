"""Data models for Linux Operations Assistant using standard library dataclasses."""

from enum import Enum
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict

class SafetyLevel(str, Enum):
    READ_ONLY = "READ_ONLY"      # Safe read commands (cat, ls, journalctl, free, df)
    MODIFYING = "MODIFYING"      # Safe system state changes (systemctl restart, touch)
    HIGH_RISK = "HIGH_RISK"      # High impact modifications (chmod -R, iptables, kill)
    DESTRUCTIVE = "DESTRUCTIVE"  # Destructive data commands (rm -rf, mkfs, dd)

@dataclass
class CPUMetrics:
    user_pct: float = 0.0
    system_pct: float = 0.0
    idle_pct: float = 100.0
    iowait_pct: float = 0.0
    steal_pct: float = 0.0
    core_count: int = 1
    zombie_count: int = 0

@dataclass
class MemoryMetrics:
    total_mb: float = 0.0
    used_mb: float = 0.0
    free_mb: float = 0.0
    available_mb: float = 0.0
    used_percent: float = 0.0
    swap_total_mb: float = 0.0
    swap_used_mb: float = 0.0
    swap_used_percent: float = 0.0

@dataclass
class LoadMetrics:
    load_1m: float = 0.0
    load_5m: float = 0.0
    load_15m: float = 0.0
    running_processes: int = 0
    total_processes: int = 0

@dataclass
class DiskPartition:
    mountpoint: str
    total_gb: float
    used_gb: float
    free_gb: float
    used_percent: float
    inodes_total: Optional[int] = None
    inodes_used: Optional[int] = None
    inodes_percent: Optional[float] = None

@dataclass
class SystemdUnitState:
    unit_name: str
    load_state: str
    active_state: str
    sub_state: str
    description: str

@dataclass
class SystemHealthSnapshot:
    timestamp: str
    hostname: str
    kernel_release: str
    uptime_seconds: float
    cpu: CPUMetrics
    memory: MemoryMetrics
    load: LoadMetrics
    disks: List[DiskPartition] = field(default_factory=list)
    failed_units: List[SystemdUnitState] = field(default_factory=list)
    pressure_status: str = "NORMAL"
    psi_metrics: Optional[Dict[str, Any]] = None
    distro_info: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class LogRecord:
    timestamp: str
    source: str
    priority: str
    message: str
    unit: Optional[str] = None
    pid: Optional[int] = None

@dataclass
class CommandFlagExplanation:
    flag: str
    purpose: str

@dataclass
class CommandProposal:
    command: str
    safety_level: SafetyLevel
    risk_score: float
    rationale: str
    flag_breakdown: List[CommandFlagExplanation] = field(default_factory=list)
    requires_sudo: bool = False
    rollback_command: Optional[str] = None
    rollback_rationale: Optional[str] = None
    sandbox_verified: bool = False

@dataclass
class XAIExplanation:
    symptom: str
    root_cause: str
    rationale: str
    evidence_logs: List[str] = field(default_factory=list)
    confidence_score: float = 0.95
    proposed_commands: List[CommandProposal] = field(default_factory=list)
    mitigation_steps: List[str] = field(default_factory=list)

@dataclass
class DiagnosticReport:
    query: str
    explanation: XAIExplanation
    latency_ms: float
    target_subsystem: Optional[str] = None
    health_snapshot: Optional[SystemHealthSnapshot] = None
    causality_dag: Optional[Dict[str, Any]] = None
    status: str = "COMPLETED"
    reasoning_engine: str = "NeuroSymbolic-Causality-XAI"

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        # Convert Enum values to string
        if "explanation" in res and "proposed_commands" in res["explanation"]:
            for cmd in res["explanation"]["proposed_commands"]:
                if isinstance(cmd.get("safety_level"), SafetyLevel):
                    cmd["safety_level"] = cmd["safety_level"].value
        return res
