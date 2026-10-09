#!/usr/bin/env python3
"""Choose the next HunieCam iPad run from evidence without experiment creep."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_NEXT_RUN_V1"


def load(path: pathlib.Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def profile(config: str, arguments: str, launch_mode: str = "direct", resolution: str = "1280x720", fps: int = 60) -> dict[str, Any]:
    p = {"launch_mode": launch_mode, "resolution": resolution, "fps": fps, "config": config.strip(), "arguments": arguments.strip()}
    canonical = json.dumps(p, sort_keys=True, separators=(",", ":"))
    p["sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return p


def choose(session: dict[str, Any], issues: dict[str, Any] | None = None, ledger: dict[str, Any] | None = None) -> dict[str, Any]:
    nxt = session.get("next", {}) if isinstance(session.get("next"), dict) else {}
    priority = str(nxt.get("priority") or "more evidence")
    experiment = nxt.get("experiment", {}) if isinstance(nxt.get("experiment"), dict) else {}
    config = str(experiment.get("config") or "")
    arguments = str(experiment.get("arguments") or "")
    proposed = profile(config, arguments)

    attempts = (ledger or {}).get("attempts", []) if isinstance(ledger, dict) else []
    same = [a for a in attempts if a.get("profile_sha256") == proposed["sha256"]]
    best_stage = int((ledger or {}).get("best_stage", 0)) if ledger else 0
    current_stage = int(session.get("deepest_stage", 0))
    issue = (issues or {}).get("best_match") if isinstance(issues, dict) else None

    runtime_block = False
    if isinstance(issue, dict) and int(issue.get("issue", 0)) in {121, 123, 173}:
        # #123 only becomes a runtime block when session triage did not offer the
        # controlled RWX experiment. #173 and stale-DXMT #121 should not be tuned around.
        if int(issue.get("issue", 0)) in {121, 173} or priority.startswith("WoW64 breakpoint"):
            runtime_block = True

    if runtime_block:
        return {
            "schema": SCHEMA,
            "status": "BLOCKED_ON_RUNTIME_EVIDENCE",
            "priority": priority,
            "run_now": False,
            "profile": profile("", ""),
            "action": nxt.get("action"),
            "upstream_issue": issue,
            "reason": "The best evidence points to a Madeira runtime failure family. Do not hide it with unrelated title switches.",
        }

    if priority == "device acceptance":
        return {
            "schema": SCHEMA,
            "status": "RUN_ACCEPTANCE_BASELINE",
            "priority": priority,
            "run_now": True,
            "purpose": "acceptance",
            "profile": profile("", ""),
            "action": nxt.get("action"),
            "reason": "Startup reached game code. Stop compatibility tuning and prove gameplay/input/audio/save/stability on the cleanest working profile.",
        }

    if priority in {"runtime prerequisite", "WoW64 address space", "Windows dependency", "remove incompatible Mono suspend override"}:
        return {
            "schema": SCHEMA,
            "status": "FIX_PREREQUISITE_THEN_RERUN_BASELINE",
            "priority": priority,
            "run_now": False,
            "profile": profile("", ""),
            "action": nxt.get("action"),
            "reason": "This blocker should be fixed before another compatibility A/B run.",
        }

    if same:
        # Repeating a diagnostic profile can be useful only if no better stage was
        # ever reached or if the caller deliberately changes purpose to acceptance.
        same_best = max(int(a.get("deepest_stage", 0)) for a in same)
        return {
            "schema": SCHEMA,
            "status": "DUPLICATE_DIAGNOSTIC_PROFILE",
            "priority": priority,
            "run_now": False,
            "profile": proposed,
            "previous_attempts": [a.get("index") for a in same],
            "previous_same_profile_best_stage": same_best,
            "overall_best_stage": best_stage,
            "action": "Do not repeat this diagnostic profile by habit. If reproducibility is the goal, record the next run as repeatability; otherwise roll back or choose a new evidence-backed single variable.",
        }

    return {
        "schema": SCHEMA,
        "status": "RUN_SINGLE_VARIABLE_EXPERIMENT" if (config or arguments) else "RUN_CLEAN_BASELINE",
        "priority": priority,
        "run_now": True,
        "purpose": "diagnostic",
        "profile": proposed,
        "action": nxt.get("action"),
        "experiment_name": experiment.get("name"),
        "rollback": experiment.get("rollback"),
        "current_stage": current_stage,
        "best_stage": best_stage,
        "reason": experiment.get("reason") or "Collect a clean baseline with both Madeira and Unity logs.",
        "rule": "One changed compatibility variable at a time; promote it only if evidence moves deeper or fixes the measured failure.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Choose the next evidence-backed HunieCam run")
    p.add_argument("--session", type=pathlib.Path, required=True)
    p.add_argument("--issues", type=pathlib.Path)
    p.add_argument("--ledger", type=pathlib.Path)
    p.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    report = choose(load(args.session) or {}, load(args.issues), load(args.ledger))
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
