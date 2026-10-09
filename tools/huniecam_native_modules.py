#!/usr/bin/env python3
"""Audit HunieCam's owned native Windows module dependency chain, read-only.

Scans HunieCamStudio.exe, top-level DLLs and HunieCamStudio_Data/Plugins DLLs.
Managed C# assemblies are intentionally excluded. Each native PE is delegated to
huniecam_pe_imports so the report contains module names/hashes/import DLL names,
not proprietary binary contents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

import huniecam_pe_imports as pe_imports

SCHEMA = "MADEIRA_HUNIECAM_NATIVE_MODULES_V1"


def _rel(root: pathlib.Path, path: pathlib.Path) -> str:
    return path.relative_to(root).as_posix()


def scan(root: pathlib.Path) -> dict[str, Any]:
    root = root.expanduser().resolve(); errors: list[str] = []; modules: list[dict[str, Any]] = []
    candidates: list[pathlib.Path] = []
    exe = root / "HunieCamStudio.exe"
    if exe.is_file(): candidates.append(exe)
    else: errors.append("HunieCamStudio.exe is missing from the supplied install root.")
    candidates.extend(sorted((p for p in root.glob("*.dll") if p.is_file()), key=lambda p: p.name.casefold()))
    plugins = root / "HunieCamStudio_Data" / "Plugins"
    if plugins.is_dir(): candidates.extend(sorted((p for p in plugins.rglob("*.dll") if p.is_file()), key=lambda p: p.as_posix().casefold()))

    seen: set[str] = set()
    for path in candidates:
        rel = _rel(root, path)
        if rel.casefold() in seen: continue
        seen.add(rel.casefold())
        audit = pe_imports.parse(path)
        modules.append({"relative_path": rel, "file_sha256": audit.get("file_sha256"), "architecture": audit.get("architecture"), "valid_pe": audit.get("valid"), "imports": audit.get("imports", []), "categories": audit.get("categories", {}), "errors": audit.get("errors", [])})

    requesters: dict[str, list[str]] = {}
    for module in modules:
        for name in module.get("imports", []):
            requesters.setdefault(str(name).casefold(), []).append(str(module["relative_path"]))
    requesters = {dll: sorted(paths, key=str.casefold) for dll, paths in sorted(requesters.items())}
    material = [{"relative_path": m["relative_path"], "file_sha256": m["file_sha256"]} for m in modules]
    fingerprint = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest() if modules else None
    return {"schema": SCHEMA, "root_label": root.name, "module_count": len(modules), "valid_module_count": sum(1 for m in modules if m["valid_pe"]), "module_set_sha256": fingerprint, "modules": modules, "dependency_requesters": requesters, "errors": errors, "valid": not errors and all(m["valid_pe"] for m in modules), "privacy": {"absolute_paths_embedded": False, "binary_contents_embedded": False}, "rule": "Use requester-module evidence before changing a dependency. Managed assemblies are excluded; this report covers only owned native Windows PE modules."}


def main() -> int:
    p = argparse.ArgumentParser(description="Audit HunieCam native Windows module dependency chain"); p.add_argument("install", type=pathlib.Path); p.add_argument("--json", dest="json_path", type=pathlib.Path); args = p.parse_args(); report = scan(args.install); text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path: args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text); return 0 if report["valid"] else 2


if __name__ == "__main__": raise SystemExit(main())
