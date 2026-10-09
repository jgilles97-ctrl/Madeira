#!/usr/bin/env python3
"""Prove HunieCam cold-launch repeatability from sealed run contexts.

For final acceptance, three checkboxes are weaker than three distinct launch IDs.
This helper requires every supplied context to be ready, unique, on the same
owned build/profile, free of triaged fatal codes, and at/above the requested
runtime stage. It stores fingerprints and stages only; no raw logs are embedded.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_REPEATABILITY_V1"


def analyze(contexts: list[dict[str, Any]], minimum_runs: int = 3, minimum_stage: int = 75) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    for index, ctx in enumerate(contexts, 1):
        summary = ctx.get("session_summary") if isinstance(ctx.get("session_summary"), dict) else {}
        row = {
            "index": index,
            "schema": ctx.get("schema"),
            "ready": bool(ctx.get("ready")),
            "run_id_sha256": ctx.get("run_id_sha256"),
            "build_fingerprint_sha256": ctx.get("build_fingerprint_sha256"),
            "profile_sha256": ctx.get("profile_sha256"),
            "deepest_stage": int(summary.get("deepest_stage", 0)),
            "failure_codes": sorted(str(x) for x in summary.get("failure_codes", []) if x),
        }
        rows.append(row)
        if row["schema"] != "MADEIRA_HUNIECAM_RUN_CONTEXT_V1":
            errors.append(f"Run {index} has unsupported context schema {row['schema']!r}.")
        if not row["ready"] or not row["run_id_sha256"]:
            errors.append(f"Run {index} is not a sealed/ready launch context.")
        if row["deepest_stage"] < minimum_stage:
            errors.append(f"Run {index} reached stage {row['deepest_stage']}, below required stage {minimum_stage}.")
        if row["failure_codes"]:
            errors.append(f"Run {index} contains triaged failure code(s): {', '.join(row['failure_codes'])}.")

    run_ids = [r["run_id_sha256"] for r in rows if r["run_id_sha256"]]
    unique_ids = set(run_ids)
    builds = {r["build_fingerprint_sha256"] for r in rows if r["build_fingerprint_sha256"]}
    profiles = {r["profile_sha256"] for r in rows if r["profile_sha256"]}
    if len(rows) < minimum_runs:
        errors.append(f"Need at least {minimum_runs} sealed cold launches; received {len(rows)}.")
    if len(unique_ids) != len(run_ids):
        errors.append("Duplicate run IDs were supplied; repeated copies of one launch do not prove cold-launch repeatability.")
    if len(unique_ids) < minimum_runs:
        errors.append(f"Need at least {minimum_runs} unique run IDs; found {len(unique_ids)}.")
    if len(builds) != 1:
        errors.append("Cold-launch contexts do not all use one identical owned-build fingerprint.")
    if len(profiles) != 1:
        errors.append("Cold-launch contexts do not all use one identical launch-profile fingerprint.")
    if len(rows) > minimum_runs:
        warnings.append("More than the minimum number of launches were supplied; every supplied launch is still required to satisfy the repeatability rules.")

    return {
        "schema": SCHEMA,
        "passed": not errors,
        "minimum_runs": minimum_runs,
        "minimum_stage": minimum_stage,
        "run_count": len(rows),
        "unique_run_count": len(unique_ids),
        "build_fingerprint_sha256": next(iter(builds)) if len(builds) == 1 else None,
        "profile_sha256": next(iter(profiles)) if len(profiles) == 1 else None,
        "runs": rows,
        "errors": errors,
        "warnings": warnings,
        "rule": "Three cold launches means three distinct sealed run IDs on the same owned build/profile, each independently reaching the required game stage without a triaged fatal error.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Verify HunieCam cold-launch repeatability")
    p.add_argument("contexts", nargs="+", type=pathlib.Path, help="Sealed huniecam-run-context.json files from distinct launches")
    p.add_argument("--minimum-runs", type=int, default=3)
    p.add_argument("--minimum-stage", type=int, default=75)
    p.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    if args.minimum_runs < 1 or args.minimum_stage < 0:
        p.error("minimum-runs must be >=1 and minimum-stage must be >=0")
    contexts = [json.loads(path.read_text(encoding="utf-8")) for path in args.contexts]
    report = analyze(contexts, args.minimum_runs, args.minimum_stage)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
