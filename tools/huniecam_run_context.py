#!/usr/bin/env python3
"""Create a deterministic identity for one HunieCam/Madeira launch evidence set.

Cycle 6 closes a provenance gap left after build/profile locking: two launches can
use the same owned binary and the same settings but still produce different logs.
A run context hashes the exact structured session, exact run record and exact
Madeira/Unity log text. Downstream tools can then refuse evidence accidentally
mixed across separate launches. A small stage summary is exposed for repeatability
checks without embedding raw logs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_RUN_CONTEXT_V1"


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_json(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return _sha_bytes(raw.encode("utf-8"))


def text_descriptor(text: str, kind: str) -> dict[str, Any]:
    encoded = text.encode("utf-8", errors="replace")
    return {
        "kind": kind,
        "present": bool(text.strip()),
        "chars": len(text),
        "lines": len(text.splitlines()),
        "text_sha256": _sha_bytes(encoded),
    }


def build(
    run_record: dict[str, Any] | None,
    session: dict[str, Any] | None,
    madeira_text: str,
    unity_text: str,
) -> dict[str, Any]:
    errors: list[str] = []
    record = run_record or {}
    sess = session or {}
    build_obj = record.get("build") if isinstance(record.get("build"), dict) else {}
    build_fp = build_obj.get("fingerprint_sha256")
    profile_fp = record.get("profile_sha256")
    if record.get("schema") != "MADEIRA_HUNIECAM_RUN_RECORD_V1":
        errors.append(f"Unsupported/missing run record schema: {record.get('schema')!r}")
    if not record.get("ready_for_comparison"):
        errors.append("Run record is not provenance-ready.")
    if not str(sess.get("schema", "")).startswith("MADEIRA_HUNIECAM_SESSION_V"):
        errors.append(f"Unsupported/missing HunieCam session schema: {sess.get('schema')!r}")
    if not build_fp:
        errors.append("Owned-build fingerprint is missing.")
    if not profile_fp:
        errors.append("Launch-profile fingerprint is missing.")

    madeira = text_descriptor(madeira_text, "madeira_log")
    unity = text_descriptor(unity_text, "unity_log")
    if not madeira["present"]:
        errors.append("Madeira log is required to identify a launch.")

    session_sha = _sha_json(sess) if sess else None
    record_sha = _sha_json(record) if record else None
    material = {
        "build_fingerprint_sha256": build_fp,
        "profile_sha256": profile_fp,
        "session_sha256": session_sha,
        "run_record_sha256": record_sha,
        "madeira_log_text_sha256": madeira["text_sha256"],
        "unity_log_text_sha256": unity["text_sha256"] if unity["present"] else None,
    }
    run_id = _sha_json(material) if build_fp and profile_fp and session_sha and record_sha and madeira["present"] else None
    failure_codes = sorted({str(x.get("code")) for x in sess.get("failures", []) if isinstance(x, dict) and x.get("code")})
    marker_codes = sorted({str(x.get("code")) for x in sess.get("markers", []) if isinstance(x, dict) and x.get("code")})
    return {
        "schema": SCHEMA,
        "title": "HunieCam Studio",
        "steam_app_id": 426000,
        "run_id_sha256": run_id,
        "build_fingerprint_sha256": build_fp,
        "profile_sha256": profile_fp,
        "session_sha256": session_sha,
        "run_record_sha256": record_sha,
        "session_summary": {
            "schema": sess.get("schema"),
            "deepest_stage": int(sess.get("deepest_stage", 0)) if sess else 0,
            "deepest_stage_name": sess.get("deepest_stage_name"),
            "failure_codes": failure_codes,
            "marker_codes": marker_codes,
        },
        "logs": {"madeira": madeira, "unity": unity},
        "material": material,
        "ready": not errors,
        "errors": errors,
        "privacy": {
            "raw_log_text_embedded": False,
            "absolute_paths_embedded": False,
            "credentials_embedded": False,
        },
        "rule": "Evidence from another launch must not be substituted merely because the EXE and settings match. The run ID binds this exact structured session, run record and log pair to this exact owned build/profile.",
    }


def _read(path: pathlib.Path | None) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path else ""


def main() -> int:
    p = argparse.ArgumentParser(description="Create one HunieCam launch run-context identity")
    p.add_argument("--run-record", type=pathlib.Path, required=True)
    p.add_argument("--session", type=pathlib.Path, required=True)
    p.add_argument("--madeira-log", type=pathlib.Path, required=True)
    p.add_argument("--unity-log", type=pathlib.Path)
    p.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    record = json.loads(args.run_record.read_text(encoding="utf-8"))
    session = json.loads(args.session.read_text(encoding="utf-8"))
    report = build(record, session, _read(args.madeira_log), _read(args.unity_log))
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
