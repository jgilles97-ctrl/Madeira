#!/usr/bin/env python3
"""Compare two HunieCam Madeira attempts without rewarding confounded tests.

Cycle 5 adds provenance locking: when run records are supplied, different owned
binaries are never treated as an A/B experiment. The older session/profile-only
interface remains available for existing evidence files.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_RUN_COMPARE_V2"
IGNORE_PROFILE_KEYS = {"note", "notes", "timestamp", "date", "evidence", "attempt", "label"}


def load(path: pathlib.Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        for key in sorted(value):
            if key in IGNORE_PROFILE_KEYS:
                continue
            name = f"{prefix}.{key}" if prefix else key
            out.update(flatten(value[key], name))
    elif isinstance(value, list):
        out[prefix] = value
    else:
        out[prefix] = value
    return out


def profile_changes(before: dict[str, Any] | None, after: dict[str, Any] | None) -> list[dict[str, Any]]:
    if before is None or after is None:
        return []
    a = flatten(before)
    b = flatten(after)
    changes = []
    for key in sorted(set(a) | set(b)):
        if a.get(key) != b.get(key):
            changes.append({"key": key, "before": a.get(key), "after": b.get(key)})
    return changes


def failure_codes(session: dict[str, Any] | None) -> set[str]:
    if not session:
        return set()
    return {str(item.get("code")) for item in session.get("failures", []) if isinstance(item, dict) and item.get("code")}


def _record_build(record: dict[str, Any] | None) -> str | None:
    if not record:
        return None
    build = record.get("build") if isinstance(record.get("build"), dict) else {}
    return build.get("fingerprint_sha256")


def _record_profile(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if not record:
        return None
    return record.get("profile") if isinstance(record.get("profile"), dict) else None


def compare(
    before_session: dict[str, Any] | None,
    after_session: dict[str, Any] | None,
    before_profile: dict[str, Any] | None = None,
    after_profile: dict[str, Any] | None = None,
    before_record: dict[str, Any] | None = None,
    after_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provenance_errors: list[str] = []
    before_build = _record_build(before_record)
    after_build = _record_build(after_record)
    if before_record is not None or after_record is not None:
        if not before_record or not after_record:
            provenance_errors.append("Both run records are required when provenance locking is used.")
        elif not before_record.get("ready_for_comparison") or not after_record.get("ready_for_comparison"):
            provenance_errors.append("One or both run records are not marked ready_for_comparison.")
        elif not before_build or not after_build:
            provenance_errors.append("One or both run records are missing an owned-build fingerprint.")
        elif before_build != after_build:
            provenance_errors.append("The runs came from different owned game binaries/build fingerprints; this is not a valid A/B comparison.")
        if before_profile is None:
            before_profile = _record_profile(before_record)
        if after_profile is None:
            after_profile = _record_profile(after_record)

    before_stage = int((before_session or {}).get("deepest_stage", 0))
    after_stage = int((after_session or {}).get("deepest_stage", 0))
    delta = after_stage - before_stage
    changes = profile_changes(before_profile, after_profile)
    before_fail = failure_codes(before_session)
    after_fail = failure_codes(after_session)
    introduced = sorted(after_fail - before_fail)
    cleared = sorted(before_fail - after_fail)

    if provenance_errors:
        verdict = "INVALID_PROVENANCE"
        useful = False
        reason = provenance_errors[0]
    elif len(changes) > 1:
        verdict = "AMBIGUOUS_MULTI_CHANGE"
        useful = False
        reason = "More than one launch/profile variable changed, so this run cannot prove which change caused the result."
    elif delta > 0:
        verdict = "DEEPER"
        useful = True
        reason = "The newer run reached a deeper proven stage."
    elif delta < 0:
        verdict = "REGRESSION"
        useful = True
        reason = "The newer run stopped earlier than the baseline."
    elif introduced and not cleared:
        verdict = "REGRESSION_NEW_FAILURE"
        useful = True
        reason = "Stage depth did not improve and a new classified failure appeared."
    elif cleared and not introduced:
        verdict = "IMPROVED_FAILURE_SET"
        useful = True
        reason = "Stage depth is unchanged, but a previous classified failure disappeared."
    else:
        verdict = "NO_PROVEN_MOVEMENT"
        useful = True
        reason = "No deeper stage or clear failure-set improvement was proven."

    keep_change = bool(not provenance_errors and len(changes) == 1 and verdict in {"DEEPER", "IMPROVED_FAILURE_SET"})
    if provenance_errors:
        action = "Do not compare or promote either setting. Re-run against the same hashed owned build and regenerate provenance records."
    elif keep_change:
        action = "Keep the single change for the next confirmation run."
    elif len(changes) == 1:
        action = "Roll back the experiment unless independent device evidence shows a specific benefit."
    elif len(changes) > 1:
        action = "Return to the last clean profile and change only one variable."
    else:
        action = "Keep the clean profile and collect more evidence before adding a switch."

    perf_same_baseline = None
    if before_record and after_record:
        p0 = _record_profile(before_record) or {}
        p1 = _record_profile(after_record) or {}
        perf_same_baseline = all(p0.get(k) == p1.get(k) for k in ("resolution", "display", "fps"))

    return {
        "schema": SCHEMA,
        "before_stage": before_stage,
        "after_stage": after_stage,
        "stage_delta": delta,
        "profile_changes": changes,
        "changed_variable_count": len(changes),
        "cleared_failures": cleared,
        "introduced_failures": introduced,
        "provenance": {
            "locked": before_record is not None or after_record is not None,
            "before_build_fingerprint": before_build,
            "after_build_fingerprint": after_build,
            "same_owned_build": bool(before_build and after_build and before_build == after_build) if (before_record or after_record) else None,
            "errors": provenance_errors,
        },
        "performance_baseline_same": perf_same_baseline,
        "verdict": verdict,
        "comparison_useful": useful,
        "keep_single_change": keep_change,
        "reason": reason,
        "next_action": action,
        "rule": "A compatibility change is retained only when the same owned build was tested, one variable changed, and evidence shows a deeper stage or clearly improved failure set.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two HunieCam Madeira attempts")
    parser.add_argument("--before-session", type=pathlib.Path, required=True)
    parser.add_argument("--after-session", type=pathlib.Path, required=True)
    parser.add_argument("--before-profile", type=pathlib.Path)
    parser.add_argument("--after-profile", type=pathlib.Path)
    parser.add_argument("--before-record", type=pathlib.Path)
    parser.add_argument("--after-record", type=pathlib.Path)
    parser.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = parser.parse_args()
    report = compare(
        load(args.before_session), load(args.after_session),
        load(args.before_profile), load(args.after_profile),
        load(args.before_record), load(args.after_record),
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["comparison_useful"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
