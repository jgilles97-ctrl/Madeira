#!/usr/bin/env python3
"""Match a HunieCam run against known upstream Madeira failure families.

This is a routing aid, not proof that two bugs have the same root cause. It
requires concrete log signatures and records why a match was made so we can
reuse upstream fixes without blindly copying unrelated game workarounds.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
from dataclasses import dataclass
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_ISSUE_MATCHER_V1"


@dataclass(frozen=True)
class IssueRule:
    number: int
    title: str
    patterns: tuple[re.Pattern[str], ...]
    require_all: bool
    relevance: str
    action: str


RULES = (
    IssueRule(
        123,
        "Unity/Mono, .NET and Java RWX store-undecoded failures",
        (re.compile(r"\[store-undecoded\]", re.I), re.compile(r"(?:MonoManager|mono\.dll|HunieCamStudio_Data[/\\]Mono)", re.I)),
        True,
        "high",
        "Check whether the first fault is a real store encoding. Current Madeira already fixed several encodings; if a new one remains, preserve the exact instruction and nearby mach-exception lines. Do not assume issue #123 if the instruction is 0xd4200000 (guest breakpoint).",
    ),
    IssueRule(
        173,
        "WoW64 WRITECOPY self-modifying image + guest breakpoint misdelivery",
        (re.compile(r"SEC_IMAGE\s+WRITECOPY", re.I), re.compile(r"\[store-undecoded\].*insn=0xd4200000", re.I)),
        True,
        "high",
        "Treat as a Madeira WoW64/runtime problem, not an RWX-plain title tweak. Preserve WRITECOPY, breakpoint and redelivery evidence.",
    ),
    IssueRule(
        121,
        "DXMT Metal library uses unsupported Metal language version",
        (re.compile(r"Metal.*language version\s*4\.1|language version 4\.1.*not support", re.I),),
        False,
        "high",
        "Update/rebuild the Madeira/DXMT runtime; do not create a HunieCam-specific graphics workaround for a stale Metal library.",
    ),
    IssueRule(
        116,
        "WoW64 CPU feature check reports no SSE2",
        (re.compile(r"CPU Error", re.I), re.compile(r"SSE2.*(?:not supported|unsupported|missing)", re.I)),
        False,
        "medium",
        "Capture the CPU-feature check evidence. HunieCam is an old 32-bit title, so an incorrect WoW64 feature report is more plausible than changing the game's graphics settings.",
    ),
    IssueRule(
        233,
        "Dock start screen hides game-owned fatal/error dialog",
        (re.compile(r"\[win-name\].*(?:Fatal error|Failed to load|Error)", re.I), re.compile(r"Waiting for its window", re.I)),
        False,
        "medium",
        "Use Show desktop / direct launch to reveal the game's own message box and diagnose the underlying error rather than treating the wait screen as a hang.",
    ),
    IssueRule(
        90,
        "Unity/Rewired controller path uses Windows.Gaming.Input/HID instead of XInput",
        (re.compile(r"Windows\.Gaming\.Input", re.I), re.compile(r"\\HID#VID_", re.I)),
        False,
        "low",
        "Controller support is optional for HunieCam. Do not block the port on this if touch/pointer input works; use it only if a controller convenience mode is later pursued.",
    ),
)


def text_of(path: pathlib.Path | None) -> str:
    if not path:
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def match(text: str, preflight: dict[str, Any] | None = None) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for rule in RULES:
        found = [bool(p.search(text)) for p in rule.patterns]
        hit = all(found) if rule.require_all else any(found)
        if not hit:
            continue
        matches.append({
            "issue": rule.number,
            "url": f"https://github.com/willfaust/Madeira/issues/{rule.number}",
            "title": rule.title,
            "relevance": rule.relevance,
            "pattern_hits": found,
            "action": rule.action,
        })

    runtime = (preflight or {}).get("runtime_signals", {}) if preflight else {}
    unity_mono = bool(runtime.get("mono_runtime_found"))
    gameassembly = bool(runtime.get("gameassembly_found"))
    exclusions = []
    if unity_mono and not gameassembly:
        exclusions.append({
            "issue": 232,
            "reason": "BALL x PIT's real-suspend workaround is for Unity IL2CPP. HunieCam's preflight identifies game-bundled Mono instead, so that workaround is not transferable evidence.",
        })
        exclusions.append({
            "issue": 230,
            "reason": "The wintypes.dll / Failed to load il2cpp report applies to IL2CPP GameAssembly.dll. HunieCam's preflight identifies Mono and no GameAssembly.dll.",
        })

    order = {"high": 0, "medium": 1, "low": 2}
    matches.sort(key=lambda x: (order.get(str(x["relevance"]), 9), int(x["issue"])))
    return {
        "schema": SCHEMA,
        "matches": matches,
        "best_match": matches[0] if matches else None,
        "explicit_nonmatches": exclusions,
        "rule": "A signature match is a lead, not proof. Keep the original HunieCam log and verify the first failing event before applying any upstream workaround.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Match HunieCam logs to known Madeira issues")
    p.add_argument("--madeira-log", type=pathlib.Path)
    p.add_argument("--unity-log", type=pathlib.Path)
    p.add_argument("--preflight", type=pathlib.Path)
    p.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    preflight = json.loads(text_of(args.preflight)) if args.preflight else None
    report = match(text_of(args.madeira_log) + "\n" + text_of(args.unity_log), preflight)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
