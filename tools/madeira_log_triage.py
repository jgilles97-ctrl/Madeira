#!/usr/bin/env python3
"""Offline triage for Madeira diagnostic logs.

This utility is intentionally read-only and dependency-free. It recognizes
high-signal Madeira markers, Detroit/MoltenVK shader failure signatures, and the
Detroit physical-device Vulkan gate, then turns them into a compact, redacted
summary for bug reports and device comparison.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from dataclasses import dataclass
from typing import Iterable

SCHEMA = "MADEIRA_LOG_TRIAGE_V2"
DETROIT_GATE_SCHEMA = "MADEIRA_DETROIT_DEVICE_GATE_V1"
SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "INFO": 3}
DETROIT_GATE_ORDER = ("vulkan-device", "win32-surface", "present-120")
DETROIT_GATE_GUIDANCE = {
    "vulkan-device": (
        "The failure is before visible rendering. Inspect vulkan-1.dll / winevulkan loading, "
        "MoltenVK startup, GPU enumeration, and logical-device creation before changing Detroit itself."
    ),
    "win32-surface": (
        "The Vulkan device worked, so focus on the Wine Win32-surface -> Madeira CAMetalLayer -> "
        "VkMetalSurfaceEXT bridge and presentation support."
    ),
    "present-120": (
        "Device and surface creation worked. Focus on swapchain creation, acquire/submit/present, "
        "Metal-layer lifetime, and any memory/thermal failure during sustained presentation."
    ),
    "payload-fingerprint": (
        "The fixed x64 test payload could not be identified. Rebuild/stage the four Detroit canaries "
        "before interpreting any graphics result."
    ),
    "foreground-integrity": (
        "The graphics stages ran, but Madeira left the iOS foreground during the test. Re-run the "
        "Detroit graphics test and keep Madeira visible until it finishes; do not count this run as proof."
    ),
    "proof-publication": (
        "The graphics stages passed but the durable physical-device proof could not be written. Fix the "
        "proof-file failure and rerun before unlocking Detroit itself."
    ),
}


@dataclass(frozen=True)
class Rule:
    code: str
    severity: str
    title: str
    pattern: re.Pattern[str]
    guidance: str


RULES: tuple[Rule, ...] = (
    Rule(
        "jit_debugger_missing_at_pool_request",
        "CRITICAL",
        "Debugger was not attached when Madeira requested the JIT pool",
        re.compile(r"\[jit-debugger\]\s*attached=0\s+at the pool request", re.I),
        "Re-run Madeira through its Enable JIT flow so StikDebug is attached at the pool request.",
    ),
    Rule(
        "jit_pool_address_space_failure",
        "HIGH",
        "JIT pool allocation hit an address-space failure",
        re.compile(r"(?:jit.{0,40}pool.{0,80}(?:fail|kern_no_space|no space)|kern_no_space.{0,80}jit)", re.I),
        "Capture the surrounding JIT/Memory+ lines and device/iPadOS version; this can distinguish entitlement/VA-map failures.",
    ),
    Rule(
        "windows_access_violation",
        "HIGH",
        "Windows process reported STATUS_ACCESS_VIOLATION (0xC0000005)",
        re.compile(r"(?:0x)?c0000005", re.I),
        "Include the first access-violation line and nearby module/PC lines in the upstream report.",
    ),
    Rule(
        "windows_out_of_memory",
        "HIGH",
        "Windows process reported STATUS_NO_MEMORY (0xC0000017)",
        re.compile(r"(?:0x)?c0000017", re.I),
        "Check Memory+ state and include footprint/allocation lines around the failure.",
    ),
    Rule(
        "teb_tsd_regression",
        "CRITICAL",
        "Possible TEB/TSD-slot regression",
        re.compile(r"(?:slot\s*275|teb\s*=\s*(?:0x)?0\b|null\s+teb|tsd.{0,40}mismatch)", re.I),
        "This resembles a historical M4-iPad TEB/TSD failure. Record build SHA and exact iPadOS/device before filing.",
    ),
    Rule(
        "stikdebug_pid_protocol_error",
        "HIGH",
        "StikDebug/JIT launch returned an unexpected PID response",
        re.compile(r"(?:expected\s+integer\s+pid|unexpectedresponse.{0,80}pid)", re.I),
        "Record the StikDebug version, Madeira build, and the complete launch-response line.",
    ),
    Rule(
        "steam_invalid_platform_29",
        "MEDIUM",
        "Steam launch refusal 29 / invalid platform",
        re.compile(r"(?:launch\s+refusal\s*29|invalid\s+platform|(?:error|code)\s*29\b)", re.I),
        "Treat this as a launch/load failure signal; include preceding Madeira load error lines.",
    ),
    Rule(
        "moltenvk_shader_address_space_compile",
        "HIGH",
        "MoltenVK/MSL rejected a Detroit-style shader address-space declaration",
        re.compile(r"automatic\s+variable\s+qualified\s+with\s+an\s+address\s+space", re.I),
        "This exact shader-compile signature appeared in Detroit compatibility work. Keep Metal argument buffers enabled, "
        "record the MoltenVK/SPIRV-Cross build, and fix the translation layer rather than patching the game binary.",
    ),
    Rule(
        "metal_buffer_index_limit",
        "HIGH",
        "Metal shader buffer index exceeded the 0-30 direct-buffer range",
        re.compile(r"['\"]?buffer['\"]?\s+attribute\s+parameter\s+is\s+out\s+of\s+bounds.{0,80}between\s+0\s+and\s+30", re.I),
        "Detroit reports this when the argument-buffer route is disabled. Do not use MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS=0 "
        "as a blanket workaround; return to the argument-buffer path and diagnose its shader translation instead.",
    ),
    Rule(
        "detroit_r32uint_blend_validation",
        "HIGH",
        "Detroit hit Metal R32Uint blending validation",
        re.compile(r"(?:blending\s+is\s+enabled.{0,160}MTLPixelFormatR32Uint.{0,100}not\s+blendable|MTLPixelFormatR32Uint.{0,160}not\s+blendable)", re.I),
        "This is a known Detroit/MoltenVK pipeline incompatibility. Capture the full pipeline error and compare the pinned "
        "Detroit MoltenVK fork before changing game assets or disabling unrelated graphics features.",
    ),
    Rule(
        "detroit_r32uint_output_mismatch",
        "HIGH",
        "Detroit shader output type did not match an R32Uint Metal attachment",
        re.compile(r"output\s+of\s+type\s+float4.{0,120}not\s+compatible.{0,120}MTLPixelFormatR32Uint", re.I),
        "This exact first-scene Detroit signature has been reported in MoltenVK testing. Treat it as a render-pipeline "
        "translation/compatibility blocker, not a generic FEX or Wine crash.",
    ),
    Rule(
        "moltenvk_device_lost",
        "HIGH",
        "MoltenVK/Vulkan reported a lost GPU device",
        re.compile(r"(?:VK_ERROR_DEVICE_LOST|Lost\s+VkDevice\s+after\s+MTLCommandBuffer)", re.I),
        "Check the same lines for GPU timeout, address fault, out-of-memory, or background/NotPermitted details. On iOS, "
        "also verify Madeira stayed in the foreground for the entire graphics run before changing Detroit itself.",
    ),
    Rule(
        "moltenvk_gpu_memory_failure",
        "HIGH",
        "MoltenVK/Metal reported GPU or Vulkan memory exhaustion",
        re.compile(r"(?:kIOGPUCommandBufferCallbackErrorOutOfMemory|VK_ERROR_OUT_OF_(?:DEVICE|HOST)_MEMORY)", re.I),
        "Treat memory as the primary blocker. Correlate this timestamp with [device-memory] footprint/available-memory lines "
        "and keep Detroit's shader compression and 720p/30 memory-first profile enabled for the next A/B run.",
    ),
)

POSITIVE_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "jit_debugger_attached_at_pool_request",
        "Debugger attached at JIT pool request",
        re.compile(r"\[jit-debugger\]\s*attached=1\s+at the pool request", re.I),
    ),
    (
        "clean_x64_probe",
        "x64 probe reported clean execution",
        re.compile(r"(?:cube-x64\s+clean|0\s+segv\b|0\s+c0000005\b)", re.I),
    ),
)


def redact_line(line: str) -> str:
    line = re.sub(
        r"/var/mobile/Containers/Data/Application/[0-9A-Fa-f-]{16,}",
        "/var/mobile/Containers/Data/Application/[REDACTED]",
        line,
    )
    line = re.sub(r"/Users/[^/\s]+", "/Users/[REDACTED]", line)
    line = re.sub(
        r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/-]+",
        r"\1[REDACTED]",
        line,
    )
    line = re.sub(
        r"(?i)\b(token|api[_-]?key|secret|password)\b\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        line,
    )
    return line.rstrip("\n")


def _samples(matches: Iterable[tuple[int, str]], limit: int = 3) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for line_no, raw in matches:
        out.append({"line": line_no, "text": redact_line(raw)})
        if len(out) >= limit:
            break
    return out


def _last_value(lines: list[str], key: str) -> str | None:
    prefix = key + "="
    for line in reversed(lines):
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()
    return None


def _parse_detroit_gate(lines: list[str]) -> dict[str, object]:
    """Parse only the newest Detroit gate attempt from a potentially long log."""
    starts = [i for i, line in enumerate(lines) if line.strip() == f"SCHEMA={DETROIT_GATE_SCHEMA}"]
    if not starts:
        return {"detected": False}

    start = starts[-1]
    gate_lines = lines[start:]
    stages: list[dict[str, object]] = []
    for stage_name in DETROIT_GATE_ORDER:
        stage: dict[str, object] = {"name": stage_name, "status": "NOT_REPORTED"}
        result_prefix = f"GATE_RESULT={stage_name}:"
        exit_prefix = f"GATE_CHILD_EXIT={stage_name}:"
        current_stage: str | None = None
        for raw in gate_lines:
            line = raw.strip()
            if line.startswith("GATE_BEGIN="):
                current_stage = line.split("=", 1)[1]
            if line.startswith(result_prefix):
                stage["status"] = line[len(result_prefix):].strip()
            elif line.startswith(exit_prefix):
                stage["exit_code"] = line[len(exit_prefix):].strip()
            elif current_stage == stage_name and line.startswith("GATE_ERROR="):
                stage["error"] = line.split("=", 1)[1].strip()
        stages.append(stage)

    overall = _last_value(gate_lines, "OVERALL") or "INCOMPLETE"
    failed_gate = _last_value(gate_lines, "FAILED_GATE")
    next_gate = _last_value(gate_lines, "NEXT_GATE")
    final_markers = {
        "vulkan_device": _last_value(gate_lines, "VULKAN_DEVICE"),
        "win32_surface": _last_value(gate_lines, "WIN32_SURFACE"),
        "presented_120_frames": _last_value(gate_lines, "PRESENTED_120_FRAMES"),
        "foreground_integrity": _last_value(gate_lines, "FOREGROUND_INTEGRITY"),
    }
    proof_complete = (
        overall == "PASS"
        and final_markers["vulkan_device"] == "PASS"
        and final_markers["win32_surface"] == "PASS"
        and final_markers["presented_120_frames"] == "PASS"
        and final_markers["foreground_integrity"] == "PASS"
        and all(stage["status"] == "PASS" for stage in stages)
    )

    return {
        "detected": True,
        "schema": DETROIT_GATE_SCHEMA,
        "start_line": start + 1,
        "overall": overall,
        "proof_complete": proof_complete,
        "failed_gate": failed_gate,
        "next_gate": next_gate,
        "stages": stages,
        "final_markers": final_markers,
    }


def triage_text(text: str) -> dict[str, object]:
    lines = text.splitlines()
    findings: list[dict[str, object]] = []

    for rule in RULES:
        hits = [(i, line) for i, line in enumerate(lines, start=1) if rule.pattern.search(line)]
        if hits:
            findings.append(
                {
                    "code": rule.code,
                    "severity": rule.severity,
                    "title": rule.title,
                    "count": len(hits),
                    "samples": _samples(hits),
                    "guidance": rule.guidance,
                }
            )

    detroit_gate = _parse_detroit_gate(lines)
    if detroit_gate.get("detected"):
        overall = str(detroit_gate.get("overall", "INCOMPLETE"))
        failed_gate = detroit_gate.get("failed_gate")
        if overall == "FAIL":
            gate_name = str(failed_gate or "unknown")
            guidance = DETROIT_GATE_GUIDANCE.get(
                gate_name,
                "Inspect the newest gate attempt from its first GATE_BEGIN line; do not launch Detroit until this gate is understood.",
            )
            gate_start = int(detroit_gate.get("start_line", 1))
            failure_hits = [
                (i, line)
                for i, line in enumerate(lines, start=1)
                if i >= gate_start and (
                    line.strip() == "OVERALL=FAIL"
                    or line.startswith("GATE_ERROR=")
                    or line.startswith("FOREGROUND_INTEGRITY=FAIL")
                    or line.startswith("PROOF_ERROR=")
                    or line.startswith("PAYLOAD_HASH_ERROR=")
                )
            ]
            findings.append(
                {
                    "code": "detroit_device_gate_failed",
                    "severity": "HIGH",
                    "title": f"Detroit physical-device Vulkan gate failed at {gate_name}",
                    "count": 1,
                    "samples": _samples(failure_hits),
                    "guidance": guidance,
                }
            )
        elif overall != "PASS" or not detroit_gate.get("proof_complete"):
            gate_start = int(detroit_gate.get("start_line", 1))
            findings.append(
                {
                    "code": "detroit_device_gate_incomplete",
                    "severity": "MEDIUM",
                    "title": "Detroit physical-device Vulkan gate did not produce complete proof",
                    "count": 1,
                    "samples": _samples([(gate_start, lines[gate_start - 1])]),
                    "guidance": (
                        "Run the gate to completion and require all three stage PASS results, FOREGROUND_INTEGRITY=PASS, "
                        "VULKAN_DEVICE=PASS, WIN32_SURFACE=PASS, PRESENTED_120_FRAMES=PASS, and OVERALL=PASS."
                    ),
                }
            )

    positive_signals: list[dict[str, object]] = []
    for code, title, pattern in POSITIVE_RULES:
        hits = [(i, line) for i, line in enumerate(lines, start=1) if pattern.search(line)]
        if hits:
            positive_signals.append(
                {"code": code, "title": title, "count": len(hits), "samples": _samples(hits)}
            )

    if detroit_gate.get("proof_complete"):
        positive_signals.append(
            {
                "code": "detroit_device_gate_passed",
                "title": "Detroit local Vulkan device gate proved all three physical-device stages in the foreground",
                "count": 1,
                "samples": [],
            }
        )

    findings.sort(key=lambda f: (SEVERITY_ORDER[str(f["severity"])], str(f["code"])))
    severity_counts = {sev: 0 for sev in SEVERITY_ORDER}
    for finding in findings:
        severity_counts[str(finding["severity"])] += 1

    return {
        "schema": SCHEMA,
        "line_count": len(lines),
        "finding_count": len(findings),
        "severity_counts": severity_counts,
        "findings": findings,
        "positive_signals": positive_signals,
        "detroit_device_gate": detroit_gate,
        "notes": [
            "Heuristic summary only: a matching line is evidence to inspect, not proof of root cause.",
            "Detroit gate PASS is accepted only from the newest gate attempt and only when stage/final/foreground markers agree.",
            "The tool is offline/read-only and redacts common local paths and secret-like values from samples.",
        ],
    }


def render_text(report: dict[str, object], source: pathlib.Path) -> str:
    counts = report["severity_counts"]
    assert isinstance(counts, dict)
    lines = [
        "# Madeira Log Triage",
        "",
        f"Source: `{source.name}`",
        f"Lines: {report['line_count']}",
        f"Findings: {report['finding_count']}",
        "Severity: "
        + ", ".join(f"{sev}={counts.get(sev, 0)}" for sev in ("CRITICAL", "HIGH", "MEDIUM", "INFO")),
        "",
    ]

    gate = report.get("detroit_device_gate")
    if isinstance(gate, dict) and gate.get("detected"):
        overall = gate.get("overall", "INCOMPLETE")
        lines += ["## Detroit physical-device Vulkan gate", f"Overall: **{overall}**"]
        stages = gate.get("stages", [])
        if isinstance(stages, list):
            for stage in stages:
                if not isinstance(stage, dict):
                    continue
                detail = f"- {stage.get('name')}: {stage.get('status', 'NOT_REPORTED')}"
                if stage.get("exit_code"):
                    detail += f" (child exit {stage['exit_code']})"
                if stage.get("error"):
                    detail += f" — {redact_line(str(stage['error']))}"
                lines.append(detail)
        markers = gate.get("final_markers")
        if isinstance(markers, dict):
            lines.append(f"- Foreground integrity: {markers.get('foreground_integrity') or 'NOT_REPORTED'}")
        if gate.get("failed_gate"):
            lines.append(f"- First failed gate: `{gate['failed_gate']}`")
        if gate.get("next_gate"):
            lines.append(f"- Next gate: `{gate['next_gate']}`")
        if gate.get("proof_complete"):
            lines.append("- Proof status: complete — device, Windows surface, 120-frame presentation, and foreground integrity all passed.")
        else:
            lines.append("- Proof status: incomplete — do not count this as Detroit-ready graphics yet.")
        lines.append("")

    findings = report["findings"]
    assert isinstance(findings, list)
    if not findings:
        lines.append("No known high-signal failure markers were detected.")
    else:
        for item in findings:
            assert isinstance(item, dict)
            lines += [
                f"## [{item['severity']}] {item['title']}",
                f"- Code: `{item['code']}`",
                f"- Matches: {item['count']}",
                f"- Guidance: {item['guidance']}",
            ]
            samples = item.get("samples", [])
            if isinstance(samples, list):
                for sample in samples:
                    if isinstance(sample, dict):
                        lines.append(f"- L{sample['line']}: `{sample['text']}`")
            lines.append("")

    positives = report["positive_signals"]
    assert isinstance(positives, list)
    if positives:
        lines += ["## Positive signals"]
        for item in positives:
            assert isinstance(item, dict)
            lines.append(f"- {item['title']} (`{item['code']}`): {item['count']} match(es)")
        lines.append("")

    lines += ["Heuristic summary only. Always attach the original diagnostic log when reporting a bug."]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline triage for Madeira diagnostic logs")
    parser.add_argument("log", type=pathlib.Path, help="Path to madeira-log.txt")
    parser.add_argument("--json", dest="json_path", type=pathlib.Path, help="Write structured JSON report")
    args = parser.parse_args()

    text = args.log.read_text(encoding="utf-8", errors="replace")
    report = triage_text(text)

    if args.json_path:
        args.json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(render_text(report, args.log))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
