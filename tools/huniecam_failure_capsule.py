#!/usr/bin/env python3
"""Extract a compact, privacy-safer first-failure capsule from a Madeira log.

The capsule preserves the low-level lines needed to classify a runtime bug while
hashing the complete source log. It is intentionally small and does not replace
keeping the original private evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
from dataclasses import dataclass
from typing import Any

import huniecam_log_redact as log_redact

SCHEMA = "MADEIRA_HUNIECAM_FAILURE_CAPSULE_V1"


@dataclass(frozen=True)
class Rule:
    code: str
    pattern: re.Pattern[str]
    priority: int


RULES = (
    Rule("jit_missing", re.compile(r"\[jit-debugger\].*attached=0", re.I), 0),
    Rule("wow_map_refused", re.compile(r"\[wow-window\].*refused", re.I), 1),
    Rule("missing_dll", re.compile(r"(?:err:module:import_dll|\[dll-missing\])", re.I), 2),
    Rule("guest_breakpoint", re.compile(r"\[store-undecoded\].*insn=0xd4200000", re.I), 3),
    Rule("store_undecoded", re.compile(r"\[store-undecoded\]", re.I), 4),
    Rule("writecopy_image", re.compile(r"SEC_IMAGE\s+WRITECOPY", re.I), 5),
    Rule("redelivery_storm", re.compile(r"\[redeliv\].*(?:storm|terminat|identical)", re.I), 6),
    Rule("graphics_init", re.compile(r"(?:Failed to initialize graphics|Failed creating D3D|GfxDevice.*fail)", re.I), 7),
    Rule("steam_init", re.compile(r"SteamAPI[_ ]Init.*(?:fail|false)", re.I), 8),
    Rule("no_memory", re.compile(r"(?:0x)?c0000017", re.I), 9),
    Rule("access_violation", re.compile(r"(?:0x)?c0000005|access violation", re.I), 10),
    Rule("fatal", re.compile(r"(?:fatal error|Crash!!!|unhandled exception)", re.I), 11),
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def extract(text: str, before: int = 6, after: int = 10) -> dict[str, Any]:
    lines = text.splitlines()
    hits: list[tuple[int, int, Rule]] = []
    for rule in RULES:
        for idx, line in enumerate(lines):
            if rule.pattern.search(line):
                hits.append((rule.priority, idx, rule))
                break

    if not hits:
        return {
            "schema": SCHEMA,
            "found": False,
            "source_log_sha256": sha256_text(text),
            "signature": None,
            "excerpt": [],
            "redaction": None,
            "rule": "No known high-signal failure was found. Keep the full private logs and use session triage rather than inventing a cause.",
        }

    _, idx, rule = min(hits, key=lambda x: (x[0], x[1]))
    lo = max(0, idx - max(0, before))
    hi = min(len(lines), idx + max(0, after) + 1)
    raw_excerpt = "\n".join(lines[lo:hi])
    cleaned, redaction = log_redact.redact(raw_excerpt)
    excerpt_lines = cleaned.splitlines()
    return {
        "schema": SCHEMA,
        "found": True,
        "source_log_sha256": sha256_text(text),
        "signature": rule.code,
        "failure_line": idx + 1,
        "excerpt_start_line": lo + 1,
        "excerpt_end_line": hi,
        "excerpt": excerpt_lines,
        "redaction": redaction,
        "rule": "This is a routing capsule, not root-cause proof. Keep the original private log; use the capsule for quick comparison/upstream discussion after review.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Extract a redacted HunieCam first-failure capsule")
    p.add_argument("log", type=pathlib.Path)
    p.add_argument("--before", type=int, default=6)
    p.add_argument("--after", type=int, default=10)
    p.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    report = extract(args.log.read_text(encoding="utf-8", errors="replace"), args.before, args.after)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
