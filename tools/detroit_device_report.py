#!/usr/bin/env python3
"""Turn a Madeira Detroit physical-gate log into a plain-English report.

Read-only. This tool does not create qualification proof and never upgrades a
failed/incomplete run to PASS. It only interprets stable key=value markers that
were emitted by the x86-64 Windows canaries/controller on the physical device.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from dataclasses import asdict, dataclass

SCHEMA = "MADEIRA_DETROIT_DEVICE_REPORT_V1"
REQUIRED_CAPABILITY_MARKERS = (
    "DETROIT_VULKAN_1_1_LOADER",
    "DETROIT_VULKAN_1_1_DEVICE",
    "DETROIT_COMPUTE_QUEUE",
    "DETROIT_DESCRIPTOR_INDEXING",
    "DETROIT_CAPABILITIES",
)


@dataclass(frozen=True)
class Finding:
    status: str
    name: str
    explanation: str


def _human_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    number = float(value)
    for unit in units:
        if number < 1024.0 or unit == units[-1]:
            return f"{number:.2f} {unit}"
        number /= 1024.0
    return f"{value} B"


def _last_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if re.fullmatch(r"[A-Z0-9_]+", key):
            values[key] = value.strip()
    return values


def analyze(text: str) -> dict[str, object]:
    values = _last_values(text)
    findings: list[Finding] = []

    failed_gate = values.get("FAILED_GATE")
    overall = values.get("OVERALL")
    proof = values.get("PROOF_RESULT")

    if overall == "PASS" and proof == "PASS":
        run_status = "PHYSICAL_GATE_PASS"
    elif overall == "FAIL":
        run_status = "PHYSICAL_GATE_FAIL"
    else:
        run_status = "INCOMPLETE_OR_NO_GATE_RESULT"

    for marker in REQUIRED_CAPABILITY_MARKERS:
        value = values.get(marker)
        if value == "PASS":
            findings.append(Finding("PASS", marker, "Passed on the recorded Windows/Vulkan path."))
        elif value is not None:
            findings.append(Finding("FAIL", marker, f"Recorded value was {value!r}, not PASS."))
        else:
            findings.append(Finding("INFO", marker, "No stable marker was found in this log."))

    loader_api = values.get("LOADER_API")
    gpu_api = values.get("GPU_0_API")
    gpu_name = values.get("GPU_0_NAME")
    if loader_api:
        findings.append(Finding("INFO", "Vulkan loader version", loader_api))
    if gpu_api:
        findings.append(Finding("INFO", "Physical Vulkan device version", gpu_api))
    if gpu_name:
        findings.append(Finding("INFO", "Vulkan GPU", gpu_name))

    compute = values.get("COMPUTE_QUEUE_FAMILY")
    dedicated = values.get("DEDICATED_COMPUTE_QUEUE_FAMILY")
    if compute is not None:
        findings.append(Finding("INFO", "Compute-capable queue", compute))
    if dedicated is not None:
        explanation = dedicated
        if dedicated == "NONE":
            explanation = "None reported. This is recorded evidence only; Detroit qualification does not require a separate dedicated compute queue."
        findings.append(Finding("INFO", "Dedicated compute queue", explanation))

    descriptor_fields = (
        "DESCRIPTOR_INDEXING_SHADER_UNIFORM_BUFFER_NONUNIFORM",
        "DESCRIPTOR_INDEXING_SHADER_SAMPLED_IMAGE_NONUNIFORM",
        "DESCRIPTOR_INDEXING_SHADER_STORAGE_BUFFER_NONUNIFORM",
        "DESCRIPTOR_INDEXING_SHADER_STORAGE_IMAGE_NONUNIFORM",
        "DESCRIPTOR_INDEXING_PARTIALLY_BOUND",
        "DESCRIPTOR_INDEXING_VARIABLE_COUNT",
        "DESCRIPTOR_INDEXING_RUNTIME_ARRAY",
    )
    descriptor_evidence = {key: values[key] for key in descriptor_fields if key in values}

    budget_heaps: list[dict[str, object]] = []
    heap_count_text = values.get("MEMORY_BUDGET_HEAP_COUNT")
    if heap_count_text and heap_count_text.isdigit():
        for index in range(int(heap_count_text)):
            budget_text = values.get(f"MEMORY_BUDGET_HEAP_{index}_BUDGET_BYTES")
            usage_text = values.get(f"MEMORY_BUDGET_HEAP_{index}_USAGE_BYTES")
            plus_text = values.get(f"MEMORY_BUDGET_HEAP_{index}_BUDGET_PLUS_USAGE_BYTES")
            row: dict[str, object] = {"heap": index}
            for label, raw in (("budget", budget_text), ("usage", usage_text), ("budget_plus_usage", plus_text)):
                if raw and raw.isdigit():
                    number = int(raw)
                    row[f"{label}_bytes"] = number
                    row[f"{label}_human"] = _human_bytes(number)
            budget_heaps.append(row)

    memory_semantics = values.get("MEMORY_BUDGET_SEMANTICS")
    memory_telemetry = values.get("MEMORY_BUDGET_TELEMETRY")
    if memory_telemetry:
        findings.append(Finding(
            "INFO",
            "Vulkan memory-budget telemetry",
            f"{memory_telemetry}. Treat these MoltenVK/iOS values as telemetry only, not fixed VRAM or a qualification threshold.",
        ))

    first_failure_plain = None
    if failed_gate:
        first_failure_plain = {
            "payload-fingerprint": "The bundled Windows test/runtime identity could not be verified.",
            "vulkan-device": "The Detroit Vulkan capability/device stage failed. Check Vulkan 1.1, compute support, descriptor indexing, and the Wine/MoltenVK device path first.",
            "win32-surface": "The Vulkan device stage passed, but the Windows-window to iPad Metal-surface stage failed.",
            "present-120": "The surface stage passed, but 120 consecutive presented frames did not complete.",
            "foreground-integrity": "Madeira left the foreground during qualification; rerun while keeping it active.",
            "proof-publication": "The graphics stages passed, but trustworthy PASS proof could not be saved.",
        }.get(failed_gate, f"The first reported failed gate was {failed_gate!r}.")
        findings.append(Finding("FAIL", "First failed gate", first_failure_plain))

    report: dict[str, object] = {
        "schema": SCHEMA,
        "run_status": run_status,
        "overall_marker": overall,
        "proof_marker": proof,
        "failed_gate": failed_gate,
        "payload_fingerprint": values.get("PAYLOAD_FNV64"),
        "gpu_name": gpu_name,
        "loader_api": loader_api,
        "gpu_api": gpu_api,
        "descriptor_indexing_evidence": descriptor_evidence,
        "memory_budget_semantics": memory_semantics,
        "memory_budget_heaps": budget_heaps,
        "findings": [asdict(item) for item in findings],
        "notes": [
            "This report does not create or validate Madeira's durable physical-device proof file.",
            "A successful text report is not evidence that Detroit itself runs on iPad.",
            "VK_EXT_memory_budget values are implementation-dependent and are treated as telemetry only on MoltenVK/iOS.",
            "The next game gate remains Detroit process start and shader compilation only after current physical graphics proof is accepted by Madeira.",
        ],
    }
    return report


def render(report: dict[str, object]) -> str:
    lines = ["# Detroit physical graphics report", "", f"Run: {report['run_status']}"]
    gpu = report.get("gpu_name")
    if gpu:
        lines.append(f"GPU: {gpu}")
    loader = report.get("loader_api")
    device = report.get("gpu_api")
    if loader or device:
        lines.append(f"Vulkan: loader {loader or 'unknown'}; device {device or 'unknown'}")
    failed = report.get("failed_gate")
    if failed:
        lines.append(f"First failed gate: {failed}")
    lines.append("")

    findings = report.get("findings", [])
    if isinstance(findings, list):
        for raw in findings:
            if not isinstance(raw, dict):
                continue
            lines.append(f"[{raw.get('status')}] {raw.get('name')}: {raw.get('explanation')}")

    heaps = report.get("memory_budget_heaps", [])
    if isinstance(heaps, list) and heaps:
        lines.extend(("", "Vulkan memory-budget telemetry (not a pass/fail threshold):"))
        for row in heaps:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"  heap {row.get('heap')}: budget={row.get('budget_human', 'unknown')}, "
                f"usage={row.get('usage_human', 'unknown')}, "
                f"budget+usage={row.get('budget_plus_usage_human', 'unknown')}"
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=pathlib.Path)
    parser.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = parser.parse_args()

    text = args.log.read_text(encoding="utf-8", errors="replace")
    report = analyze(text)
    if args.json_path:
        args.json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
