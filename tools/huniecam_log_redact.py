#!/usr/bin/env python3
"""Redact personal/credential-like fields from HunieCam/Madeira logs for sharing.

The redactor deliberately preserves instruction encodings, addresses, module
names, error codes and Madeira tags because those are needed for runtime bugs.
It is not a substitute for reviewing a log before posting it publicly.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_LOG_REDACT_V1"

RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("mac_user", re.compile(r"/Users/[^/\s]+/"), "/Users/<redacted>/"),
    ("windows_user", re.compile(r"(?i)(C:\\users\\)[^\\\s]+"), r"\1<redacted>"),
    ("email", re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"), "<redacted-email>"),
    ("token_kv", re.compile(r"(?i)\b(access[_-]?token|refresh[_-]?token|oauth[_-]?token|login[_-]?key|steamLoginSecure|password|passwd)\s*[:=]\s*([^\s;,]+)"), r"\1=<redacted>"),
    ("bearer", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"), "Bearer <redacted>"),
    ("pairing_secret", re.compile(r"(?i)\b(pairing[_-]?(?:secret|token|key)|device[_-]?secret)\s*[:=]\s*([^\s;,]+)"), r"\1=<redacted>"),
    ("udid", re.compile(r"(?i)\b(udid|device[_-]?id)\s*[:=]\s*([A-Za-z0-9-]{16,})"), r"\1=<redacted>"),
)


def redact(text: str) -> tuple[str, dict[str, Any]]:
    counts: dict[str, int] = {}
    out = text
    for name, pattern, replacement in RULES:
        out, count = pattern.subn(replacement, out)
        if count:
            counts[name] = count
    return out, {
        "schema": SCHEMA,
        "replacement_counts": counts,
        "total_replacements": sum(counts.values()),
        "preserved_for_diagnostics": ["memory addresses", "instruction encodings", "module names", "error/status codes", "Madeira log tags"],
        "warning": "Review the redacted output before public sharing; no automatic redactor can know every application-specific secret format.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Redact a HunieCam/Madeira diagnostic log")
    p.add_argument("source", type=pathlib.Path)
    p.add_argument("--out", type=pathlib.Path, required=True)
    p.add_argument("--report", type=pathlib.Path)
    args = p.parse_args()
    text = args.source.read_text(encoding="utf-8", errors="replace")
    cleaned, report = redact(text)
    args.out.write_text(cleaned, encoding="utf-8")
    if args.report:
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
