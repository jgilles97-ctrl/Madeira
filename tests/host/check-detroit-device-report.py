#!/usr/bin/env python3
"""Host fixtures for tools/detroit_device_report.py."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/detroit_device_report.py"
spec = importlib.util.spec_from_file_location("detroit_device_report", TOOL)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_pass_report() -> None:
    text = """
LOADER_API=1.3.280
GPU_0_NAME=Apple M4
GPU_0_API=1.3.280
DETROIT_VULKAN_1_1_LOADER=PASS
DETROIT_VULKAN_1_1_DEVICE=PASS
COMPUTE_QUEUE_FAMILY=0
DEDICATED_COMPUTE_QUEUE_FAMILY=NONE
DETROIT_COMPUTE_QUEUE=PASS
DETROIT_DESCRIPTOR_INDEXING=PASS
DETROIT_CAPABILITIES=PASS
DESCRIPTOR_INDEXING_RUNTIME_ARRAY=1
MEMORY_BUDGET_HEAP_COUNT=1
MEMORY_BUDGET_HEAP_0_BUDGET_BYTES=4294967296
MEMORY_BUDGET_HEAP_0_USAGE_BYTES=1073741824
MEMORY_BUDGET_HEAP_0_BUDGET_PLUS_USAGE_BYTES=5368709120
MEMORY_BUDGET_SEMANTICS=TELEMETRY_ONLY_MOLTENVK_IOS
MEMORY_BUDGET_TELEMETRY=PASS
PAYLOAD_FNV64=0123456789abcdef
PROOF_RESULT=PASS
OVERALL=PASS
"""
    report = mod.analyze(text)
    require(report["run_status"] == "PHYSICAL_GATE_PASS", "full pass was not recognized")
    require(report["gpu_name"] == "Apple M4", "GPU name missing")
    require(report["descriptor_indexing_evidence"]["DESCRIPTOR_INDEXING_RUNTIME_ARRAY"] == "1",
            "descriptor evidence missing")
    heaps = report["memory_budget_heaps"]
    require(len(heaps) == 1, "memory-budget heap missing")
    require(heaps[0]["budget_human"] == "4.00 GiB", "budget humanization incorrect")
    rendered = mod.render(report)
    require("telemetry (not a pass/fail threshold)" in rendered, "memory telemetry caveat missing")
    require("None reported" in rendered, "dedicated-compute optional explanation missing")


def test_first_failure() -> None:
    text = """
DETROIT_VULKAN_1_1_LOADER=PASS
DETROIT_VULKAN_1_1_DEVICE=PASS
FAILED_GATE=win32-surface
PROOF_RESULT=NOT_WRITTEN
OVERALL=FAIL
"""
    report = mod.analyze(text)
    require(report["run_status"] == "PHYSICAL_GATE_FAIL", "failure was not recognized")
    require(report["failed_gate"] == "win32-surface", "first failure missing")
    rendered = mod.render(report)
    require("Windows-window to iPad Metal-surface" in rendered, "plain surface failure explanation missing")


def test_incomplete_never_promotes() -> None:
    text = "DETROIT_CAPABILITIES=PASS\nVULKAN_DEVICE=PASS\n"
    report = mod.analyze(text)
    require(report["run_status"] == "INCOMPLETE_OR_NO_GATE_RESULT",
            "partial markers were incorrectly promoted to physical PASS")


def test_last_value_wins() -> None:
    text = "OVERALL=FAIL\nOVERALL=PASS\nPROOF_RESULT=PASS\n"
    report = mod.analyze(text)
    require(report["run_status"] == "PHYSICAL_GATE_PASS", "latest stable marker should win")


def main() -> int:
    for test in (test_pass_report, test_first_failure, test_incomplete_never_promotes, test_last_value_wins):
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
