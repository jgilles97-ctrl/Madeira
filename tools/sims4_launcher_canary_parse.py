#!/usr/bin/env python3
"""Parse `sims4-launcher-canary.exe` output into the next Sims/EA device gate."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from typing import Any

SCHEMA = "SIMS4_LAUNCHER_CANARY_RESULT_V1"
LINE_RE = re.compile(r"^CANARY\s+(\S+)\s+(PASS|FAIL|OBSERVE)\s*(.*)$")
SUMMARY_RE = re.compile(r"^CANARY\s+SUMMARY\s+failures=(\d+)\s*$")

FAILURE_GATES = {
    "x64-process": "FIX_X64_FEX_RUNTIME",
    "child-process": "FIX_PSEUDO_PROCESS_HANDOFF",
    "service-control-manager": "FIX_WINDOWS_SERVICE_CONTROL_MANAGER",
    "ea-background-service": "FIX_EA_BACKGROUND_SERVICE_QUERY",
    "sensapi": "FIX_WINDOWS_NETWORK_STATE_APIS",
    "network-list-manager": "FIX_WINDOWS_NETWORK_STATE_APIS",
    "tcp-1.1.1.1-443": "FIX_IPAD_GUEST_NETWORK_ROUTE",
    "winhttp-https": "FIX_WINHTTP_HTTPS_PATH",
}

# Earlier entries are prerequisites for later entries. If several fail in one
# run, work the earliest prerequisite first.
PRIORITY = (
    "x64-process",
    "child-process",
    "service-control-manager",
    "ea-background-service",
    "sensapi",
    "network-list-manager",
    "tcp-1.1.1.1-443",
    "winhttp-https",
)


def parse(text: str) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    observations: list[dict[str, Any]] = []
    summary_failures: int | None = None

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        summary = SUMMARY_RE.match(line)
        if summary:
            summary_failures = int(summary.group(1))
            continue
        match = LINE_RE.match(line)
        if not match:
            continue
        name, status, detail = match.groups()
        entry = {"line": lineno, "status": status, "detail": detail}
        if status == "OBSERVE":
            observations.append({"name": name, **entry})
        else:
            checks[name] = entry

    failed = [name for name in PRIORITY if checks.get(name, {}).get("status") == "FAIL"]
    missing = [name for name in PRIORITY if name not in checks]
    stopped_observation = next(
        (
            item for item in observations
            if item["name"] == "ea-service-stale-check"
            and re.search(r"state_name=(?:STOPPED|STOP_PENDING)\b", item["detail"], re.I)
        ),
        None,
    )

    if failed:
        next_gate = FAILURE_GATES[failed[0]]
    elif missing:
        next_gate = "REPEAT_LAUNCHER_CANARY_WITH_COMPLETE_OUTPUT"
    elif summary_failures not in (None, 0):
        next_gate = "RECONCILE_CANARY_SUMMARY_WITH_CHECK_LINES"
    elif stopped_observation:
        next_gate = "CAPTURE_AND_INSPECT_EA_BACKGROUNDSERVICE_INI"
    else:
        next_gate = "LAUNCH_EA_APP_IN_WINE_DESKTOP"

    observed_failures = sum(1 for item in checks.values() if item["status"] == "FAIL")
    summary_consistent = summary_failures is None or summary_failures == observed_failures

    return {
        "schema": SCHEMA,
        "checks": checks,
        "observations": observations,
        "failed_checks": failed,
        "missing_checks": missing,
        "summary_failures": summary_failures,
        "observed_failures": observed_failures,
        "summary_consistent": summary_consistent,
        "ea_service_stopped_observed": stopped_observation is not None,
        "next_gate": next_gate,
        "physical_device_success": "UNPROVEN",
        "rule": (
            "Passing this canary proves only small launcher prerequisites. It does not prove EA App, CEF, or The Sims 4 runs."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Parse Sims 4 launcher canary output")
    ap.add_argument("log", type=pathlib.Path)
    ap.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = ap.parse_args()
    report = parse(args.log.read_text(encoding="utf-8", errors="replace"))
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if not report["failed_checks"] and not report["missing_checks"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
