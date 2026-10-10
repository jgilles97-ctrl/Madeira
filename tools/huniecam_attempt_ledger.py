#!/usr/bin/env python3
"""Maintain a machine-readable HunieCam compatibility attempt ledger.

Cycle 8 V4 records Madeira input mode and locks an experiment series to both the
owned HunieCam build and the exact audited Madeira/Wine/FEX/DXMT runtime set.
That prevents results from different emulator/runtime builds from being blended
into one apparent progression or repeatability series.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_ATTEMPT_LEDGER_V4"
LEGACY_SCHEMAS = {
    "MADEIRA_HUNIECAM_ATTEMPT_LEDGER_V1",
    "MADEIRA_HUNIECAM_ATTEMPT_LEDGER_V2",
    "MADEIRA_HUNIECAM_ATTEMPT_LEDGER_V3",
}
RUNTIME_SCHEMA = "MADEIRA_HUNIECAM_RUNTIME_BUNDLE_AUDIT_V1"
INPUT_MODES = {"direct_finger", "touch_pointer", "hardware_mouse", "hardware_trackpad"}


def load(path: pathlib.Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def profile_fingerprint(profile: dict[str, Any]) -> str:
    canonical = json.dumps(profile, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def new_ledger() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "title": "HunieCam Studio",
        "steam_app_id": 426000,
        "owned_build_fingerprint": None,
        "runtime_set_sha256": None,
        "attempts": [],
        "best_stage": 0,
        "best_attempt": None,
    }


def _migrate(ledger: dict[str, Any] | None) -> dict[str, Any]:
    if ledger is None:
        return new_ledger()
    out = json.loads(json.dumps(ledger))
    schema = out.get("schema")
    if schema in LEGACY_SCHEMAS:
        out["schema"] = SCHEMA
        out.setdefault("owned_build_fingerprint", None)
        out.setdefault("runtime_set_sha256", None)
        for attempt in out.get("attempts", []):
            if not isinstance(attempt, dict):
                continue
            attempt.setdefault("owned_build_fingerprint", None)
            attempt.setdefault("runtime_set_sha256", None)
            if isinstance(attempt.get("profile"), dict):
                attempt["profile"].setdefault("display", "unknown-legacy")
                attempt["profile"].setdefault("input_mode", "unknown-legacy")
    elif schema != SCHEMA:
        raise ValueError(f"unsupported ledger schema: {schema}")
    return out


def _record_build_fingerprint(run_record: dict[str, Any] | None) -> str | None:
    if not run_record:
        return None
    if run_record.get("schema") != "MADEIRA_HUNIECAM_RUN_RECORD_V1":
        raise ValueError(f"unsupported run record schema: {run_record.get('schema')}")
    if not run_record.get("ready_for_comparison"):
        raise ValueError("run record is not provenance-ready; do not add it to the HunieCam attempt ledger")
    build = run_record.get("build") if isinstance(run_record.get("build"), dict) else {}
    fingerprint = build.get("fingerprint_sha256")
    if not fingerprint:
        raise ValueError("run record has no owned-build fingerprint")
    return str(fingerprint)


def _runtime_fingerprint(runtime_audit: dict[str, Any] | None) -> str | None:
    if runtime_audit is None:
        return None
    if runtime_audit.get("schema") != RUNTIME_SCHEMA:
        raise ValueError(f"unsupported runtime audit schema: {runtime_audit.get('schema')}")
    if not runtime_audit.get("launch_ready"):
        raise ValueError("runtime audit is not launch-ready; do not spend/record a HunieCam device attempt with this Madeira build")
    if not runtime_audit.get("wow64_ready") or not runtime_audit.get("renderer_neutral_ready"):
        raise ValueError("runtime audit does not prove both WoW64/FEX and renderer-neutral readiness")
    if runtime_audit.get("errors"):
        raise ValueError("runtime audit contains errors; do not record this Madeira build as a valid HunieCam attempt")
    fingerprint = runtime_audit.get("runtime_set_sha256")
    if not fingerprint:
        raise ValueError("runtime audit has no runtime_set_sha256")
    return str(fingerprint)


def add_attempt(
    ledger: dict[str, Any] | None,
    session: dict[str, Any],
    guard: dict[str, Any] | None,
    *,
    launch_mode: str,
    resolution: str,
    fps: int,
    config: str,
    arguments: str,
    display: str = "fit",
    input_mode: str = "direct_finger",
    purpose: str = "diagnostic",
    note: str = "",
    now: str | None = None,
    run_record: dict[str, Any] | None = None,
    runtime_audit: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    out = _migrate(ledger)
    if guard and guard.get("status") == "FAIL":
        raise ValueError("config guard rejected this experiment; do not record/run it as a valid HunieCam attempt")
    if purpose not in {"diagnostic", "repeatability", "acceptance", "acceptance-measurement"}:
        raise ValueError("purpose must be diagnostic, repeatability, acceptance, or acceptance-measurement")
    if launch_mode not in {"direct", "dock"}:
        raise ValueError("launch_mode must be direct or dock")
    if not display.strip():
        raise ValueError("display mode must be recorded")
    if input_mode not in INPUT_MODES:
        raise ValueError(f"input_mode must be one of {sorted(INPUT_MODES)}")
    if fps <= 0:
        raise ValueError("fps must be positive")

    record_build = _record_build_fingerprint(run_record)
    runtime_set = _runtime_fingerprint(runtime_audit)
    locked_build = out.get("owned_build_fingerprint")
    locked_runtime = out.get("runtime_set_sha256")

    if locked_build and not record_build:
        raise ValueError("this ledger is locked to an owned build; a provenance-ready run record is required for every new attempt")
    if locked_build and record_build != locked_build:
        raise ValueError("run record belongs to a different owned HunieCam build; start a separate ledger instead of mixing binaries")
    if not locked_build and record_build:
        out["owned_build_fingerprint"] = record_build

    if locked_runtime and not runtime_set:
        raise ValueError("this ledger is locked to a Madeira runtime; the matching launch-ready Runtime Bundle Audit V1 is required for every new attempt")
    if locked_runtime and runtime_set != locked_runtime:
        raise ValueError("runtime audit belongs to a different Madeira runtime set; start a separate ledger instead of mixing emulator/runtime builds")
    if not locked_runtime and runtime_set:
        out["runtime_set_sha256"] = runtime_set

    profile = {
        "launch_mode": launch_mode,
        "resolution": resolution,
        "display": display.strip(),
        "fps": fps,
        "input_mode": input_mode,
        "config": config.strip(),
        "arguments": arguments.strip(),
    }
    fingerprint = profile_fingerprint(profile)
    attempts: list[dict[str, Any]] = out.setdefault("attempts", [])
    duplicates = [
        a for a in attempts
        if a.get("profile_sha256") == fingerprint
        and a.get("owned_build_fingerprint") == record_build
        and a.get("runtime_set_sha256") == runtime_set
    ]
    stage = int(session.get("deepest_stage", 0))

    if run_record:
        rec_session = run_record.get("session") if isinstance(run_record.get("session"), dict) else {}
        rec_stage = int(rec_session.get("deepest_stage", -1))
        if rec_stage != stage:
            raise ValueError("run record deepest stage does not match the supplied session")
        rec_profile = run_record.get("profile") if isinstance(run_record.get("profile"), dict) else {}
        for key, value in (
            ("launch_mode", launch_mode),
            ("resolution", resolution),
            ("display", display),
            ("fps", fps),
            ("input_mode", input_mode),
            ("config", config.strip()),
            ("arguments", arguments.strip()),
        ):
            if rec_profile.get(key) != value:
                raise ValueError(f"run record profile {key} does not match the ledger attempt")

    old_best = int(out.get("best_stage", 0))
    movement = (
        "BASELINE" if not attempts
        else "IMPROVED" if stage > old_best
        else "REGRESSED_VS_BEST" if stage < old_best
        else "MATCHED_BEST"
    )
    failure_codes = sorted({str(x.get("code")) for x in session.get("failures", []) if x.get("code")})
    marker_codes = sorted({str(x.get("code")) for x in session.get("markers", []) if x.get("code")})
    next_block = session.get("next", {}) if isinstance(session.get("next"), dict) else {}
    experiment_name = guard.get("experiment") if guard else None
    attempt = {
        "index": len(attempts) + 1,
        "recorded_at_utc": now or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "purpose": purpose,
        "profile": profile,
        "profile_sha256": fingerprint,
        "owned_build_fingerprint": record_build,
        "runtime_set_sha256": runtime_set,
        "duplicate_profile_before": bool(duplicates),
        "previous_same_profile_attempts": [int(a.get("index", 0)) for a in duplicates],
        "guard_status": guard.get("status") if guard else None,
        "experiment": experiment_name,
        "deepest_stage": stage,
        "deepest_stage_name": session.get("deepest_stage_name"),
        "movement": movement,
        "failure_codes": failure_codes,
        "marker_codes": marker_codes,
        "next_priority": next_block.get("priority"),
        "note": note,
    }
    attempts.append(attempt)
    if stage > old_best or out.get("best_attempt") is None:
        out["best_stage"] = stage
        out["best_attempt"] = attempt["index"]
    else:
        out["best_stage"] = old_best

    warnings = []
    if record_build is None:
        warnings.append("This legacy/unsealed attempt has no owned-build fingerprint. New device runs should include a provenance-ready run record.")
    if runtime_set is None:
        warnings.append("This legacy/unsealed attempt has no audited Madeira runtime fingerprint. New device runs should include Runtime Bundle Audit V1.")
    if duplicates and purpose == "diagnostic":
        warnings.append("This exact diagnostic profile on the same game build and Madeira runtime was already tried. Repeat it only for deliberate reproducibility checking.")
    if movement == "REGRESSED_VS_BEST":
        warnings.append("This run did not reach the best proven stage. Roll back its single changed variable unless the regression itself is the intended test result.")
    summary = {
        "attempt": attempt,
        "owned_build_fingerprint": out.get("owned_build_fingerprint"),
        "runtime_set_sha256": out.get("runtime_set_sha256"),
        "best_stage": out["best_stage"],
        "best_attempt": out["best_attempt"],
        "warnings": warnings,
        "recommendation": "Keep" if movement == "IMPROVED" else "Control/repeat" if purpose in {"repeatability", "acceptance", "acceptance-measurement"} else "Do not promote this profile yet",
        "rule": "One ledger represents one owned HunieCam build on one exact Madeira runtime set. A runtime change starts a new evidence series rather than silently continuing the old one.",
    }
    return out, summary


def main() -> int:
    p = argparse.ArgumentParser(description="Append one HunieCam Madeira run to the evidence ledger")
    p.add_argument("--session", type=pathlib.Path, required=True)
    p.add_argument("--guard", type=pathlib.Path)
    p.add_argument("--run-record", type=pathlib.Path)
    p.add_argument("--runtime-audit", type=pathlib.Path, help="Runtime Bundle Audit V1 from the exact Madeira build used for this attempt")
    p.add_argument("--ledger", type=pathlib.Path)
    p.add_argument("--out", type=pathlib.Path, required=True)
    p.add_argument("--launch-mode", choices=["direct", "dock"], default="direct")
    p.add_argument("--resolution", default="1280x720")
    p.add_argument("--display", default="fit")
    p.add_argument("--fps", type=int, default=60)
    p.add_argument("--input-mode", choices=sorted(INPUT_MODES), default="direct_finger")
    p.add_argument("--config", default="")
    p.add_argument("--arguments", default="")
    p.add_argument("--purpose", choices=["diagnostic", "repeatability", "acceptance", "acceptance-measurement"], default="diagnostic")
    p.add_argument("--note", default="")
    args = p.parse_args()
    session = json.loads(args.session.read_text(encoding="utf-8"))
    guard = load(args.guard)
    ledger, summary = add_attempt(
        load(args.ledger),
        session,
        guard,
        launch_mode=args.launch_mode,
        resolution=args.resolution,
        display=args.display,
        fps=args.fps,
        input_mode=args.input_mode,
        config=args.config,
        arguments=args.arguments,
        purpose=args.purpose,
        note=args.note,
        run_record=load(args.run_record),
        runtime_audit=load(args.runtime_audit),
    )
    args.out.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
