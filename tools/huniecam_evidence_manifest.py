#!/usr/bin/env python3
"""Create a privacy-minimal manifest for one HunieCam/Madeira evidence set.

The manifest hashes source evidence and copies only small structured summaries.
It does not embed raw logs, save contents, proprietary binaries, absolute paths,
Steam tokens, pairing material, or credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_EVIDENCE_MANIFEST_V1"


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def descriptor(path: pathlib.Path | None, kind: str) -> dict[str, Any] | None:
    if path is None:
        return None
    st = path.stat()
    return {"kind": kind, "name": path.name, "bytes": st.st_size, "sha256": sha256(path)}


def load_json(path: pathlib.Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def summary(kind: str, data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    if kind == "preflight":
        ident = data.get("identity", {})
        runtime = data.get("runtime_signals", {})
        return {
            "schema": data.get("schema"),
            "exe_found": data.get("exe_found"),
            "exe_sha256": ident.get("exe_sha256"),
            "architecture": ident.get("pe", {}).get("architecture") if isinstance(ident.get("pe"), dict) else None,
            "runtime_family": runtime.get("runtime_family"),
            "unity_versions_seen": runtime.get("unity_versions_seen"),
            "depot_shape": data.get("depot_shape"),
        }
    if kind == "session":
        return {
            "schema": data.get("schema"),
            "deepest_stage": data.get("deepest_stage"),
            "deepest_stage_name": data.get("deepest_stage_name"),
            "marker_codes": [m.get("code") for m in data.get("markers", [])],
            "failure_codes": [f.get("code") for f in data.get("failures", [])],
            "next_priority": data.get("next", {}).get("priority") if isinstance(data.get("next"), dict) else None,
        }
    if kind == "guard":
        return {"schema": data.get("schema"), "status": data.get("status"), "experiment": data.get("experiment"), "changes": data.get("changes")}
    if kind == "issues":
        return {"schema": data.get("schema"), "best_match": data.get("best_match"), "explicit_nonmatches": data.get("explicit_nonmatches")}
    if kind == "ledger":
        attempts = data.get("attempts", [])
        return {"schema": data.get("schema"), "attempt_count": len(attempts), "best_stage": data.get("best_stage"), "best_attempt": data.get("best_attempt")}
    if kind.startswith("save"):
        return {"schema": data.get("schema"), "tree_sha256": data.get("tree_sha256"), "file_count": data.get("file_count"), "progress_write_detected": data.get("progress_write_detected")}
    if kind == "acceptance":
        return {"schema": data.get("schema"), "overall": data.get("overall"), "accepted": data.get("accepted"), "counts": data.get("counts"), "next_unproven_gate": data.get("next_unproven_gate")}
    return {"schema": data.get("schema")}


def build(inputs: dict[str, pathlib.Path | None]) -> dict[str, Any]:
    structured_kinds = {"preflight", "session", "guard", "issues", "ledger", "save_after", "save_relaunch", "acceptance"}
    files: list[dict[str, Any]] = []
    summaries: dict[str, Any] = {}
    for kind, path in inputs.items():
        if path is None:
            continue
        files.append(descriptor(path, kind))  # type: ignore[arg-type]
        if kind in structured_kinds:
            data = load_json(path)
            summaries[kind] = summary(kind, data)

    present = {f["kind"] for f in files}
    minimum_review = {"preflight", "session", "madeira_log"}.issubset(present)
    acceptance_complete = bool((summaries.get("acceptance") or {}).get("accepted"))
    integrity_warnings = []

    guard = summaries.get("guard") or {}
    if guard.get("status") == "FAIL":
        integrity_warnings.append("The config guard rejected this run profile; do not promote it as valid evidence.")

    pre = summaries.get("preflight") or {}
    if pre and not pre.get("exe_sha256"):
        integrity_warnings.append("Preflight is present but lacks an executable SHA-256 identity.")

    session = summaries.get("session") or {}
    if session and not session.get("deepest_stage") and "madeira_log" in present:
        integrity_warnings.append("A Madeira log is present but the structured session report proves no game stage; inspect whether the correct log was analyzed.")

    return {
        "schema": SCHEMA,
        "title": "HunieCam Studio",
        "steam_app_id": 426000,
        "files": sorted(files, key=lambda x: x["kind"]),
        "summaries": summaries,
        "minimum_review_bundle_complete": minimum_review,
        "device_acceptance_complete": acceptance_complete,
        "integrity_warnings": integrity_warnings,
        "privacy": {
            "raw_logs_embedded": False,
            "save_contents_embedded": False,
            "absolute_paths_embedded": False,
            "credentials_embedded": False,
        },
        "rule": "Share the manifest plus only the raw evidence specifically needed for the current blocker. Never add Steam credentials, JIT pairing secrets, or proprietary game binaries.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Build a HunieCam/Madeira evidence manifest")
    for name in ("preflight", "session", "guard", "issues", "ledger", "save-after", "save-relaunch", "acceptance", "madeira-log", "unity-log"):
        p.add_argument(f"--{name}", dest=name.replace("-", "_"), type=pathlib.Path)
    p.add_argument("--json", dest="json_path", type=pathlib.Path, required=True)
    args = p.parse_args()
    inputs = {
        "preflight": args.preflight,
        "session": args.session,
        "guard": args.guard,
        "issues": args.issues,
        "ledger": args.ledger,
        "save_after": args.save_after,
        "save_relaunch": args.save_relaunch,
        "acceptance": args.acceptance,
        "madeira_log": args.madeira_log,
        "unity_log": args.unity_log,
    }
    report = build(inputs)
    args.json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
