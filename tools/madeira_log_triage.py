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
        "notes": [
            "Heuristic summary only: a matching line is evidence to inspect, not proof of root cause.",
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
