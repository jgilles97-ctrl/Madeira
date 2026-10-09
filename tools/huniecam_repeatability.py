#!/usr/bin/env python3
"""Prove HunieCam cold-launch repeatability from sealed Run Context V2 files.

Three checkboxes are weaker than three distinct launch IDs. Each counted launch
must seal guard/performance evidence (Context V2), use the same owned build and
profile, reach the requested game stage, and carry no triaged fatal failure.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_REPEATABILITY_V2"
REQUIRED_CONTEXT_SCHEMA = "MADEIRA_HUNIECAM_RUN_CONTEXT_V2"


def analyze(contexts: list[dict[str, Any]], minimum_runs: int = 3, minimum_stage: int = 75) -> dict[str, Any]:
    errors: list[str] = []; warnings: list[str] = []; rows: list[dict[str, Any]] = []
    for index, ctx in enumerate(contexts, 1):
        summary = ctx.get("session_summary") if isinstance(ctx.get("session_summary"), dict) else {}
        row = {"index": index, "schema": ctx.get("schema"), "ready": bool(ctx.get("ready")), "run_id_sha256": ctx.get("run_id_sha256"), "build_fingerprint_sha256": ctx.get("build_fingerprint_sha256"), "profile_sha256": ctx.get("profile_sha256"), "guard_sha256": ctx.get("guard_sha256"), "performance_sha256": ctx.get("performance_sha256"), "deepest_stage": int(summary.get("deepest_stage", 0)), "failure_codes": sorted(str(x) for x in summary.get("failure_codes", []) if x)}
        rows.append(row)
        if row["schema"] != REQUIRED_CONTEXT_SCHEMA: errors.append(f"Run {index} must use {REQUIRED_CONTEXT_SCHEMA}; got {row['schema']!r}.")
        if not row["ready"] or not row["run_id_sha256"]: errors.append(f"Run {index} is not a sealed/ready launch context.")
        if not row["guard_sha256"] or not row["performance_sha256"]: errors.append(f"Run {index} does not seal both guard and performance evidence.")
        if row["deepest_stage"] < minimum_stage: errors.append(f"Run {index} reached stage {row['deepest_stage']}, below required stage {minimum_stage}.")
        if row["failure_codes"]: errors.append(f"Run {index} contains triaged failure code(s): {', '.join(row['failure_codes'])}.")

    run_ids = [r["run_id_sha256"] for r in rows if r["run_id_sha256"]]; unique_ids = set(run_ids)
    builds = {r["build_fingerprint_sha256"] for r in rows if r["build_fingerprint_sha256"]}; profiles = {r["profile_sha256"] for r in rows if r["profile_sha256"]}
    if len(rows) < minimum_runs: errors.append(f"Need at least {minimum_runs} sealed cold launches; received {len(rows)}.")
    if len(unique_ids) != len(run_ids): errors.append("Duplicate run IDs were supplied; repeated copies of one launch do not prove cold-launch repeatability.")
    if len(unique_ids) < minimum_runs: errors.append(f"Need at least {minimum_runs} unique run IDs; found {len(unique_ids)}.")
    if len(builds) != 1: errors.append("Cold-launch contexts do not all use one identical owned-build fingerprint.")
    if len(profiles) != 1: errors.append("Cold-launch contexts do not all use one identical launch-profile fingerprint.")
    if len(rows) > minimum_runs: warnings.append("More than the minimum number of launches were supplied; every supplied launch is still required to satisfy the rules.")
    return {"schema": SCHEMA, "passed": not errors, "required_context_schema": REQUIRED_CONTEXT_SCHEMA, "minimum_runs": minimum_runs, "minimum_stage": minimum_stage, "run_count": len(rows), "unique_run_count": len(unique_ids), "build_fingerprint_sha256": next(iter(builds)) if len(builds) == 1 else None, "profile_sha256": next(iter(profiles)) if len(profiles) == 1 else None, "runs": rows, "errors": errors, "warnings": warnings, "rule": "Three cold launches means three distinct Run Context V2 IDs on the same owned build/profile, each sealing guard/performance and independently reaching scene stage without a triaged fatal error."}


def main() -> int:
    p = argparse.ArgumentParser(description="Verify HunieCam cold-launch repeatability")
    p.add_argument("contexts", nargs="+", type=pathlib.Path); p.add_argument("--minimum-runs", type=int, default=3); p.add_argument("--minimum-stage", type=int, default=75); p.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    if args.minimum_runs < 1 or args.minimum_stage < 0: p.error("minimum-runs must be >=1 and minimum-stage must be >=0")
    report = analyze([json.loads(path.read_text(encoding="utf-8")) for path in args.contexts], args.minimum_runs, args.minimum_stage); rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path: args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered); return 0 if report["passed"] else 2


if __name__ == "__main__": raise SystemExit(main())
