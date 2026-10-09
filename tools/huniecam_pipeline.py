#!/usr/bin/env python3
"""Run the HunieCam compatibility analysis pipeline without touching game files.

One command turns an owned install + one device run into reproducible JSON:
preflight, config guard, session triage, upstream issue matches, next-run choice,
and a privacy-minimal evidence manifest. The tool never launches the game and
never changes the install or Madeira prefix.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

import huniecam_config_guard as config_guard
import huniecam_evidence_manifest as evidence_manifest
import huniecam_issue_matcher as issue_matcher
import huniecam_next_run as next_run
import huniecam_probe as probe
import huniecam_session_triage as session_triage
import huniecam_storage_guard as storage_guard

SCHEMA = "MADEIRA_HUNIECAM_PIPELINE_V1"


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
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    pre = probe.probe_install(install)
    guard = config_guard.inspect(config_text, arguments)
    madeira_text = read_text(madeira_log)
    unity_text = read_text(unity_log)
    session = session_triage.analyze(madeira_text, unity_text, pre)
    issues = issue_matcher.match(madeira_text + "\n" + unity_text, pre)
    nxt = next_run.choose(session, issues, ledger)

    paths = {
        "preflight": out_dir / "huniecam-preflight.json",
        "guard": out_dir / "huniecam-guard.json",
        "session": out_dir / "huniecam-session.json",
        "issues": out_dir / "huniecam-issues.json",
        "next": out_dir / "huniecam-next-run.json",
    }
    write_json(paths["preflight"], pre)
    write_json(paths["guard"], guard)
    write_json(paths["session"], session)
    write_json(paths["issues"], issues)
    write_json(paths["next"], nxt)

    storage = None
    if storage_root:
        storage = storage_guard.scan(storage_root)
        write_json(out_dir / "huniecam-storage.json", storage)

    manifest_inputs: dict[str, pathlib.Path | None] = {
        "preflight": paths["preflight"],
        "session": paths["session"],
        "guard": paths["guard"],
        "issues": paths["issues"],
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
        "deepest_stage": session.get("deepest_stage"),
        "deepest_stage_name": session.get("deepest_stage_name"),
        "best_upstream_issue_match": (issues.get("best_match") or {}).get("issue") if isinstance(issues.get("best_match"), dict) else None,
        "next_run_status": nxt.get("status"),
        "next_run_priority": nxt.get("priority"),
        "next_run_profile": nxt.get("profile"),
        "storage_large_jit_dumps": storage.get("large_jit_dump_count") if storage else None,
        "evidence_manifest": manifest_path.name,
        "outputs": [p.name for p in paths.values()] + [manifest_path.name] + (["huniecam-storage.json"] if storage else []),
        "rule": "If guard_status is FAIL, do not run that profile. If next_run_status blocks on runtime evidence, preserve logs instead of adding title switches.",
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
    p.add_argument("--out-dir", type=pathlib.Path, required=True)
    args = p.parse_args()
    ledger = json.loads(args.ledger.read_text(encoding="utf-8")) if args.ledger else None
    summary = run(
        args.install, args.madeira_log, args.unity_log, args.out_dir,
        config_text=read_text(args.config), arguments=args.arguments,
        ledger=ledger, storage_root=args.storage_root,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["guard_status"] != "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
