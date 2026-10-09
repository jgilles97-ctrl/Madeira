#!/usr/bin/env python3
"""Snapshot HunieCam's Wine registry configuration without exposing values.

HunieCam's Windows configuration is stored under HKCU\Software\HuniePot\
HunieCam Studio while saves live in LocalLow. This tool helps keep those lanes
separate: it extracts only the title section from a Wine user.reg/reg export and
hashes values instead of printing their contents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_REGISTRY_SNAPSHOT_V1"
TARGET = "software\\huniepot\\huniecam studio"
SECTION_RE = re.compile(r"^\[(.+?)\]\s*$")
VALUE_RE = re.compile(r'^((?:"(?:[^"\\]|\\.)*")|@)\s*=')


def _norm_section(value: str) -> str:
    text = value.strip().replace("\\\\", "\\").casefold()
    for prefix in ("hkey_current_user\\", "hkcu\\"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text.rstrip("\\")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def snapshot(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    start = None
    header = None
    for i, line in enumerate(lines):
        m = SECTION_RE.match(line.strip())
        if m and _norm_section(m.group(1)) == TARGET:
            start = i + 1
            header = m.group(1)
            break

    if start is None:
        return {
            "schema": SCHEMA,
            "found": False,
            "target": r"HKEY_CURRENT_USER\Software\HuniePot\HunieCam Studio",
            "section_sha256": None,
            "values": {},
            "warnings": ["HunieCam registry configuration section was not found in the supplied registry text."],
        }

    body: list[str] = []
    for line in lines[start:]:
        if SECTION_RE.match(line.strip()):
            break
        if line.strip().startswith("#") or line.strip().startswith(";"):
            continue
        if line.strip():
            body.append(line.rstrip())

    values: dict[str, str] = {}
    current_name: str | None = None
    current_parts: list[str] = []

    def flush() -> None:
        nonlocal current_name, current_parts
        if current_name is not None:
            values[current_name] = _hash("\n".join(current_parts))
        current_name = None
        current_parts = []

    for line in body:
        m = VALUE_RE.match(line.strip())
        if m:
            flush()
            token = m.group(1)
            current_name = "(Default)" if token == "@" else token[1:-1]
            current_parts = [line.strip()]
        elif current_name is not None:
            # Wine registry hex values may continue on following lines.
            current_parts.append(line.strip())
    flush()

    canonical = "\n".join(body)
    return {
        "schema": SCHEMA,
        "found": True,
        "target": r"HKEY_CURRENT_USER\Software\HuniePot\HunieCam Studio",
        "source_header": header,
        "section_sha256": _hash(canonical),
        "value_count": len(values),
        "values": dict(sorted(values.items())),
        "raw_values_exposed": False,
        "warnings": [],
        "rule": "This snapshot is configuration evidence only. A registry change is not save loss; LocalLow save persistence must be verified separately.",
    }


def compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    b = before.get("values") if isinstance(before.get("values"), dict) else {}
    a = after.get("values") if isinstance(after.get("values"), dict) else {}
    added = sorted(set(a) - set(b))
    removed = sorted(set(b) - set(a))
    changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    same = bool(before.get("found") and after.get("found") and not added and not removed and not changed)
    return {
        "schema": "MADEIRA_HUNIECAM_REGISTRY_COMPARE_V1",
        "same_configuration": same,
        "added_value_names": added,
        "removed_value_names": removed,
        "changed_value_names": changed,
        "before_section_sha256": before.get("section_sha256"),
        "after_section_sha256": after.get("section_sha256"),
        "rule": "Registry differences describe title configuration changes. Do not use this result as a substitute for LocalLow save verification.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Snapshot/compare HunieCam Wine registry configuration")
    sub = p.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("registry", type=pathlib.Path)
    snap.add_argument("--json", dest="json_path", type=pathlib.Path)
    comp = sub.add_parser("compare")
    comp.add_argument("before", type=pathlib.Path)
    comp.add_argument("after", type=pathlib.Path)
    comp.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    if args.command == "snapshot":
        report = snapshot(args.registry.read_text(encoding="utf-8", errors="replace"))
    else:
        before = json.loads(args.before.read_text(encoding="utf-8"))
        after = json.loads(args.after.read_text(encoding="utf-8"))
        report = compare(before, after)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
