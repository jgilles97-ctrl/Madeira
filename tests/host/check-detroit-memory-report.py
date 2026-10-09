#!/usr/bin/env python3
"""Host fixtures for tools/detroit_memory_report.py."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "detroit_memory_report.py"
spec = importlib.util.spec_from_file_location("detroit_memory_report", TOOL)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_shader_checkpoints() -> None:
    text = "\n".join(
        [
            "[device-memory] available-mib=2100.0 footprint-mib=1800.0 peak-mib=1810.0",
            "Compiling Shaders 50%",
            "[device-memory] available-mib=1500.0 footprint-mib=2400.0 peak-mib=2410.0",
            "Compiling Shaders 90%",
            "[device-memory] available-mib=720.0 footprint-mib=3200.0 peak-mib=3210.0",
            "Compiling Shaders 98%",
            "[device-memory] available-mib=610.0 footprint-mib=3330.0 peak-mib=3350.0",
            "Compiling Shaders 100%",
        ]
    )
    report = mod.render(text)
    require("Samples: 4" in report, "sample count missing")
    require("minimum 610.0 MiB" in report, "minimum headroom missing")
    require("Highest shader progress seen: 100%" in report, "shader max missing")
    require("No explicit memory-pressure signature" in report, "clean-run interpretation missing")
    require("Late shader-cache pattern" not in report, "clean run was falsely labeled as late cache failure")


def test_pressure_is_blocked() -> None:
    text = "\n".join(
        [
            "[device-memory] available-mib=500.0 footprint-mib=3500.0 peak-mib=3510.0",
            "Compiling Shaders 98%",
            "jetsam: killed for memory pressure",
        ]
    )
    report = mod.render(text)
    require("Memory-pressure signatures: 1" in report, "pressure count missing")
    require("BLOCKED:" in report, "pressure run not marked blocked")
    require("Late shader-cache pattern" in report, "late 98% memory failure pattern not identified")
    require("Keep shader compression enabled" in report, "compression recovery guidance missing")
    require("MSL library cache disabled" in report, "8 GB MSL cache guidance missing")


def test_moltenvk_gpu_oom_is_pressure() -> None:
    text = "\n".join(
        [
            "[device-memory] available-mib=430.0 footprint-mib=3650.0 peak-mib=3660.0",
            "Compiling Shaders 99%",
            "[mvk-error] VK_ERROR_OUT_OF_DEVICE_MEMORY: MTLCommandBuffer execution failed (kIOGPUCommandBufferCallbackErrorOutOfMemory)",
        ]
    )
    samples, progress, pressure = mod.parse(text)
    require(len(samples) == 1, "MoltenVK fixture memory sample missing")
    require(progress[-1][1] == 99, "MoltenVK fixture shader progress missing")
    require(len(pressure) == 1, "MoltenVK GPU OOM not recognized as memory pressure")
    report = mod.render(text)
    require("Late shader-cache pattern" in report, "late MoltenVK GPU OOM not connected to shader phase")


def test_early_pressure_does_not_claim_late_cache_pattern() -> None:
    text = "\n".join(
        [
            "[device-memory] available-mib=900.0 footprint-mib=2500.0 peak-mib=2510.0",
            "Compiling Shaders 50%",
            "VK_ERROR_OUT_OF_HOST_MEMORY",
        ]
    )
    report = mod.render(text)
    require("BLOCKED:" in report, "early pressure not blocked")
    require("Late shader-cache pattern" not in report, "early OOM falsely attributed to late cache-save phase")


def test_missing_samples_explains_profile() -> None:
    report = mod.render("Compiling Shaders 90%\n")
    require("No `[device-memory]` samples were found" in report, "missing-sample explanation absent")
    require("detroit-m4-8gb.cfg" in report, "profile recovery hint absent")


def main() -> int:
    for test in (
        test_shader_checkpoints,
        test_pressure_is_blocked,
        test_moltenvk_gpu_oom_is_pressure,
        test_early_pressure_does_not_claim_late_cache_pattern,
        test_missing_samples_explains_profile,
    ):
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
