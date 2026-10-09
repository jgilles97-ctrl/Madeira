#!/usr/bin/env python3
"""Choose a Windows dependency action from HunieCam evidence without guessing.

The owned EXE import audit tells us direct imports. Session/failure evidence tells
us what the runtime actually could not load. This helper never downloads or
installs anything; it classifies the next dependency step and explicitly blocks
random redistributable/native-DLL experimentation.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_DEPENDENCY_PLAN_V1"
DLL_RE = re.compile(r"(?i)\b([A-Za-z0-9_.+-]+\.dll)\b")


def _missing_names(session: dict[str, Any] | None) -> list[str]:
    names: dict[str, str] = {}
    for failure in (session or {}).get("failures", []):
        if not isinstance(failure, dict) or failure.get("code") != "missing_dll":
            continue
        for sample in failure.get("samples", []):
            if not isinstance(sample, dict):
                continue
            for name in DLL_RE.findall(str(sample.get("text", ""))):
                names.setdefault(name.casefold(), name)
    return sorted(names.values(), key=str.casefold)


def choose(pe_imports: dict[str, Any] | None, session: dict[str, Any] | None) -> dict[str, Any]:
    audit = pe_imports or {}
    imports = {str(x).casefold(): str(x) for x in audit.get("imports", [])}
    missing = _missing_names(session)
    direct = [name for name in missing if name.casefold() in imports]
    indirect = [name for name in missing if name.casefold() not in imports]
    errors: list[str] = []
    if audit and not audit.get("valid"):
        errors.append("PE import audit is invalid; direct-import conclusions are unavailable.")

    if direct:
        status = "EXACT_DIRECT_IMPORT_MISSING"
        action = "Satisfy only the exact missing direct-import DLL prerequisite through a legitimate runtime/package source, then rerun the unchanged baseline. Do not add unrelated native overrides."
    elif indirect:
        status = "RUNTIME_REPORTED_INDIRECT_OR_DYNAMIC_MISSING"
        action = "The runtime named a missing DLL that HunieCamStudio.exe does not directly import. Treat it as an indirect/plugin/dynamic dependency: identify which loaded module requested it before installing or overriding anything."
    elif any(isinstance(x, dict) and x.get("code") == "missing_dll" for x in (session or {}).get("failures", [])):
        status = "MISSING_DLL_NAME_UNPARSED"
        action = "Preserve the first missing-DLL log line with nearby module context. Do not guess a redistributable until the exact DLL name/requesting module is known."
    else:
        status = "NO_MISSING_DLL_EVIDENCE"
        action = "Do not install extra Visual C++, DirectX, .NET, Wine Mono, or native DLL overrides. There is no missing-DLL evidence to justify a dependency change."

    return {
        "schema": SCHEMA,
        "status": status,
        "missing_dlls": missing,
        "direct_exe_import_matches": direct,
        "indirect_or_dynamic_candidates": indirect,
        "pe_audit_valid": audit.get("valid") if audit else None,
        "action": action,
        "errors": errors,
        "rule": "A dependency change requires an exact runtime missing-DLL signal or direct owned-PE evidence. Absence of evidence means keep the clean prefix/profile unchanged.",
    }


def load(path: pathlib.Path | None) -> dict[str, Any] | None:
    return None if path is None else json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    p = argparse.ArgumentParser(description="Choose evidence-backed HunieCam Windows dependency action")
    p.add_argument("--pe-imports", type=pathlib.Path, required=True)
    p.add_argument("--session", type=pathlib.Path, required=True)
    p.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    report = choose(load(args.pe_imports), load(args.session))
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path: args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if not report["errors"] else 2


if __name__ == "__main__": raise SystemExit(main())
