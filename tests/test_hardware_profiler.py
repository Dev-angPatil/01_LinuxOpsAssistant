"""Unit tests for Hardware Profiler, Benchmarking, Model Selector & Capability Pruning."""

import os
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from ops_assistant.hardware.profiler import (
    HardwareProfiler, CPUInfo, MemoryInfo, GPUInfo, StorageInfo, HardwareProfile
)
from ops_assistant.hardware.advisor import (
    HardwareAdvisor, ModelSelector, CapabilityMatrix, ModelTier, MODEL_CATALOG
)


class TestHardwareProfiler(unittest.TestCase):
    def setUp(self):
        self.profiler = HardwareProfiler()

    def test_inspect_cpu_live(self):
        cpu = self.profiler.inspect_cpu()
        self.assertIsInstance(cpu, CPUInfo)
        self.assertGreater(cpu.logical_cores, 0)
        self.assertGreater(cpu.physical_cores, 0)
        self.assertIsInstance(cpu.flags, list)
        self.assertIsInstance(cpu.has_avx2, bool)

    def test_inspect_memory_live(self):
        mem = self.profiler.inspect_memory()
        self.assertIsInstance(mem, MemoryInfo)
        self.assertGreater(mem.total_mb, 0.0)
        self.assertGreaterEqual(mem.available_mb, 0.0)
        self.assertGreaterEqual(mem.safe_model_headroom_mb, 0.0)

    def test_inspect_gpu_live(self):
        gpu = self.profiler.inspect_gpu()
        self.assertIsInstance(gpu, GPUInfo)
        self.assertIn(gpu.vendor, ["nvidia", "amd", "intel", "apple", "generic", "cpu_fallback"])
        self.assertGreaterEqual(gpu.total_vram_mb, 0.0)

    def test_inspect_storage_live(self):
        storage = self.profiler.inspect_storage()
        self.assertIsInstance(storage, StorageInfo)
        self.assertGreater(storage.total_gb, 0.0)
        self.assertGreaterEqual(storage.available_gb, 0.0)

    def test_profile_live(self):
        profile = self.profiler.profile()
        self.assertIsInstance(profile, HardwareProfile)
        self.assertGreater(profile.hardware_score, 0.0)
        self.assertIn("Tier", profile.compute_tier)
        d = profile.to_dict()
        self.assertIn("cpu", d)
        self.assertIn("memory", d)
        self.assertIn("gpu", d)
        self.assertIn("storage", d)

    def test_model_selector_micro_ram(self):
        # Mock constrained system with 1GB RAM
        prof = HardwareProfile(
            timestamp=1000.0,
            cpu=CPUInfo(architecture="x86_64", logical_cores=2),
            memory=MemoryInfo(total_mb=1024.0, available_mb=500.0, safe_model_headroom_mb=350.0),
            gpu=GPUInfo(present=False),
            storage=StorageInfo(available_gb=10.0)
        )
        rec = ModelSelector.recommend_model(prof)
        self.assertIsNone(rec["model_key"])
        self.assertFalse(rec["download_required"])
        self.assertEqual(rec["tier"], ModelTier.TIER_0.value)
        self.assertIn("Deterministic", rec["name"])

    def test_model_selector_lightweight_ram(self):
        # Mock 3GB RAM system
        prof = HardwareProfile(
            timestamp=1000.0,
            cpu=CPUInfo(architecture="x86_64", logical_cores=4, has_avx2=True),
            memory=MemoryInfo(total_mb=3072.0, available_mb=2000.0, safe_model_headroom_mb=1400.0),
            gpu=GPUInfo(present=False),
            storage=StorageInfo(available_gb=50.0)
        )
        rec = ModelSelector.recommend_model(prof)
        self.assertIn(rec["model_key"], ["qwen2.5-coder-0.5b", "smollm2-360m"])
        self.assertTrue(rec["download_required"])

    def test_model_selector_high_end_workstation(self):
        # Mock 32GB RAM + NVIDIA GPU with 12GB VRAM
        prof = HardwareProfile(
            timestamp=1000.0,
            cpu=CPUInfo(architecture="x86_64", logical_cores=16, has_avx2=True, has_fma=True),
            memory=MemoryInfo(total_mb=32768.0, available_mb=24000.0, safe_model_headroom_mb=16800.0),
            gpu=GPUInfo(present=True, vendor="nvidia", device_name="NVIDIA RTX 4080", total_vram_mb=16384.0, free_vram_mb=12000.0),
            storage=StorageInfo(available_gb=200.0)
        )
        rec = ModelSelector.recommend_model(prof)
        self.assertIn(rec["model_key"], ["deepseek-r1-distill-qwen-7b", "qwen2.5-coder-7b", "mistral-7b-instruct"])
        self.assertIn("GPU Accelerated", rec["acceleration"])

    def test_capability_matrix_generation(self):
        advisor = HardwareAdvisor(profiler=self.profiler)
        prof = self.profiler.profile()
        caps = advisor.generate_capability_matrix(prof)
        self.assertIsInstance(caps, CapabilityMatrix)
        self.assertGreater(len(caps.features_to_keep), 0)
        self.assertGreater(caps.recommended_threads, 0)
        self.assertIn(caps.recommended_ctx_size, [2048, 4096])

    def test_full_advisory(self):
        advisor = HardwareAdvisor(profiler=self.profiler)
        adv = advisor.get_full_advisory()
        self.assertIn("profile", adv)
        self.assertIn("recommended_model", adv)
        self.assertIn("capability_matrix", adv)
        self.assertIn("all_compatible_models", adv)


if __name__ == "__main__":
    unittest.main()
