#!/usr/bin/env python3
"""Sims 4 / EA App focused triage for Madeira logs."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from dataclasses import dataclass

SCHEMA = "SIMS4_MADEIRA_TRIAGE_V1"


@dataclass(frozen=True)
class Rule:
    code: str
    stage: str
    severity: str
    pattern: re.Pattern[str]
    explanation: str
    next_action: str


RULES = (
    Rule(
        "jit_not_ready", "runtime", "BLOCKER",
        re.compile(r"(?:debugger.{0,20}attached=0|failed to enable jit|jit.{0,40}(?:fail|not ready))", re.I),
        "Madeira did not have working JIT when the session started.",
        "Do not debug EA App or Sims yet. Fix JIT first and repeat the same profile.",
    ),
    Rule(
        "memory_failure", "runtime", "BLOCKER",
        re.compile(r"(?:c0000017|out of memory|kern_no_space|cannot allocate|allocation.{0,30}fail)", re.I),
        "The process hit a memory/address-space allocation failure.",
        "Capture Memory+ state, footprint and the first failed reservation before changing renderer settings.",
    ),
    Rule(
        "missing_dll", "loader", "BLOCKER",
        re.compile(r"import_dll Library ([^ ]+).{0,120}not found|status c0000135", re.I),
        "Wine could not load a required Windows DLL.",
        "Record the first missing DLL and add/audit the correct 64-bit Wine component before another device run.",
    ),
    Rule(
        "ea_background_service", "ea_app", "BLOCKER",
        re.compile(r"(?:EABackgroundService|background services?).{0,120}(?:crash|fail|error|not running|could not)", re.I),
        "EA App's background service did not become usable.",
        "Run the EA App qualification profile in the Wine desktop with Windows services started, then isolate the first service/RPC error.",
    ),
    Rule(
        "ea_cef_failure", "ea_app", "BLOCKER",
        re.compile(r"(?:EACefSubProcess|cef).{0,120}(?:crash|fail|error|gpu process|sandbox)", re.I),
        "EA App's Chromium/CEF UI subprocess failed.",
        "Keep TS4 out of the test. Qualify EA App UI first and capture the first CEF process error plus D3D11/DXMT lines.",
    ),
    Rule(
        "launcher_exited_early", "ea_app", "HIGH",
        re.compile(r"(?:Wine finished after (?:0|1|2|3|4|5)\.|host-ended result=34|first process exits?)", re.I),
        "The launcher session may be ending before its child processes can take over.",
        "Use the Wine desktop launch mode so explorer stays alive; do not combine this change with renderer changes.",
    ),
    Rule(
        "dxmt_failure", "graphics", "BLOCKER",
        re.compile(r"(?:dxmt|d3d11|dxgi).{0,160}(?:fail|error|unsupported|terminate|device removed)", re.I),
        "The D3D11-to-Metal graphics path failed before or during initialization.",
        "Run the built-in x64 DX11 cube on this exact Madeira build. If it fails too, fix the runtime before testing Sims.",
    ),
    Rule(
        "metal_language_mismatch", "graphics", "BLOCKER",
        re.compile(r"Metal.*language version .*not supported|MTLLibraryErrorDomain", re.I),
        "The packaged Metal shader library is incompatible with the installed iPadOS runtime.",
        "Rebuild/use a DXMT package targeting a Metal language version supported by this iPadOS build.",
    ),
    Rule(
        "access_violation", "guest", "HIGH",
        re.compile(r"(?:0x)?c0000005", re.I),
        "A Windows access violation occurred.",
        "Capture the first occurrence with module/PC lines; later repeats are usually secondary noise.",
    ),
)

POSITIVE = (
    ("ts4_loaded", re.compile(r"(?:TS4_x64\.exe|The Sims 4)", re.I)),
    ("dx11_feature_level", re.compile(r"D3D_FEATURE_LEVEL_11_[01]|feature level:\s*11", re.I)),
    ("window_created", re.compile(r"\[win-name\].*(?:Sims|TS4)", re.I)),
)


def classify(text: str) -> dict[str, object]:
    lines = text.splitlines()
    findings: list[dict[str, object]] = []
    for rule in RULES:
        hits = [(i, line.strip()) for i, line in enumerate(lines, 1) if rule.pattern.search(line)]
        if hits:
            findings.append({
                "code": rule.code,
                "stage": rule.stage,
                "severity": rule.severity,
                "count": len(hits),
                "first_line": hits[0][0],
                "sample": hits[0][1][:500],
                "explanation": rule.explanation,
                "next_action": rule.next_action,
            })

    positive = []
    for code, pattern in POSITIVE:
        hits = [i for i, line in enumerate(lines, 1) if pattern.search(line)]
        if hits:
            positive.append({"code": code, "count": len(hits), "first_line": hits[0]})

    if findings:
        earliest = min(findings, key=lambda x: int(x["first_line"]))
        next_gate = f"FIX_{str(earliest['code']).upper()}"
    elif any(p["code"] == "window_created" for p in positive):
        next_gate = "MEASURE_FIRST_FRAME_AND_MENU"
    elif any(p["code"] == "ts4_loaded" for p in positive):
        next_gate = "CAPTURE_GRAPHICS_INITIALIZATION"
    else:
        next_gate = "CAPTURE_EA_APP_TO_TS4_PROCESS_START"

    return {
        "schema": SCHEMA,
        "line_count": len(lines),
        "findings": findings,
        "positive_signals": positive,
        "next_gate": next_gate,
        "success_claim": "UNPROVEN",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Triage Madeira/EA App/Sims 4 logs")
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
