#!/usr/bin/env python3
"""Lint a HunieCam/Madeira experiment before it reaches the iPad.

The clean profile has no renderer override. Each diagnostic run may change at
most one compatibility variable. Known-bad Unity-Mono experiments are rejected
and speculative renderer forcing is not allowed into the baseline by habit.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shlex
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_CONFIG_GUARD_V2"

KNOWN_CONFIG_EXPERIMENTS = {
    "d3d9": {"native"},
    "env.MADEIRA_WOW_RWX_PLAIN": {"1"},
}
KNOWN_ARGUMENT_EXPERIMENTS = {"-force-d3d9"}

FORBIDDEN_CONFIG_PATTERNS = (
    (re.compile(r"^(?:env\.)?MADEIRA_MONO_SUSPEND$", re.I), {"hybrid"},
     "Unity Mono is known to abort with hybrid suspend in Madeira issue #123."),
    (re.compile(r"^mono-suspend$", re.I), {"hybrid"},
     "Unity Mono is known to abort with hybrid suspend in Madeira issue #123."),
    (re.compile(r"^(?:env\.)?MADEIRA_WX$", re.I), {"1", "on", "true"},
     "The forced WX path produced a Mono-init wild-pointer crash in Madeira issue #123."),
    (re.compile(r"^wx$", re.I), {"1", "on", "true"},
     "The forced WX path produced a Mono-init wild-pointer crash in Madeira issue #123."),
)

DISCOURAGED_CONFIG_PATTERNS = (
    (re.compile(r"^(?:env\.)?MADEIRA_REAL_SUSPEND$", re.I),
     "real-suspend helped a modern IL2CPP title, but issue #123 found no benefit for Unity Mono. Do not use it for HunieCam without new evidence."),
    (re.compile(r"^real-suspend$", re.I),
     "real-suspend helped a modern IL2CPP title, but issue #123 found no benefit for Unity Mono. Do not use it for HunieCam without new evidence."),
    (re.compile(r"^(?:pool|jit-pool|env\.MADEIRA_JIT_POOL|env\.MADEIRA_POOL)$", re.I),
     "Changing JIT-pool sizing can worsen WoW64 virtual-address pressure. Keep the default unless a real log specifically justifies it."),
)

FORBIDDEN_ARGUMENTS = {
    "-force-opengl": "The clean HunieCam profile does not force a renderer. Observe the owned build's Unity log first; OpenGL is not an evidence-backed experiment here.",
    "-force-d3d11": "The clean HunieCam profile does not force D3D11. A clean D3D11 selection is allowed when Unity chooses it naturally, but forcing it is not part of the evidence plan.",
    "-force-vulkan": "The clean HunieCam profile does not force a renderer, and this Unity 5.3-era Windows build has no evidence-backed Vulkan experiment in the Madeira plan.",
}


def parse_config(text: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if "=" not in line:
            out.append({"line": str(number), "key": line, "value": "", "raw": raw})
            continue
        key, value = line.split("=", 1)
        out.append({"line": str(number), "key": key.strip(), "value": value.strip(), "raw": raw})
    return out


def normalize_arg(token: str) -> str:
    return token.strip().lower()


def inspect(config_text: str, arguments: str) -> dict[str, Any]:
    entries = parse_config(config_text)
    try:
        argv = shlex.split(arguments, posix=True)
        arg_parse_error = None
    except ValueError as exc:
        argv = []
        arg_parse_error = str(exc)

    failures: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    changes: list[dict[str, str]] = []
    unknown: list[dict[str, str]] = []

    if arg_parse_error:
        failures.append({"code": "argument_parse_error", "message": arg_parse_error})

    for entry in entries:
        key = entry["key"]
        value = entry["value"].strip().lower()
        forbidden = False
        for pattern, bad_values, reason in FORBIDDEN_CONFIG_PATTERNS:
            if pattern.match(key) and value in bad_values:
                failures.append({"code": "known_bad_config", "message": f"{key}={entry['value']}: {reason}"})
                forbidden = True
                break
        if forbidden:
            changes.append({"kind": "config", "name": key, "value": entry["value"]})
            continue

        for pattern, reason in DISCOURAGED_CONFIG_PATTERNS:
            if pattern.match(key):
                warnings.append({"code": "discouraged_config", "message": f"{key}={entry['value']}: {reason}"})
                break

        if key in KNOWN_CONFIG_EXPERIMENTS and value in {v.lower() for v in KNOWN_CONFIG_EXPERIMENTS[key]}:
            changes.append({"kind": "config", "name": key, "value": entry["value"]})
        else:
            unknown.append(entry)
            changes.append({"kind": "config", "name": key, "value": entry["value"]})

    for token in argv:
        low = normalize_arg(token)
        if low in FORBIDDEN_ARGUMENTS:
            failures.append({"code": "known_bad_argument", "message": f"{token}: {FORBIDDEN_ARGUMENTS[low]}"})
        if low in KNOWN_ARGUMENT_EXPERIMENTS:
            changes.append({"kind": "argument", "name": low, "value": "1"})
        elif low.startswith("-"):
            changes.append({"kind": "argument", "name": low, "value": "1"})
            if low not in FORBIDDEN_ARGUMENTS:
                unknown.append({"line": "argument", "key": token, "value": "", "raw": token})

    if len(changes) > 1:
        failures.append({
            "code": "multiple_variables",
            "message": f"This run changes {len(changes)} compatibility variables. HunieCam experiments must change exactly one variable from the previous clean/control run.",
        })

    if unknown:
        warnings.append({
            "code": "unreviewed_variable",
            "message": "One or more config/argument changes are not in the HunieCam evidence plan. Treat them as unreviewed rather than carrying them forward by habit.",
        })

    status = "FAIL" if failures else "WARN" if warnings else "PASS"
    experiment = "clean baseline"
    if len(changes) == 1:
        change = changes[0]
        if change["name"] == "d3d9": experiment = "native D3D9 frontend A/B"
        elif change["name"] == "env.MADEIRA_WOW_RWX_PLAIN": experiment = "Unity Mono RWX plain-memory A/B"
        elif change["name"] == "-force-d3d9": experiment = "force Unity D3D9 A/B"
        else: experiment = "unreviewed single-variable experiment"

    return {
        "schema": SCHEMA,
        "status": status,
        "experiment": experiment,
        "change_count": len(changes),
        "changes": changes,
        "failures": failures,
        "warnings": warnings,
        "unknown_changes": unknown,
        "baseline": {
            "config": "",
            "arguments": "",
            "renderer_override": None,
            "resolution": "1280x720",
            "display": "fit",
            "fps": 60,
        },
        "conditional_experiment_rules": {
            "-force-d3d9": "Only after D3D11 is tied to a graphics failure/crash, or graphics init fails before an API is proven.",
            "d3d9=native": "Only after D3D9 is proven active and the remaining failure is graphics-specific.",
            "MADEIRA_WOW_RWX_PLAIN=1": "Only for real protected-memory store evidence with HunieCam's bundled Unity Mono loaded; never for the 0xd4200000 breakpoint family.",
        },
        "rule": "Clean means no renderer override. Use one evidence-backed compatibility change at a time and roll it back if it does not produce a measurable benefit.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Guard HunieCam Madeira experiment settings")
    p.add_argument("--config", type=pathlib.Path, help="Text file containing this game's Madeira config")
    p.add_argument("--arguments", default="", help="Launch arguments exactly as entered")
    p.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    text = args.config.read_text(encoding="utf-8") if args.config else ""
    report = inspect(text, args.arguments)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] != "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
