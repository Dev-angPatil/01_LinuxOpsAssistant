"""
Linux Hardware Profiler & Benchmarking Engine.

Inspects CPU (cores, architecture, AVX2/AVX-512/NEON vector flags),
RAM & Swap headroom (/proc/meminfo),
GPU & VRAM (NVIDIA CUDA, AMD ROCm/Radeon, Intel Arc/Iris, Apple/Vulkan, CPU-fallback),
and Storage availability for local AI model inference and capability tuning.
"""

from __future__ import annotations

import os
import re
import shutil
import platform
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CPUInfo:
    architecture: str = "x86_64"
    model_name: str = "Unknown CPU"
    physical_cores: int = 1
    logical_cores: int = 1
    frequency_mhz: float = 0.0
    flags: List[str] = field(default_factory=list)
    has_avx2: bool = False
    has_avx512: bool = False
    has_neon: bool = False
    has_fma: bool = False
    has_fp16: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryInfo:
    total_mb: float = 0.0
    available_mb: float = 0.0
    free_mb: float = 0.0
    swap_total_mb: float = 0.0
    swap_free_mb: float = 0.0
    swap_used_mb: float = 0.0
    safe_model_headroom_mb: float = 0.0

    @property
    def total_gb(self) -> float:
        return round(self.total_mb / 1024.0, 2)

    @property
    def available_gb(self) -> float:
        return round(self.available_mb / 1024.0, 2)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["total_gb"] = self.total_gb
        d["available_gb"] = self.available_gb
        return d


@dataclass
class GPUInfo:
    present: bool = False
    vendor: str = "cpu_fallback"  # "nvidia", "amd", "intel", "apple", "cpu_fallback"
    device_name: str = "No dedicated GPU (CPU inference)"
    total_vram_mb: float = 0.0
    free_vram_mb: float = 0.0
    driver_version: str = ""
    compute_api: str = "CPU (AVX2/Vectorized)"
    cuda_compute_cap: Optional[str] = None

    @property
    def total_vram_gb(self) -> float:
        return round(self.total_vram_mb / 1024.0, 2)

    @property
    def free_vram_gb(self) -> float:
        return round(self.free_vram_mb / 1024.0, 2)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["total_vram_gb"] = self.total_vram_gb
        d["free_vram_gb"] = self.free_vram_gb
        return d


@dataclass
class StorageInfo:
    target_path: str = "/"
    total_gb: float = 0.0
    available_gb: float = 0.0
    used_gb: float = 0.0
    used_percent: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HardwareProfile:
    timestamp: float
    cpu: CPUInfo
    memory: MemoryInfo
    gpu: GPUInfo
    storage: StorageInfo
    hardware_score: float = 0.0
    compute_tier: str = "Tier-1-Lightweight"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "cpu": self.cpu.to_dict(),
            "memory": self.memory.to_dict(),
            "gpu": self.gpu.to_dict(),
            "storage": self.storage.to_dict(),
            "hardware_score": self.hardware_score,
            "compute_tier": self.compute_tier,
        }


class HardwareProfiler:
    """
    Cross-vendor Linux Hardware Profiler.
    Inspects system compute, memory, graphics acceleration, and storage capabilities.
    """

    def __init__(self, models_dir: Optional[Path] = None):
        if models_dir is None:
            from ops_assistant.model_manager.downloader import get_default_models_dir
            self.models_dir = get_default_models_dir()
        else:
            self.models_dir = Path(models_dir)

    def profile(self) -> HardwareProfile:
        """Generate a full hardware snapshot with compute score and tier."""
        import time
        cpu = self.inspect_cpu()
        mem = self.inspect_memory()
        gpu = self.inspect_gpu()
        storage = self.inspect_storage(str(self.models_dir))

        score = self._calculate_hardware_score(cpu, mem, gpu)
        tier = self._classify_compute_tier(score, mem, gpu)

        return HardwareProfile(
            timestamp=time.time(),
            cpu=cpu,
            memory=mem,
            gpu=gpu,
            storage=storage,
            hardware_score=round(score, 2),
            compute_tier=tier
        )

    def inspect_cpu(self) -> CPUInfo:
        """Inspect CPU cores, clock, architecture and SIMD flags."""
        arch = platform.machine() or "x86_64"
        logical = os.cpu_count() or 1
        physical = max(1, logical // 2) if "x86" in arch or "amd" in arch else logical

        model_name = platform.processor() or "Generic Linux CPU"
        freq = 0.0
        flags: List[str] = []

        # Parse /proc/cpuinfo
        if os.path.exists("/proc/cpuinfo"):
            try:
                core_ids = set()
                with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "model name" in line and model_name in ("Generic Linux CPU", ""):
                            parts = line.split(":", 1)
                            if len(parts) > 1:
                                model_name = parts[1].strip()
                        elif "cpu MHz" in line and freq == 0.0:
                            parts = line.split(":", 1)
                            if len(parts) > 1:
                                try:
                                    freq = float(parts[1].strip())
                                except ValueError:
                                    pass
                        elif "flags" in line or "Features" in line:
                            parts = line.split(":", 1)
                            if len(parts) > 1:
                                flags = parts[1].strip().lower().split()
                        elif "core id" in line:
                            parts = line.split(":", 1)
                            if len(parts) > 1:
                                core_ids.add(parts[1].strip())
                if core_ids:
                    physical = len(core_ids)
            except Exception:
                pass

        flags_set = set(flags)
        has_avx2 = "avx2" in flags_set
        has_avx512 = any(f.startswith("avx512") for f in flags_set)
        has_neon = "asimd" in flags_set or "neon" in flags_set
        has_fma = "fma" in flags_set
        has_fp16 = "fp16" in flags_set or "fphp" in flags_set

        return CPUInfo(
            architecture=arch,
            model_name=model_name,
            physical_cores=physical,
            logical_cores=logical,
            frequency_mhz=freq,
            flags=flags[:40],
            has_avx2=has_avx2,
            has_avx512=has_avx512,
            has_neon=has_neon,
            has_fma=has_fma,
            has_fp16=has_fp16
        )

    def inspect_memory(self) -> MemoryInfo:
        """Inspect RAM and Swap memory from /proc/meminfo."""
        mem_total = 0.0
        mem_avail = 0.0
        mem_free = 0.0
        swap_total = 0.0
        swap_free = 0.0

        if os.path.exists("/proc/meminfo"):
            try:
                with open("/proc/meminfo", "r", encoding="utf-8") as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 2:
                            key = parts[0].rstrip(":")
                            try:
                                val_kb = float(parts[1])
                                val_mb = val_kb / 1024.0
                                if key == "MemTotal":
                                    mem_total = val_mb
                                elif key == "MemAvailable":
                                    mem_avail = val_mb
                                elif key == "MemFree":
                                    mem_free = val_mb
                                elif key == "SwapTotal":
                                    swap_total = val_mb
                                elif key == "SwapFree":
                                    swap_free = val_mb
                            except ValueError:
                                pass
            except Exception:
                pass

        if mem_avail == 0.0:
            mem_avail = mem_free if mem_free > 0.0 else mem_total * 0.5

        swap_used = max(0.0, swap_total - swap_free)
        # Safe model headroom: 70% of available RAM (leaving 30% for OS & user tasks)
        safe_headroom = max(0.0, mem_avail * 0.70)

        return MemoryInfo(
            total_mb=round(mem_total, 1),
            available_mb=round(mem_avail, 1),
            free_mb=round(mem_free, 1),
            swap_total_mb=round(swap_total, 1),
            swap_free_mb=round(swap_free, 1),
            swap_used_mb=round(swap_used, 1),
            safe_model_headroom_mb=round(safe_headroom, 1)
        )

    def inspect_gpu(self) -> GPUInfo:
        """
        Multi-vendor graphics acceleration detector.
        Tries NVIDIA (nvidia-smi), AMD (rocm-smi / sysfs), Intel (intel_gpu_top / sysfs), or CPU fallback.
        """
        # 1. Probe NVIDIA CUDA
        if shutil.which("nvidia-smi"):
            try:
                cmd = [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.free,driver_version,compute_cap",
                    "--format=csv,noheader,nounits"
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                if proc.returncode == 0 and proc.stdout.strip():
                    line = proc.stdout.strip().splitlines()[0]
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 4:
                        dev_name = parts[0]
                        total_vram = float(parts[1])
                        free_vram = float(parts[2])
                        driver_ver = parts[3]
                        compute_cap = parts[4] if len(parts) > 4 else "N/A"
                        return GPUInfo(
                            present=True,
                            vendor="nvidia",
                            device_name=dev_name,
                            total_vram_mb=total_vram,
                            free_vram_mb=free_vram,
                            driver_version=driver_ver,
                            compute_api="NVIDIA CUDA",
                            cuda_compute_cap=compute_cap
                        )
            except Exception:
                pass

        # 2. Probe AMD ROCm / Radeon
        if shutil.which("rocm-smi"):
            try:
                cmd = ["rocm-smi", "--showmeminfo", "vram", "--json"]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                if proc.returncode == 0 and proc.stdout.strip():
                    import json
                    data = json.loads(proc.stdout)
                    # parse first card
                    for card, info in data.items():
                        tot_str = info.get("VRAM Total Memory (B)", "0")
                        used_str = info.get("VRAM Total Used Memory (B)", "0")
                        tot_mb = float(tot_str) / (1024 * 1024)
                        free_mb = max(0.0, tot_mb - (float(used_str) / (1024 * 1024)))
                        return GPUInfo(
                            present=True,
                            vendor="amd",
                            device_name=f"AMD Radeon ({card})",
                            total_vram_mb=round(tot_mb, 1),
                            free_vram_mb=round(free_mb, 1),
                            compute_api="AMD ROCm / HIP"
                        )
            except Exception:
                pass

        # 3. Probe Linux DRM sysfs & lspci for AMD / Intel / Discrete GPUs
        vga_name = ""
        if shutil.which("lspci"):
            try:
                proc = subprocess.run(["lspci"], capture_output=True, text=True, timeout=3)
                if proc.returncode == 0:
                    for line in proc.stdout.splitlines():
                        if re.search(r"(VGA|3D|Display)", line, re.IGNORECASE):
                            vga_name = line.split(":", 2)[-1].strip()
                            break
            except Exception:
                pass

        # Check /sys/class/drm for VRAM
        vram_total_mb = 0.0
        vram_free_mb = 0.0
        try:
            drm_path = Path("/sys/class/drm")
            if drm_path.exists():
                for card in drm_path.glob("card*"):
                    vram_file = card / "device" / "mem_info_vram_total"
                    vram_used_file = card / "device" / "mem_info_vram_used"
                    if vram_file.exists():
                        tot_bytes = int(vram_file.read_text().strip())
                        used_bytes = int(vram_used_file.read_text().strip()) if vram_used_file.exists() else 0
                        vram_total_mb = tot_bytes / (1024 * 1024)
                        vram_free_mb = max(0.0, (tot_bytes - used_bytes) / (1024 * 1024))
                        break
        except Exception:
            pass

        if vga_name:
            is_amd = bool(re.search(r"AMD|ATI|Radeon", vga_name, re.IGNORECASE))
            is_intel = bool(re.search(r"Intel", vga_name, re.IGNORECASE))
            is_nvidia = bool(re.search(r"NVIDIA", vga_name, re.IGNORECASE))

            vendor = "amd" if is_amd else ("intel" if is_intel else ("nvidia" if is_nvidia else "generic"))
            compute_api = "Vulkan / OpenCL (VRAM)" if vram_total_mb > 0 else "Direct Rendering Manager"

            return GPUInfo(
                present=True,
                vendor=vendor,
                device_name=vga_name,
                total_vram_mb=round(vram_total_mb, 1),
                free_vram_mb=round(vram_free_mb, 1),
                compute_api=compute_api
            )

        # 4. Fallback: CPU
        return GPUInfo(
            present=False,
            vendor="cpu_fallback",
            device_name="CPU Standard Execution (No discrete GPU)",
            total_vram_mb=0.0,
            free_vram_mb=0.0,
            compute_api="CPU (AVX2 / Multi-Thread)"
        )

    def inspect_storage(self, target_path: str = "/") -> StorageInfo:
        """Inspect disk space on the model storage partition."""
        p = Path(target_path).expanduser().resolve()
        if not p.exists():
            p = Path("/")

        try:
            st = os.statvfs(str(p))
            total_gb = (st.f_blocks * st.f_frsize) / (1024 ** 3)
            avail_gb = (st.f_bavail * st.f_frsize) / (1024 ** 3)
            used_gb = total_gb - avail_gb
            pct = (used_gb / total_gb * 100.0) if total_gb > 0 else 0.0
            return StorageInfo(
                target_path=str(p),
                total_gb=round(total_gb, 2),
                available_gb=round(avail_gb, 2),
                used_gb=round(used_gb, 2),
                used_percent=round(pct, 1)
            )
        except Exception:
            return StorageInfo(target_path=str(p))

    def _calculate_hardware_score(self, cpu: CPUInfo, mem: MemoryInfo, gpu: GPUInfo) -> float:
        """
        Compute a normalized hardware performance score (0.0 to 100.0).
        Weights: Memory (45%), CPU (35%), GPU (20%).
        """
        # Memory component (up to 45 pts, 32GB RAM = max)
        mem_score = min(45.0, (mem.total_mb / (32.0 * 1024.0)) * 45.0)

        # CPU component (up to 35 pts)
        cores_pts = min(20.0, (cpu.logical_cores / 16.0) * 20.0)
        simd_pts = (5.0 if cpu.has_avx512 else (3.0 if cpu.has_avx2 else (3.0 if cpu.has_neon else 0.0)))
        fma_pts = 2.0 if cpu.has_fma else 0.0
        clock_pts = min(8.0, (cpu.frequency_mhz / 4500.0) * 8.0) if cpu.frequency_mhz > 0 else 5.0
        cpu_score = min(35.0, cores_pts + simd_pts + fma_pts + clock_pts)

        # GPU component (up to 20 pts)
        gpu_score = 0.0
        if gpu.present:
            if gpu.vendor == "nvidia" and gpu.total_vram_mb >= 8192:
                gpu_score = 20.0
            elif gpu.vendor == "nvidia" and gpu.total_vram_mb >= 4096:
                gpu_score = 16.0
            elif gpu.vendor == "amd" and gpu.total_vram_mb >= 4096:
                gpu_score = 15.0
            elif gpu.total_vram_mb >= 2048:
                gpu_score = 10.0
            else:
                gpu_score = 5.0

        return min(100.0, mem_score + cpu_score + gpu_score)

    def _classify_compute_tier(self, score: float, mem: MemoryInfo, gpu: GPUInfo) -> str:
        """Classify machine into compute capability tiers."""
        if mem.total_mb < 2048:
            return "Tier-0-Micro (Pure Rules / 0-RAM Model)"
        elif mem.total_mb < 4096:
            return "Tier-1-Constrained (360M - 0.5B GGUF)"
        elif mem.total_mb < 8192 and (not gpu.present or gpu.total_vram_mb < 4096):
            return "Tier-2-Balanced (1.5B GGUF)"
        elif mem.total_mb < 16384 and (not gpu.present or gpu.total_vram_mb < 6144):
            return "Tier-3-Workstation (3B - 7B GGUF)"
        else:
            return "Tier-4-HighPerformance (7B - 14B GGUF / GPU Accelerated)"
