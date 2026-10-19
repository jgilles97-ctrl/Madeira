#!/usr/bin/env python3
"""Offline triage for Madeira diagnostic logs.

This utility is intentionally read-only and dependency-free. It recognizes a
small set of high-signal markers that already exist in Madeira logs and turns
them into a compact summary for bug reports and device comparison.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from dataclasses import dataclass
from typing import Iterable

SCHEMA = "MADEIRA_LOG_TRIAGE_V1"
SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "INFO": 3}
CORRELATION_WINDOW = 12

ACCESS_VIOLATION_PATTERN = re.compile(r"(?:0x)?c0000005", re.I)
FOREIGN_MAPPING_PATTERN = re.compile(
    r"(?:wine\s+doesn['\u2019]t\s+own\s+this\s+addr|fex\s*/\s*foreign\s+mmap|foreign\s+mmap)",
    re.I,
)
GUEST_RIP_PATTERN = re.compile(r"(?:guest\s+)?rip\s*[:=]\s*(0x[0-9a-f]+)", re.I)
FAULT_ADDRESS_PATTERN = re.compile(
    r"(?:fault(?:\s+addr(?:ess)?)?|access(?:\s+addr(?:ess)?)?)\s*[:=]\s*(0x[0-9a-f]+)",
    re.I,
)


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
        "unity_text_rendering_failure",
        "HIGH",
        "Unity reported a high-signal text, font-atlas, or shader failure",
        re.compile(
            r"(?:TextMeshPro|TMP_FontAsset|failed\s+to\s+create\s+font\s+texture|"
            r"Hidden/InternalErrorShader|(?:missing|fallback)\s+font\s+asset|"
            r"glyph\s+atlas.{0,40}(?:fail|error)|shader.{0,80}not\s+supported)",
            re.I,
        ),
        "Preserve the exact Unity build and renderer identity, then attach the first matching font/shader line with nearby resource-load errors.",
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


def _first_value(lines: list[str], pattern: re.Pattern[str]) -> str | None:
    for line in lines:
        match = pattern.search(line)
        if match:
            return match.group(1).lower()
    return None


def _access_violation_correlations(lines: list[str]) -> list[dict[str, object]]:
    """Correlate a crash with nearby foreign-map evidence without claiming causality."""
    correlations: list[dict[str, object]] = []
    for index, line in enumerate(lines):
        if not ACCESS_VIOLATION_PATTERN.search(line):
            continue

        start = max(0, index - CORRELATION_WINDOW)
        end = min(len(lines), index + CORRELATION_WINDOW + 1)
        window = lines[start:end]
        foreign_offsets = [i for i, item in enumerate(window) if FOREIGN_MAPPING_PATTERN.search(item)]
        if not foreign_offsets:
            continue

        correlations.append(
            {
                "code": "foreign_mapping_access_violation",
                "severity": "CRITICAL",
                "title": "Access violation occurred near a FEX/Wine foreign-mapping boundary",
                "access_violation_line": index + 1,
                "foreign_mapping_lines": [start + offset + 1 for offset in foreign_offsets],
                "guest_rip": _first_value(window, GUEST_RIP_PATTERN),
                "fault_address": _first_value(window, FAULT_ADDRESS_PATTERN),
                "context": [
                    {"line": line_no, "text": redact_line(lines[line_no - 1])}
                    for line_no in range(start + 1, end + 1)
                ],
                "guidance": (
                    "Preserve the exact Madeira build, JIT, FEX, Wine, and game identities; map the guest RIP "
                    "and fault address to a loaded module before assigning root cause. Do not treat the Start input as causal."
                ),
            }
        )
    return correlations


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

    positive_signals: list[dict[str, object]] = []
    for code, title, pattern in POSITIVE_RULES:
        hits = [(i, line) for i, line in enumerate(lines, start=1) if pattern.search(line)]
        if hits:
            positive_signals.append(
                {"code": code, "title": title, "count": len(hits), "samples": _samples(hits)}
            )

    correlations = _access_violation_correlations(lines)
    for correlation in correlations:
        findings.append(
            {
                "code": correlation["code"],
                "severity": correlation["severity"],
                "title": correlation["title"],
                "count": 1,
                "samples": correlation["context"],
                "guidance": correlation["guidance"],
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
        "crash_correlations": correlations,
        "positive_signals": positive_signals,
        "notes": [
            "Heuristic summary only: a matching line is evidence to inspect, not proof of root cause.",
            "The tool is offline/read-only and redacts common local paths and secret-like values from samples.",
            f"Foreign-mapping correlations require evidence within {CORRELATION_WINDOW} lines of an access violation.",
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

    correlations = report.get("crash_correlations", [])
    if isinstance(correlations, list) and correlations:
        lines += ["## Crash correlations"]
        for item in correlations:
            if not isinstance(item, dict):
                continue
            rip = item.get("guest_rip") or "not found"
            fault = item.get("fault_address") or "not found"
            lines.append(
                f"- `{item['code']}` at L{item['access_violation_line']}: guest RIP `{rip}`, fault address `{fault}`"
            )
        lines.append("")

    lines += [
        "Heuristic summary only. Always attach the original diagnostic log when reporting a bug.",
    ]
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
