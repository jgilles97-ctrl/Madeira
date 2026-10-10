#!/usr/bin/env python3
"""Choose a Windows dependency action from HunieCam evidence without guessing.

V2 combines the main EXE import audit with the owned native-module dependency
chain. A runtime missing DLL can therefore be classified as a direct EXE import,
a dependency requested by a bundled native plugin/module, or still-unresolved
dynamic evidence. This tool never installs/downloads anything.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_DEPENDENCY_PLAN_V2"
DLL_RE = re.compile(r"(?i)\b([A-Za-z0-9_.+-]+\.dll)\b")


def _missing_names(session: dict[str, Any] | None) -> list[str]:
    names: dict[str, str] = {}
    for failure in (session or {}).get("failures", []):
        if not isinstance(failure, dict) or failure.get("code") != "missing_dll": continue
        for sample in failure.get("samples", []):
            if not isinstance(sample, dict): continue
            for name in DLL_RE.findall(str(sample.get("text", ""))): names.setdefault(name.casefold(), name)
    return sorted(names.values(), key=str.casefold)


def choose(pe_imports: dict[str, Any] | None, session: dict[str, Any] | None, native_modules: dict[str, Any] | None = None) -> dict[str, Any]:
    audit = pe_imports or {}; modules = native_modules or {}
    imports = {str(x).casefold(): str(x) for x in audit.get("imports", [])}; requesters = modules.get("dependency_requesters") if isinstance(modules.get("dependency_requesters"), dict) else {}
    missing = _missing_names(session); direct = [name for name in missing if name.casefold() in imports]
    native_requesters = {name: list(requesters.get(name.casefold(), [])) for name in missing if requesters.get(name.casefold())}
    unresolved = [name for name in missing if name not in direct and name not in native_requesters]
    errors: list[str] = []
    if audit and not audit.get("valid"): errors.append("PE import audit is invalid; direct-import conclusions are unavailable.")
    if modules and not modules.get("valid"): errors.append("Native-module audit is invalid; requester-module conclusions are unavailable.")

    if direct:
        status = "EXACT_DIRECT_IMPORT_MISSING"; action = "Satisfy only the exact missing direct-import prerequisite through a legitimate runtime/package source, then rerun the unchanged baseline. Do not add unrelated native overrides."
    elif native_requesters:
        status = "EXACT_BUNDLED_NATIVE_REQUESTER_FOUND"; action = "A bundled native HunieCam module explicitly imports the missing DLL. Use the named requester module plus DLL name to identify the exact legitimate prerequisite; change no unrelated compatibility settings."
    elif unresolved:
        status = "RUNTIME_REPORTED_DYNAMIC_OR_UNRESOLVED_MISSING"; action = "The runtime named a missing DLL but neither the main EXE nor scanned bundled native modules directly import it. Preserve loader/module context and identify the dynamic/indirect requester before installing or overriding anything."
    elif any(isinstance(x, dict) and x.get("code") == "missing_dll" for x in (session or {}).get("failures", [])):
        status = "MISSING_DLL_NAME_UNPARSED"; action = "Preserve the first missing-DLL log line with nearby module context. Do not guess a redistributable until the exact DLL name/requester is known."
    else:
        status = "NO_MISSING_DLL_EVIDENCE"; action = "Do not install extra Visual C++, DirectX, .NET, Wine Mono, or native DLL overrides. There is no missing-DLL evidence to justify a dependency change."

    return {"schema": SCHEMA, "status": status, "missing_dlls": missing, "direct_exe_import_matches": direct, "bundled_native_requesters": native_requesters, "unresolved_dynamic_candidates": unresolved, "pe_audit_valid": audit.get("valid") if audit else None, "native_module_audit_valid": modules.get("valid") if modules else None, "action": action, "errors": errors, "rule": "A dependency change requires an exact runtime DLL name plus direct owned-module evidence or a separately identified dynamic requester. Absence of evidence means keep the clean prefix/profile unchanged."}


def load(path: pathlib.Path | None) -> dict[str, Any] | None:
    return None if path is None else json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    p = argparse.ArgumentParser(description="Choose evidence-backed HunieCam Windows dependency action"); p.add_argument("--pe-imports", type=pathlib.Path, required=True); p.add_argument("--native-modules", type=pathlib.Path); p.add_argument("--session", type=pathlib.Path, required=True); p.add_argument("--json", dest="json_path", type=pathlib.Path); args = p.parse_args(); report = choose(load(args.pe_imports), load(args.session), load(args.native_modules)); text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path: args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text); return 0 if not report["errors"] else 2


if __name__ == "__main__": raise SystemExit(main())
