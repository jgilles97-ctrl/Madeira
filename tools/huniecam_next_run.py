#!/usr/bin/env python3
"""Choose the next HunieCam iPad run from evidence without experiment creep.

Cycle 5 adds profile/evidence/performance gates. Reaching game code is not enough
to begin final acceptance if the tested profile was rejected, evidence is mixed,
or the intended 60 FPS control was not actually measured as active.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_NEXT_RUN_V2"


def load(path: pathlib.Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def profile(config: str, arguments: str, launch_mode: str = "direct", resolution: str = "1280x720", fps: int = 60) -> dict[str, Any]:
    p = {"launch_mode": launch_mode, "resolution": resolution, "fps": fps, "config": config.strip(), "arguments": arguments.strip()}
    canonical = json.dumps(p, sort_keys=True, separators=(",", ":"))
    p["sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return p


def choose(
    session: dict[str, Any],
    issues: dict[str, Any] | None = None,
    ledger: dict[str, Any] | None = None,
    guard: dict[str, Any] | None = None,
    performance: dict[str, Any] | None = None,
    evidence_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
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

    # Invalid input/profile evidence wins before every title-level suggestion.
    if guard is not None and guard.get("status") == "FAIL":
        return {
            "schema": SCHEMA,
            "status": "BLOCK_INVALID_PROFILE",
            "priority": "profile validation",
            "run_now": False,
            "profile": profile("", ""),
            "action": "Return to the clean profile and fix the config-guard failures before another run.",
            "guard_failures": guard.get("failures", []),
            "reason": "A guard-rejected profile cannot produce promotable HunieCam evidence.",
        }

    if evidence_contract is not None and evidence_contract.get("valid") is False:
        return {
            "schema": SCHEMA,
            "status": "BLOCK_INVALID_EVIDENCE",
            "priority": "evidence integrity",
            "run_now": False,
            "profile": profile("", ""),
            "action": "Repair the mixed/stale evidence set and regenerate the run record before interpreting this run.",
            "contract_errors": evidence_contract.get("errors", []),
            "reason": "Cross-file provenance/schema errors make the current run unsafe to compare or promote.",
        }

    runtime_block = False
    if isinstance(issue, dict) and int(issue.get("issue", 0)) in {121, 123, 173}:
        # #123 becomes a hard runtime block only when session triage did not
        # offer its one controlled RWX experiment. #173 and stale-DXMT #121
        # should not be hidden by title switches.
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

    if priority == "device acceptance":
        # Acceptance requires a valid contract. Legacy callers that do not yet
        # supply one are sent to an evidence-confirmation run rather than being
        # allowed to claim final acceptance.
        if evidence_contract is None:
            return {
                "schema": SCHEMA,
                "status": "BUILD_EVIDENCE_CONTRACT_THEN_ACCEPTANCE",
                "priority": "evidence integrity",
                "run_now": False,
                "purpose": "evidence",
                "profile": profile("", ""),
                "action": "Generate the Cycle 5 run record/evidence contract from the same baseline logs before final acceptance testing.",
                "reason": "Game code was reached, but final acceptance cannot rely on an unsealed/mixed evidence set.",
            }

        if performance is None or not performance.get("comparison_clean", False):
            cap = (performance or {}).get("fps_cap") if isinstance((performance or {}).get("fps_cap"), dict) else {}
            return {
                "schema": SCHEMA,
                "status": "RUN_ACCEPTANCE_MEASUREMENT_BASELINE",
                "priority": "measured baseline",
                "run_now": True,
                "purpose": "acceptance-measurement",
                "profile": profile("", ""),
                "action": "Repeat the clean working profile with FPS/device-load measurements until the intended 60 FPS cap and clean device state are proven.",
                "fps_cap_effective": cap.get("effective") if isinstance(cap, dict) else None,
                "performance_warnings": (performance or {}).get("warnings", []),
                "reason": "Startup reached game code, but performance/timing evidence is missing or contaminated. Do not add a compatibility switch; measure the clean profile.",
            }

        return {
            "schema": SCHEMA,
            "status": "RUN_ACCEPTANCE_BASELINE",
            "priority": priority,
            "run_now": True,
            "purpose": "acceptance",
            "profile": profile("", ""),
            "action": nxt.get("action"),
            "reason": "Game code was reached on a provenance-valid, measured clean profile. Stop compatibility tuning and prove gameplay/input/audio/save/stability.",
        }

    if same:
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
        "guard_status": guard.get("status") if guard else None,
        "reason": experiment.get("reason") or "Collect a clean baseline with both Madeira and Unity logs.",
        "rule": "One changed compatibility variable at a time; promote it only when the same owned build moves deeper or fixes the measured failure.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Choose the next evidence-backed HunieCam run")
    p.add_argument("--session", type=pathlib.Path, required=True)
    p.add_argument("--issues", type=pathlib.Path)
    p.add_argument("--ledger", type=pathlib.Path)
    p.add_argument("--guard", type=pathlib.Path)
    p.add_argument("--performance", type=pathlib.Path)
    p.add_argument("--evidence-contract", type=pathlib.Path)
    p.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    report = choose(
        load(args.session) or {}, load(args.issues), load(args.ledger),
        load(args.guard), load(args.performance), load(args.evidence_contract),
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
