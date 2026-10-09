#!/usr/bin/env python3
"""Run the HunieCam compatibility analysis pipeline without touching game files.

Cycle 5 joins preflight, guard, session, performance, upstream issue matching,
next-run choice, provenance-locked run record, evidence contract, and a
privacy-minimal manifest. The tool never launches the game and never modifies
the install or Madeira prefix.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

import huniecam_config_guard as config_guard
import huniecam_evidence_contract as evidence_contract
import huniecam_evidence_manifest as evidence_manifest
import huniecam_issue_matcher as issue_matcher
import huniecam_next_run as next_run
import huniecam_performance as performance_tool
import huniecam_probe as probe
import huniecam_run_record as run_record_tool
import huniecam_session_triage as session_triage
import huniecam_storage_guard as storage_guard

SCHEMA = "MADEIRA_HUNIECAM_PIPELINE_V2"


def read_text(path: pathlib.Path | None) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path else ""


def write_json(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(
    install: pathlib.Path,
    madeira_log: pathlib.Path,
    unity_log: pathlib.Path | None,
    out_dir: pathlib.Path,
    *,
    config_text: str = "",
    arguments: str = "",
    ledger: dict[str, Any] | None = None,
    storage_root: pathlib.Path | None = None,
    launch_mode: str = "direct",
    resolution: str = "1280x720",
    display: str = "fit",
    fps: int = 60,
    bits: int = 32,
    relative_executable: str | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    pre = probe.probe_install(install)
    guard = config_guard.inspect(config_text, arguments)
    madeira_text = read_text(madeira_log)
    unity_text = read_text(unity_log)
    session = session_triage.analyze(madeira_text, unity_text, pre)
    issues = issue_matcher.match(madeira_text + "\n" + unity_text, pre)
    perf = performance_tool.analyze(madeira_text + "\n" + unity_text, expected_fps=fps)
    nxt = next_run.choose(session, issues, ledger)

    profile = {
        "launch_mode": launch_mode,
        "resolution": resolution,
        "display": display,
        "fps": fps,
        "bits": bits,
        "config": config_text.strip(),
        "arguments": arguments.strip(),
        "relative_executable": relative_executable,
    }
    record = run_record_tool.build(pre, session, profile, perf)
    contract = evidence_contract.validate(pre, session, guard, perf, record)

    paths = {
        "preflight": out_dir / "huniecam-preflight.json",
        "guard": out_dir / "huniecam-guard.json",
        "session": out_dir / "huniecam-session.json",
        "issues": out_dir / "huniecam-issues.json",
        "performance": out_dir / "huniecam-performance.json",
        "next": out_dir / "huniecam-next-run.json",
        "run_record": out_dir / "huniecam-run-record.json",
        "contract": out_dir / "huniecam-evidence-contract.json",
    }
    for key, value in (
        ("preflight", pre), ("guard", guard), ("session", session),
        ("issues", issues), ("performance", perf), ("next", nxt),
        ("run_record", record), ("contract", contract),
    ):
        write_json(paths[key], value)

    storage = None
    if storage_root:
        storage = storage_guard.scan(storage_root)
        write_json(out_dir / "huniecam-storage.json", storage)

    manifest_inputs: dict[str, pathlib.Path | None] = {
        "preflight": paths["preflight"],
        "session": paths["session"],
        "guard": paths["guard"],
        "issues": paths["issues"],
        "performance": paths["performance"],
        "run_record": paths["run_record"],
        "contract": paths["contract"],
        "madeira_log": madeira_log,
        "unity_log": unity_log,
    }
    manifest = evidence_manifest.build(manifest_inputs)
    manifest_path = out_dir / "huniecam-evidence-manifest.json"
    write_json(manifest_path, manifest)

    summary = {
        "schema": SCHEMA,
        "output_directory": out_dir.name,
        "guard_status": guard.get("status"),
        "evidence_contract_valid": contract.get("valid"),
        "run_record_ready": record.get("ready_for_comparison"),
        "owned_build_fingerprint": (record.get("build") or {}).get("fingerprint_sha256") if isinstance(record.get("build"), dict) else None,
        "deepest_stage": session.get("deepest_stage"),
        "deepest_stage_name": session.get("deepest_stage_name"),
        "best_upstream_issue_match": (issues.get("best_match") or {}).get("issue") if isinstance(issues.get("best_match"), dict) else None,
        "performance_comparison_clean": perf.get("comparison_clean"),
        "fps_cap_effective": ((perf.get("fps_cap") or {}).get("effective") if isinstance(perf.get("fps_cap"), dict) else None),
        "next_run_status": nxt.get("status"),
        "next_run_priority": nxt.get("priority"),
        "next_run_profile": nxt.get("profile"),
        "storage_large_jit_dumps": storage.get("large_jit_dump_count") if storage else None,
        "evidence_manifest": manifest_path.name,
        "outputs": [p.name for p in paths.values()] + [manifest_path.name] + (["huniecam-storage.json"] if storage else []),
        "rule": "Do not run a guard-rejected profile. Do not compare evidence when the contract is invalid. Performance is not comparable until the intended FPS cap and device state are proven clean.",
    }
    write_json(out_dir / "huniecam-pipeline-summary.json", summary)
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description="Run HunieCam Madeira compatibility analysis in one command")
    p.add_argument("--install", type=pathlib.Path, required=True)
    p.add_argument("--madeira-log", type=pathlib.Path, required=True)
    p.add_argument("--unity-log", type=pathlib.Path)
    p.add_argument("--config", type=pathlib.Path)
    p.add_argument("--arguments", default="")
    p.add_argument("--ledger", type=pathlib.Path)
    p.add_argument("--storage-root", type=pathlib.Path)
    p.add_argument("--launch-mode", choices=["direct", "dock"], default="direct")
    p.add_argument("--resolution", default="1280x720")
    p.add_argument("--display", default="fit")
    p.add_argument("--fps", type=int, default=60)
    p.add_argument("--bits", type=int, default=32)
    p.add_argument("--relative-executable")
    p.add_argument("--out-dir", type=pathlib.Path, required=True)
    args = p.parse_args()
    ledger = json.loads(args.ledger.read_text(encoding="utf-8")) if args.ledger else None
    summary = run(
        args.install, args.madeira_log, args.unity_log, args.out_dir,
        config_text=read_text(args.config), arguments=args.arguments,
        ledger=ledger, storage_root=args.storage_root,
        launch_mode=args.launch_mode, resolution=args.resolution, display=args.display,
        fps=args.fps, bits=args.bits, relative_executable=args.relative_executable,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["guard_status"] != "FAIL" and summary["evidence_contract_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
