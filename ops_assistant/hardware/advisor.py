"""
Intelligent Model Selector & Dynamic Capability Pruning Engine.

Determines optimal local GGUF model download recommendations,
inference parameters (threads, context size, GPU offloading),
and constructs the system Capability Matrix (features to keep vs features to avoid)
based on real-time hardware constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from ops_assistant.hardware.profiler import HardwareProfile, HardwareProfiler


class ModelTier(str, Enum):
    TIER_0 = "Tier-0-Micro"
    TIER_1 = "Tier-1-Constrained"
    TIER_2 = "Tier-2-Balanced"
    TIER_3 = "Tier-3-Workstation"
    TIER_4 = "Tier-4-HighPerformance"


MODEL_CATALOG: Dict[str, Dict[str, Any]] = {
    "smollm2-360m": {
        "key": "smollm2-360m",
        "name": "SmolLM2-360M-Instruct (Q4_K_M)",
        "filename": "smollm2-360m-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct-GGUF/resolve/main/smollm2-360m-instruct-q4_k_m.gguf",
        "size_bytes": 229343712,  # ~218 MB
        "ram_required_mb": 800.0,
        "vram_recommended_mb": 0.0,
        "min_cores": 1,
        "tier": ModelTier.TIER_1.value,
        "description": "Ultra-compact 360M parameter model for extremely low-memory systems and embedded Linux.",
    },
    "qwen2.5-coder-0.5b": {
        "key": "qwen2.5-coder-0.5b",
        "name": "Qwen2.5-Coder-0.5B-Instruct (Q4_K_M)",
        "filename": "qwen2.5-coder-0.5b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF/resolve/main/qwen2.5-coder-0.5b-instruct-q4_k_m.gguf",
        "size_bytes": 397734208,  # ~379 MB
        "ram_required_mb": 1200.0,
        "vram_recommended_mb": 0.0,
        "min_cores": 2,
        "tier": ModelTier.TIER_1.value,
        "description": "Fast 0.5B parameter code & operations model with strong bash comprehension.",
    },
    "qwen2.5-coder-1.5b": {
        "key": "qwen2.5-coder-1.5b",
        "name": "Qwen2.5-Coder-1.5B-Instruct (Q4_K_M)",
        "filename": "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF/resolve/main/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
        "size_bytes": 1034000000,  # ~986 MB
        "ram_required_mb": 2500.0,
        "vram_recommended_mb": 1500.0,
        "min_cores": 4,
        "tier": ModelTier.TIER_2.value,
        "description": "Balanced 1.5B model offering high-precision diagnosis and command synthesis.",
    },
    "llama-3.2-3b": {
        "key": "llama-3.2-3b",
        "name": "Llama-3.2-3B-Instruct (Q4_K_M)",
        "filename": "llama-3.2-3b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "size_bytes": 2019000000,  # ~1.92 GB
        "ram_required_mb": 4500.0,
        "vram_recommended_mb": 3000.0,
        "min_cores": 4,
        "tier": ModelTier.TIER_3.value,
        "description": "Mid-range Llama 3.2 model for comprehensive multi-step reasoning.",
    },
    "qwen2.5-coder-7b": {
        "key": "qwen2.5-coder-7b",
        "name": "Qwen2.5-Coder-7B-Instruct (Q4_K_M)",
        "filename": "qwen2.5-coder-7b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q4_k_m.gguf",
        "size_bytes": 4680000000,  # ~4.36 GB
        "ram_required_mb": 8500.0,
        "vram_recommended_mb": 5500.0,
        "min_cores": 6,
        "tier": ModelTier.TIER_4.value,
        "description": "State-of-the-art 7B code model with deep Linux systems programming mastery.",
    },
    "mistral-7b-instruct": {
        "key": "mistral-7b-instruct",
        "name": "Mistral-7B-Instruct-v0.3 (Q4_K_M)",
        "filename": "mistral-7b-instruct-v0.3-q4_k_m.gguf",
        "url": "https://huggingface.co/MaziyarPanahi/Mistral-7B-Instruct-v0.3-GGUF/resolve/main/Mistral-7B-Instruct-v0.3.Q4_K_M.gguf",
        "size_bytes": 4370000000,  # ~4.07 GB
        "ram_required_mb": 8000.0,
        "vram_recommended_mb": 5000.0,
        "min_cores": 6,
        "tier": ModelTier.TIER_4.value,
        "description": "High-performance 7B generalist model for complex multi-turn sysadmin workflows.",
    },
    "deepseek-r1-distill-qwen-7b": {
        "key": "deepseek-r1-distill-qwen-7b",
        "name": "DeepSeek-R1-Distill-Qwen-7B (Q4_K_M)",
        "filename": "deepseek-r1-distill-qwen-7b-q4_k_m.gguf",
        "url": "https://huggingface.co/unsloth/DeepSeek-R1-Distill-Qwen-7B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf",
        "size_bytes": 4920000000,  # ~4.58 GB
        "ram_required_mb": 9000.0,
        "vram_recommended_mb": 6000.0,
        "min_cores": 8,
        "tier": ModelTier.TIER_4.value,
        "description": "Chain-of-thought reasoning model for complex distributed root-cause analysis.",
    }
}


@dataclass
class CapabilityMatrix:
    features_to_keep: List[Dict[str, str]] = field(default_factory=list)
    features_to_avoid: List[Dict[str, str]] = field(default_factory=list)
    recommended_threads: int = 2
    recommended_ctx_size: int = 2048
    recommended_gpu_layers: int = 0
    max_log_scan_lines: int = 100
    enable_llm_inference: bool = True
    enable_proactive_monitoring: bool = True
    enable_sse_streaming: bool = True
    enable_deep_dag_analysis: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ModelSelector:
    """Selects the ideal model from the catalog given a HardwareProfile."""

    @classmethod
    def recommend_model(cls, profile: HardwareProfile) -> Dict[str, Any]:
        headroom_mb = profile.memory.safe_model_headroom_mb
        vram_mb = profile.gpu.free_vram_mb if profile.gpu.present else 0.0
        cores = profile.cpu.logical_cores
        disk_avail_gb = profile.storage.available_gb

        # Check if hardware is ultra constrained
        if profile.memory.total_mb < 1500 or headroom_mb < 400:
            return {
                "model_key": None,
                "name": "Deterministic Expert Rule Engine (0 MB Model)",
                "reason": "System RAM is below 1.5 GB. Using offline 16-class deterministic rule engine to eliminate memory pressure.",
                "download_required": False,
                "tier": ModelTier.TIER_0.value,
                "model_info": None
            }

        # Find best fitting model from highest to lowest tier
        candidate_order = [
            "deepseek-r1-distill-qwen-7b",
            "qwen2.5-coder-7b",
            "mistral-7b-instruct",
            "llama-3.2-3b",
            "qwen2.5-coder-1.5b",
            "qwen2.5-coder-0.5b",
            "smollm2-360m"
        ]

        for key in candidate_order:
            info = MODEL_CATALOG[key]
            size_gb = info["size_bytes"] / (1024 ** 3)
            # Need enough disk space + 1GB safety margin
            if disk_avail_gb < (size_gb + 1.0):
                continue

            # Check if GPU offload or CPU RAM satisfies model requirements
            can_run_gpu = (vram_mb >= info["vram_recommended_mb"] and info["vram_recommended_mb"] > 0)
            can_run_cpu = (headroom_mb >= info["ram_required_mb"] and cores >= info["min_cores"])

            if can_run_gpu or can_run_cpu:
                accel_type = "GPU Accelerated (VRAM)" if can_run_gpu else "CPU Multithreaded"
                return {
                    "model_key": key,
                    "name": info["name"],
                    "filename": info["filename"],
                    "size_mb": round(info["size_bytes"] / (1024 * 1024), 1),
                    "tier": info["tier"],
                    "acceleration": accel_type,
                    "reason": f"Optimally matched for {profile.memory.total_gb} GB RAM ({cores} CPU cores) and {profile.gpu.device_name}.",
                    "download_required": True,
                    "model_info": info
                }

        # Fallback to smollm2-360m
        fallback_info = MODEL_CATALOG["smollm2-360m"]
        return {
            "model_key": "smollm2-360m",
            "name": fallback_info["name"],
            "filename": fallback_info["filename"],
            "size_mb": round(fallback_info["size_bytes"] / (1024 * 1024), 1),
            "tier": ModelTier.TIER_1.value,
            "acceleration": "CPU Multithreaded (Safe Fallback)",
            "reason": "Lightweight fallback model ensuring zero memory exhaustion risk.",
            "download_required": True,
            "model_info": fallback_info
        }


class HardwareAdvisor:
    """
    Advises on model selection, inference concurrency, and capability pruning.
    """

    def __init__(self, profiler: Optional[HardwareProfiler] = None):
        self.profiler = profiler or HardwareProfiler()

    def get_full_advisory(self) -> Dict[str, Any]:
        """Generate comprehensive hardware assessment and capability guidance."""
        profile = self.profiler.profile()
        model_rec = ModelSelector.recommend_model(profile)
        caps = self.generate_capability_matrix(profile)

        return {
            "profile": profile.to_dict(),
            "recommended_model": model_rec,
            "capability_matrix": caps.to_dict(),
            "all_compatible_models": self._list_compatibility(profile)
        }

    def generate_capability_matrix(self, profile: HardwareProfile) -> CapabilityMatrix:
        """
        Dynamically decide what functionality to keep and what to avoid/prune.
        """
        mem_mb = profile.memory.total_mb
        cores = profile.cpu.logical_cores
        gpu = profile.gpu

        keep: List[Dict[str, str]] = []
        avoid: List[Dict[str, str]] = []

        # Always keep core deterministic engine
        keep.append({
            "feature": "16-Class Failure Taxonomy Engine",
            "status": "ENABLED",
            "rationale": "Sub-50ms deterministic triage uses 0 MB model memory and zero cloud tokens."
        })
        keep.append({
            "feature": "Multi-Distro Knowledge Base",
            "status": "ENABLED",
            "rationale": "Embedded SQLite database provides instant cross-distro command adaptation."
        })

        # LLM Inference
        if mem_mb >= 1500:
            enable_llm = True
            keep.append({
                "feature": "Local LLM Inference Engine",
                "status": "ENABLED",
                "rationale": f"System has {profile.memory.total_gb} GB RAM, sufficient for tier-matched GGUF inference."
            })
        else:
            enable_llm = False
            avoid.append({
                "feature": "Local In-Process LLM Weights",
                "status": "DISABLED",
                "rationale": "System RAM < 1.5 GB. Disabled to prevent Out-of-Memory (OOM) kernel panics."
            })

        # Live SSE Streaming Telemetry
        if cores >= 2 and mem_mb >= 2048:
            enable_sse = True
            keep.append({
                "feature": "Real-Time SSE Telemetry Streaming",
                "status": "ENABLED",
                "rationale": "Multi-core CPU supports non-blocking 1.5s background polling."
            })
        else:
            enable_sse = False
            avoid.append({
                "feature": "Continuous SSE Live Polling",
                "status": "THROTTLED",
                "rationale": "Single-core or constrained memory system; use on-demand telemetry queries."
            })

        # Log Scan Buffer
        if mem_mb >= 8192:
            max_lines = 1000
            keep.append({
                "feature": "Deep Log Ingestion (1000+ lines)",
                "status": "ENABLED",
                "rationale": "High memory headroom allows deep journalctl and dmesg history scraping."
            })
        elif mem_mb >= 3000:
            max_lines = 200
            keep.append({
                "feature": "Standard Log Ingestion (200 lines)",
                "status": "ENABLED",
                "rationale": "Balanced buffer size captures essential crash logs without cache bloat."
            })
        else:
            max_lines = 50
            avoid.append({
                "feature": "Deep Historical Log Scrapes",
                "status": "RESTRICTED (50 lines)",
                "rationale": "Constrained memory; log buffer limited to 50 lines to preserve RAM."
            })

        # Dynamic Causality DAG
        if mem_mb >= 2048:
            enable_dag = True
            keep.append({
                "feature": "Dynamic Temporal Causality DAG",
                "status": "ENABLED",
                "rationale": "Constructs full topological root-cause graphs from multi-log event streams."
            })
        else:
            enable_dag = False
            avoid.append({
                "feature": "Multi-Node Causality DAG Graphs",
                "status": "SIMPLIFIED",
                "rationale": "Edge device; uses linear causal matching rather than in-memory DAG structures."
            })

        # Ephemeral Sandbox Probe
        keep.append({
            "feature": "Ephemeral Namespace CoW Probe",
            "status": "ENABLED",
            "rationale": "Safe unshare + OverlayFS dry-run verifies syntax before user prompts."
        })

        # Proactive Monitoring & Audits
        if cores >= 4 and mem_mb >= 4096:
            enable_proactive = True
            keep.append({
                "feature": "Proactive Autonomous Health Auditor",
                "status": "ENABLED",
                "rationale": "System has sufficient compute to run multi-subsystem security & storage audits."
            })
        else:
            enable_proactive = True
            avoid.append({
                "feature": "Continuous Background Proactive Loops",
                "status": "ON-DEMAND ONLY",
                "rationale": "Run proactive health scans on-demand rather than as continuous background daemons."
            })

        # Docker Operations
        import shutil
        if shutil.which("docker"):
            keep.append({
                "feature": "Docker & Container Operations",
                "status": "ENABLED",
                "rationale": "Docker daemon binary detected on host system."
            })
        else:
            avoid.append({
                "feature": "Docker Daemon Management",
                "status": "SKIPPED",
                "rationale": "Docker CLI not installed on host machine."
            })

        # Compute optimal threads & GPU layers
        recommended_threads = max(1, min(cores - 1 if cores > 2 else cores, 8))
        recommended_ctx = 4096 if mem_mb >= 8192 else 2048
        gpu_layers = 0
        if gpu.present:
            if gpu.vendor == "nvidia" and gpu.total_vram_mb >= 6000:
                gpu_layers = 33
            elif gpu.total_vram_mb >= 3000:
                gpu_layers = 20
            elif gpu.total_vram_mb >= 1500:
                gpu_layers = 10

        return CapabilityMatrix(
            features_to_keep=keep,
            features_to_avoid=avoid,
            recommended_threads=recommended_threads,
            recommended_ctx_size=recommended_ctx,
            recommended_gpu_layers=gpu_layers,
            max_log_scan_lines=max_lines,
            enable_llm_inference=enable_llm,
            enable_proactive_monitoring=enable_proactive,
            enable_sse_streaming=enable_sse,
            enable_deep_dag_analysis=enable_dag
        )

    def _list_compatibility(self, profile: HardwareProfile) -> List[Dict[str, Any]]:
        """Evaluate all models in the catalog against this hardware profile."""
        results = []
        headroom_mb = profile.memory.safe_model_headroom_mb
        vram_mb = profile.gpu.free_vram_mb if profile.gpu.present else 0.0

        for key, info in MODEL_CATALOG.items():
            ram_ok = headroom_mb >= info["ram_required_mb"]
            vram_ok = (vram_mb >= info["vram_recommended_mb"]) if info["vram_recommended_mb"] > 0 else False
            compat = ram_ok or vram_ok
            results.append({
                "key": key,
                "name": info["name"],
                "size_mb": round(info["size_bytes"] / (1024 * 1024), 1),
                "compatible": compat,
                "required_ram_mb": info["ram_required_mb"],
                "recommended_vram_mb": info["vram_recommended_mb"],
                "status": "Compatible" if compat else "Insufficient RAM/VRAM",
                "tier": info["tier"]
            })
        return results
