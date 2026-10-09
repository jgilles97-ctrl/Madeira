#!/usr/bin/env python3
"""Compare two HunieCam Madeira attempts without rewarding noisy multi-change tests.

The tool consumes two session-triage JSON reports plus optional launch-profile
JSON files. It reports whether the newer run moved deeper, regressed, or stayed
at the same proven stage, and whether the comparison is scientifically useful
(one deliberate variable changed at most).
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_RUN_COMPARE_V1"
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
    return {str(item.get("code")) for item in session.get("failures", []) if item.get("code")}


def compare(
    before_session: dict[str, Any] | None,
    after_session: dict[str, Any] | None,
    before_profile: dict[str, Any] | None = None,
    after_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    before_stage = int((before_session or {}).get("deepest_stage", 0))
    after_stage = int((after_session or {}).get("deepest_stage", 0))
    delta = after_stage - before_stage
    changes = profile_changes(before_profile, after_profile)
    before_fail = failure_codes(before_session)
    after_fail = failure_codes(after_session)
    introduced = sorted(after_fail - before_fail)
    cleared = sorted(before_fail - after_fail)

    if len(changes) > 1:
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

    keep_change = bool(len(changes) == 1 and verdict in {"DEEPER", "IMPROVED_FAILURE_SET"})
    action = (
        "Keep the single change for the next confirmation run."
        if keep_change
        else "Roll back the experiment unless independent device evidence shows a specific benefit."
        if len(changes) == 1
        else "Return to the last clean profile and change only one variable."
        if len(changes) > 1
        else "Keep the clean profile and collect more evidence before adding a switch."
    )

    return {
        "schema": SCHEMA,
        "before_stage": before_stage,
        "after_stage": after_stage,
        "stage_delta": delta,
        "profile_changes": changes,
        "changed_variable_count": len(changes),
        "cleared_failures": cleared,
        "introduced_failures": introduced,
        "verdict": verdict,
        "comparison_useful": useful,
        "keep_single_change": keep_change,
        "reason": reason,
        "next_action": action,
        "rule": "A compatibility change is retained only when one variable changed and evidence shows a deeper stage or a clearly improved failure set.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two HunieCam Madeira attempts")
    parser.add_argument("--before-session", type=pathlib.Path, required=True)
    parser.add_argument("--after-session", type=pathlib.Path, required=True)
    parser.add_argument("--before-profile", type=pathlib.Path)
    parser.add_argument("--after-profile", type=pathlib.Path)
    parser.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = parser.parse_args()
    report = compare(load(args.before_session), load(args.after_session), load(args.before_profile), load(args.after_profile))
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["comparison_useful"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
