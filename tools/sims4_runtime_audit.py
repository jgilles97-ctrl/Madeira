#!/usr/bin/env python3
"""Fingerprint and audit Madeira's staged ARM64EC Windows runtime for Sims/EA tests.

The audit is deliberately conservative: launcher-risk modules are evidence targets,
not assumed requirements. Missing risk modules do not fail the audit by themselves.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from dataclasses import dataclass, asdict

SCHEMA = "SIMS4_MADEIRA_RUNTIME_AUDIT_V1"

# These have appeared as missing/important in Madeira secondary-launcher work.
# They are NOT asserted to be EA App requirements until a device/import log proves it.
LAUNCHER_RISK_MODULES = (
    "netprofm.dll",
    "sensapi.dll",
    "avifil32.dll",
    "msvfw32.dll",
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

    def state(name: str, evidence_only: bool = False) -> dict[str, object]:
        rec = by_name.get(name.lower())
        if rec:
            return {
                "status": "bundled",
                "path": rec.relative_path,
                "size": rec.size,
                "sha256": rec.sha256,
                "requires_device_import_evidence": False,
            }
        return {
            "status": "not_bundled",
            "path": None,
            "requires_device_import_evidence": evidence_only,
        }

    core = {name: state(name) for name in CORE_SIGNAL_MODULES}
    risk = {name: state(name, True) for name in LAUNCHER_RISK_MODULES}
    total_bytes = sum(r.size for r in records)

    return {
        "schema": SCHEMA,
        "runtime_root": str(root),
        "runtime_exists": root.is_dir(),
        "file_count": len(records),
        "total_bytes": total_bytes,
        "runtime_fingerprint_sha256": fingerprint(records),
        "core_signal_modules": core,
        "launcher_risk_modules": risk,
        "launcher_risk_policy": (
            "Missing launcher-risk modules are NOT a failure. Build/add one only after "
            "a device/import log or controlled canary proves it is needed."
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
