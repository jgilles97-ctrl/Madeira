#!/usr/bin/env python3
"""Fingerprint and audit Madeira's staged ARM64EC Windows runtime for Sims/EA tests.

The audit separates generic core modules from launcher coverage that has already
been physically validated in upstream Madeira testing. "Validated" means the DLL
was built/loaded and its Windows API worked on a device; it does NOT mean EA App
specifically requires the DLL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from dataclasses import dataclass, asdict

SCHEMA = "SIMS4_MADEIRA_RUNTIME_AUDIT_V2"

# Physically exercised in Madeira secondary-launcher/device work. These are safe
# runtime-coverage candidates for the Sims/EA canary lane, but are not asserted
# to be EA App requirements until our own canary/import evidence says so.
VALIDATED_LAUNCHER_COVERAGE_MODULES = (
    "netprofm.dll",
    "sensapi.dll",
    "avifil32.dll",
    "msvfw32.dll",
)

# Generic network module already present in the ordinary Madeira runtime.
NETWORK_SIGNAL_MODULES = (
    "winhttp.dll",
)

# Generic graphics/runtime files useful for qualifying a Sims 4 D3D11 test lane.
CORE_SIGNAL_MODULES = (
    "d3d11.dll",
    "dxgi.dll",
    "xtajit64.dll",
)


@dataclass(frozen=True)
class FileRecord:
    relative_path: str
    size: int
    sha256: str


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_files(root: pathlib.Path) -> list[FileRecord]:
    records: list[FileRecord] = []
    if not root.is_dir():
        return records
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.relative_to(root).as_posix().lower()):
        try:
            rel = path.relative_to(root).as_posix()
            records.append(FileRecord(rel, path.stat().st_size, sha256_file(path)))
        except OSError:
            continue
    return records


def fingerprint(records: list[FileRecord]) -> str:
    h = hashlib.sha256()
    for rec in sorted(records, key=lambda r: r.relative_path.lower()):
        h.update(rec.relative_path.lower().encode("utf-8"))
        h.update(b"\0")
        h.update(str(rec.size).encode("ascii"))
        h.update(b"\0")
        h.update(rec.sha256.encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def module_index(records: list[FileRecord]) -> dict[str, FileRecord]:
    out: dict[str, FileRecord] = {}
    for rec in records:
        out.setdefault(pathlib.PurePosixPath(rec.relative_path).name.lower(), rec)
    return out


def audit(root: pathlib.Path) -> dict[str, object]:
    root = root.resolve()
    records = collect_files(root)
    by_name = module_index(records)

    def state(name: str, *, evidence_class: str) -> dict[str, object]:
        rec = by_name.get(name.lower())
        base: dict[str, object] = {
            "evidence_class": evidence_class,
            "ea_requirement": "UNPROVEN",
        }
        if rec:
            return {
                **base,
                "status": "bundled",
                "path": rec.relative_path,
                "size": rec.size,
                "sha256": rec.sha256,
            }
        return {
            **base,
            "status": "not_bundled",
            "path": None,
        }

    core = {name: state(name, evidence_class="core_runtime") for name in CORE_SIGNAL_MODULES}
    network = {name: state(name, evidence_class="generic_network") for name in NETWORK_SIGNAL_MODULES}
    validated = {
        name: state(name, evidence_class="physically_validated_madeira_launcher_coverage")
        for name in VALIDATED_LAUNCHER_COVERAGE_MODULES
    }
    total_bytes = sum(r.size for r in records)
    validated_present = sum(1 for item in validated.values() if item["status"] == "bundled")

    return {
        "schema": SCHEMA,
        "runtime_root": str(root),
        "runtime_exists": root.is_dir(),
        "file_count": len(records),
        "total_bytes": total_bytes,
        "runtime_fingerprint_sha256": fingerprint(records),
        "core_signal_modules": core,
        "network_signal_modules": network,
        "validated_launcher_coverage_modules": validated,
        "validated_launcher_coverage_present": validated_present,
        "validated_launcher_coverage_total": len(VALIDATED_LAUNCHER_COVERAGE_MODULES),
        "launcher_coverage_policy": (
            "The four validated coverage DLLs have worked in physical Madeira tests. "
            "Their absence is an inventory gap for this diagnostic lane, not proof of an EA App requirement. "
            "Use the Sims launcher canary/import logs to decide whether a missing DLL is causal."
        ),
        "device_claim": "UNPROVEN",
        "next_gate": "CAPTURE_EXACT_RUNTIME_FINGERPRINT_WITH_FIRST_EA_APP_DEVICE_LOG",
    }


def main() -> int:
    default = pathlib.Path(__file__).resolve().parents[1] / "app" / "Madeira" / "arm64ec-windows"
    ap = argparse.ArgumentParser(description="Audit/fingerprint Madeira ARM64EC runtime for Sims 4")
    ap.add_argument("runtime_root", nargs="?", type=pathlib.Path, default=default)
    ap.add_argument("--json", dest="json_path", type=pathlib.Path)
    ap.add_argument("--include-files", action="store_true", help="Include the full file inventory in JSON")
    args = ap.parse_args()

    report = audit(args.runtime_root)
    if args.include_files:
        report["files"] = [asdict(r) for r in collect_files(args.runtime_root.resolve())]
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["runtime_exists"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
