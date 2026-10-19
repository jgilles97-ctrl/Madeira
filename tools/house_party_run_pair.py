#!/usr/bin/env python3
"""Offline, read-only comparison of two House Party / Madeira diagnostic runs.

The manifest is a locally supplied claim, not independent proof of app identity.
No proprietary assets, network access, or optional dependencies are required.
Output contains hashes, line numbers, and diagnostic addresses, not log text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys

SCHEMA = "MADEIRA_HOUSE_PARTY_RUN_PAIR_V1"
MAX_LOG_BYTES = 24 * 1024 * 1024
WINDOW = 12
SHARED_IDENTITY = (
    "source_commit", "app_sha256", "game_sha256", "device", "os_version",
    "jit_route", "fex_revision", "wine_revision", "dxmt_revision", "profile_id",
)
CRASH_STATUS = re.compile(r"(?<![a-z0-9])(?:0x)?c0000005(?![a-z0-9])", re.I)
CRASH_CONTEXT = re.compile(
    r"(?:unhandled\s+exception|ntterminateprocess|process\s+terminated|"
    r"crashed\s+with|fatal\s+exception|status_access_violation)", re.I
)
FATAL_SIGNAL = re.compile(
    r"(?:\bsigsegv\b|\bexc_bad_access\b|segmentation\s+fault)", re.I
)
NEGATIVE_STATUS = re.compile(
    r"(?<!\w)(?:0|zero|no)\s+(?:0x)?c0000005\b", re.I
)
FOREIGN_MAP = re.compile(
    r"(?:wine\s+doesn['\u2019]t\s+own\s+this\s+addr|"
    r"fex\s*/\s*foreign\s+mmap|foreign\s+mmap)", re.I
)
GUEST_RIP = re.compile(r"(?:guest\s+)?rip\s*[:=]\s*(0x[0-9a-f]+)", re.I)
FAULT = re.compile(
    r"(?:fault(?:\s+addr(?:ess)?)?|access\s+addr(?:ess)?)"
    r"\s*[:=]\s*(0x[0-9a-f]+)", re.I
)
TEXT_CLUE = re.compile(
    r"(?:textmeshpro|tmp_fontasset|failed\s+to\s+create\s+font\s+texture|"
    r"hidden/internalerrorshader|(?:missing|fallback)\s+font\s+asset|"
    r"glyph\s+atlas.{0,40}(?:fail|error))", re.I
)


def _read_limited(path: pathlib.Path) -> bytes:
    with path.open("rb") as f:
        data = f.read(MAX_LOG_BYTES + 1)
    if len(data) > MAX_LOG_BYTES:
        raise ValueError("log exceeds the 24 MiB safety limit")
    return data


def _fatal_kind(line: str) -> str | None:
    if FATAL_SIGNAL.search(line):
        return "native_fault_signal"
    if CRASH_STATUS.search(line) and not NEGATIVE_STATUS.search(line):
        if CRASH_CONTEXT.search(line):
            return "windows_access_violation"
    return None


def _closest(lines: list[str], pattern: re.Pattern[str], center: int,
             begin: int, end: int) -> str | None:
    for i in sorted(range(begin, end), key=lambda i: (abs(i - center), i)):
        found = pattern.search(lines[i])
        if found:
            return found.group(1).lower()
    return None


def inspect_log(raw: bytes) -> dict[str, object]:
    lines = raw.decode("utf-8", errors="replace").splitlines()
    fatal_events = [(i, _fatal_kind(line)) for i, line in enumerate(lines)]
    fatal_events = [(i, kind) for i, kind in fatal_events if kind is not None]
    uncertain = [
        i + 1 for i, line in enumerate(lines)
        if CRASH_STATUS.search(line) and not NEGATIVE_STATUS.search(line)
        and _fatal_kind(line) is None
    ]
    text_lines = [i + 1 for i, line in enumerate(lines) if TEXT_CLUE.search(line)]
    first = None
    if fatal_events:
        index, kind = fatal_events[0]
        begin = max(0, index - WINDOW)
        end = min(len(lines), index + WINDOW + 1)
        if len(fatal_events) > 1:
            end = min(end, fatal_events[1][0])
        first = {
            "line": index + 1,
            "kind": kind,
            "guest_rip": _closest(lines, GUEST_RIP, index, begin, end),
            "fault_address": _closest(lines, FAULT, index, begin, end),
            "foreign_mapping_lines": [
                i + 1 for i in range(begin, end)
                if FOREIGN_MAP.search(lines[i])
            ],
            "association_only_not_root_cause": True,
        }
    return {
        "log_sha256": hashlib.sha256(raw).hexdigest(),
        "line_count": len(lines),
        "first_fatal": first,
        "fatal_count": len(fatal_events),
        "uncertain_access_violation_lines": uncertain[:10],
        "text_shader_font_clue_lines": text_lines[:10],
        "not_proved": ["gameplay", "readable_menu", "audio", "input",
                       "save_load", "stability", "physical_device"],
    }


def compare(control_raw: bytes, start_raw: bytes,
            manifest: dict[str, object]) -> dict[str, object]:
    control = inspect_log(control_raw)
    start = inspect_log(start_raw)
    reasons = []
    fields = {}
    for name in ("control", "start"):
        entry = manifest.get(name)
        if not isinstance(entry, dict):
            reasons.append(name + "_identity_missing")
            entry = {}
        fields[name] = entry
        for key in SHARED_IDENTITY + ("run_id",):
            value = entry.get(key)
            if not isinstance(value, str) or not value.strip():
                reasons.append(name + "_" + key + "_missing")
    for key in SHARED_IDENTITY:
        a = fields["control"].get(key)
        b = fields["start"].get(key)
        if a and b and a != b:
            reasons.append(key + "_mismatch")
    if fields["control"].get("run_id") == fields["start"].get("run_id"):
        reasons.append("run_ids_not_distinct")
    if control["log_sha256"] == start["log_sha256"]:
        reasons.append("logs_byte_identical")
    if not control_raw or not start_raw:
        reasons.append("empty_log")
    if reasons:
        verdict = "INCOMPARABLE"
    elif start["first_fatal"] and not control["first_fatal"]:
        verdict = "START_ONLY_FATAL_SIGNAL"
    elif control["first_fatal"] and start["first_fatal"]:
        verdict = "BOTH_RUNS_FATAL_SIGNALS"
    elif control["first_fatal"] and not start["first_fatal"]:
        verdict = "CONTROL_ONLY_FATAL_SIGNAL"
    else:
        verdict = "NO_UNAMBIGUOUS_FATAL_SIGNAL"
    shared = {key: fields["control"].get(key) for key in SHARED_IDENTITY}
    identity_digest = hashlib.sha256(
        json.dumps(shared, sort_keys=True).encode("utf-8")
    ).hexdigest() if not reasons else None
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "comparable": not reasons,
        "hold_reasons": sorted(set(reasons)),
        "identity_manifest_is_operator_supplied_not_verified": True,
        "shared_identity_digest": identity_digest,
        "control": control,
        "start": start,
        "notes": [
            "This report contains diagnostic associations, not a crash root cause.",
            "Clean log markers do not prove a playable game or any hardware test.",
            "A live device run must independently verify source/app identity and preserve original logs.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--control", required=True, type=pathlib.Path)
    p.add_argument("--start", required=True, type=pathlib.Path)
    p.add_argument("--manifest", required=True, type=pathlib.Path)
    args = p.parse_args(argv)
    try:
        manifest = json.loads(_read_limited(args.manifest))
        if not isinstance(manifest, dict):
            raise ValueError("identity manifest must be an object")
        report = compare(_read_limited(args.control), _read_limited(args.start),
                         manifest)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        print("diagnostic input error: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["comparable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
