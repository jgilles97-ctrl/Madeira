#!/usr/bin/env python3
"""Classify EA App Chromium/CEF helper roles from Madeira/Wine logs.

Madeira runs Windows pseudo-processes as threads in one iOS Mach task. Chromium
helpers are therefore worth identifying precisely before any helper-specific
containment is considered. This tool is observation-only: it never recommends
killing or skipping a helper merely from its executable name.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from collections import Counter
from typing import Any

SCHEMA = "SIMS4_EA_CEF_ROLES_V1"

CEF_EXE_RE = re.compile(r"\bEACefSubProcess\.exe\b", re.I)
TYPE_RE = re.compile(r"(?:^|\s)--type=(?:\"([^\"]+)\"|'([^']+)'|([^\s\"]+))", re.I)
UTILITY_RE = re.compile(r"(?:^|\s)--utility-sub-type=(?:\"([^\"]+)\"|'([^']+)'|([^\s\"]+))", re.I)
PROCESS_ID_RE = re.compile(r"\b(?:pid|process[_ -]?id)\s*[=:]\s*(\d+)\b", re.I)
FATAL_RE = re.compile(
    r"(?:c0000005|access violation|NtTerminateProcess|NtRaiseHardError|crash|fatal|GPU process.{0,40}(?:fail|exit)|NetworkService.{0,40}(?:fail|exit))",
    re.I,
)


def first_group(match: re.Match[str] | None) -> str | None:
    if not match:
        return None
    for value in match.groups():
        if value:
            return value.strip().strip('"\'')
    return None


def normalize_role(line: str) -> tuple[str, str | None]:
    role = first_group(TYPE_RE.search(line))
    utility = first_group(UTILITY_RE.search(line))
    if not role:
        role = "browser_or_unspecified"
    return role.lower(), utility.lower() if utility else None


def classify(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    helpers: list[dict[str, Any]] = []
    role_counts: Counter[str] = Counter()
    utility_counts: Counter[str] = Counter()
    fatal_by_role: Counter[str] = Counter()

    for lineno, line in enumerate(lines, 1):
        if not CEF_EXE_RE.search(line):
            continue
        role, utility = normalize_role(line)
        pid_match = PROCESS_ID_RE.search(line)
        fatal = bool(FATAL_RE.search(line))
        entry = {
            "line": lineno,
            "role": role,
            "utility_sub_type": utility,
            "pid": int(pid_match.group(1)) if pid_match else None,
            "fatal_signal": fatal,
            "sample": line.strip()[:1000],
        }
        helpers.append(entry)
        role_counts[role] += 1
        if utility:
            utility_counts[utility] += 1
        if fatal:
            fatal_by_role[role] += 1

    observed_roles = sorted(role_counts)
    observed_utilities = sorted(utility_counts)
    network_service_seen = any("network" in item for item in observed_utilities)
    gpu_seen = "gpu-process" in role_counts
    renderer_seen = "renderer" in role_counts

    if not helpers:
        next_gate = "CAPTURE_EA_CEF_COMMAND_LINES"
    elif fatal_by_role:
        first_fatal = next(item for item in helpers if item["fatal_signal"])
        next_gate = f"ISOLATE_EA_CEF_{str(first_fatal['role']).upper().replace('-', '_')}_FAILURE"
    elif not (gpu_seen and renderer_seen and network_service_seen):
        next_gate = "CAPTURE_MISSING_EA_CEF_ROLES"
    else:
        next_gate = "CORRELATE_EA_CEF_ROLES_WITH_WINDOW_AND_TS4_START"

    return {
        "schema": SCHEMA,
        "helper_line_count": len(helpers),
        "role_counts": dict(sorted(role_counts.items())),
        "utility_sub_type_counts": dict(sorted(utility_counts.items())),
        "fatal_by_role": dict(sorted(fatal_by_role.items())),
        "helpers": helpers,
        "role_coverage": {
            "gpu_process_seen": gpu_seen,
            "renderer_seen": renderer_seen,
            "network_service_seen": network_service_seen,
        },
        "next_gate": next_gate,
        "containment_policy": (
            "Observation only. Madeira has proven Chromium can run in its single-Mach-task pseudo-process model. "
            "Do not block or kill an EA helper by executable name alone; require role-specific device evidence."
        ),
        "physical_device_success": "UNPROVEN",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Classify EACefSubProcess roles from a Madeira/Wine log")
    ap.add_argument("log", type=pathlib.Path)
    ap.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = ap.parse_args()
    report = classify(args.log.read_text(encoding="utf-8", errors="replace"))
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
