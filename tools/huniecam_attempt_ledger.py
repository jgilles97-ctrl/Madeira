#!/usr/bin/env python3
"""Maintain a machine-readable HunieCam compatibility attempt ledger.

The ledger stores only diagnostic metadata, not proprietary game content. It
fingerprints each launch profile, records the deepest proven stage, and says
whether a run moved the port forward, stayed level, or regressed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_ATTEMPT_LEDGER_V1"


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
        "attempts": [],
        "best_stage": 0,
        "best_attempt": None,
    }


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
    purpose: str = "diagnostic",
    note: str = "",
    now: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    out = json.loads(json.dumps(ledger or new_ledger()))
    if out.get("schema") != SCHEMA:
        raise ValueError(f"unsupported ledger schema: {out.get('schema')}")
    if guard and guard.get("status") == "FAIL":
        raise ValueError("config guard rejected this experiment; do not record/run it as a valid HunieCam attempt")
    if purpose not in {"diagnostic", "repeatability", "acceptance"}:
        raise ValueError("purpose must be diagnostic, repeatability, or acceptance")
    if launch_mode not in {"direct", "dock"}:
        raise ValueError("launch_mode must be direct or dock")
    if fps <= 0:
        raise ValueError("fps must be positive")

    profile = {
        "launch_mode": launch_mode,
        "resolution": resolution,
        "fps": fps,
        "config": config.strip(),
        "arguments": arguments.strip(),
    }
    fingerprint = profile_fingerprint(profile)
    attempts: list[dict[str, Any]] = out.setdefault("attempts", [])
    duplicates = [a for a in attempts if a.get("profile_sha256") == fingerprint]

    stage = int(session.get("deepest_stage", 0))
    old_best = int(out.get("best_stage", 0))
    if not attempts:
        movement = "BASELINE"
    elif stage > old_best:
        movement = "IMPROVED"
    elif stage < old_best:
        movement = "REGRESSED_VS_BEST"
    else:
        movement = "MATCHED_BEST"

    failure_codes = sorted({str(x.get("code")) for x in session.get("failures", []) if x.get("code")})
    marker_codes = sorted({str(x.get("code")) for x in session.get("markers", []) if x.get("code")})
    next_block = session.get("next", {}) if isinstance(session.get("next"), dict) else {}
    experiment_name = None
    if guard:
        experiment_name = guard.get("experiment")

    attempt = {
        "index": len(attempts) + 1,
        "recorded_at_utc": now or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "purpose": purpose,
        "profile": profile,
        "profile_sha256": fingerprint,
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
    if duplicates and purpose == "diagnostic":
        warnings.append("This diagnostic profile was already tried. Repeat it only if you are deliberately checking reproducibility; otherwise use the next evidence-backed single-variable experiment.")
    if movement == "REGRESSED_VS_BEST":
        warnings.append("This run did not reach the best proven stage. Roll back its single changed variable unless the regression itself is the intended test result.")

    summary = {
        "attempt": attempt,
        "best_stage": out["best_stage"],
        "best_attempt": out["best_attempt"],
        "warnings": warnings,
        "recommendation": "Keep" if movement == "IMPROVED" else "Control/repeat" if purpose in {"repeatability", "acceptance"} else "Do not promote this profile yet",
    }
    return out, summary


def main() -> int:
    p = argparse.ArgumentParser(description="Append one HunieCam Madeira run to the evidence ledger")
    p.add_argument("--session", type=pathlib.Path, required=True)
    p.add_argument("--guard", type=pathlib.Path)
    p.add_argument("--ledger", type=pathlib.Path)
    p.add_argument("--out", type=pathlib.Path, required=True)
    p.add_argument("--launch-mode", choices=["direct", "dock"], default="direct")
    p.add_argument("--resolution", default="1280x720")
    p.add_argument("--fps", type=int, default=60)
    p.add_argument("--config", default="")
    p.add_argument("--arguments", default="")
    p.add_argument("--purpose", choices=["diagnostic", "repeatability", "acceptance"], default="diagnostic")
    p.add_argument("--note", default="")
    args = p.parse_args()

    session = json.loads(args.session.read_text(encoding="utf-8"))
    guard = load(args.guard)
    ledger, summary = add_attempt(
        load(args.ledger), session, guard,
        launch_mode=args.launch_mode, resolution=args.resolution, fps=args.fps,
        config=args.config, arguments=args.arguments, purpose=args.purpose, note=args.note,
    )
    args.out.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
