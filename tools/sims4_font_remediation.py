#!/usr/bin/env python3
"""Plan an evidence-gated Wine font remediation for EA Desktop CEF.

This tool is intentionally non-mutating. It consumes a parsed Sims launcher
canary result and emits a deterministic registry plan only when the device
canary proves Arial cannot be resolved. It never assumes the July 2026 EA/Wine
Arial bug is present merely because EA CEF crashed.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

SCHEMA = "SIMS4_FONT_REMEDIATION_PLAN_V1"
CANARY_SCHEMA = "SIMS4_LAUNCHER_CANARY_RESULT_V1"


def make_plan(canary: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if canary.get("schema") != CANARY_SCHEMA:
        blockers.append("CANARY_SCHEMA_MISMATCH")

    dwrite = canary.get("dwrite_arial_resolution") or {}
    check = (canary.get("checks") or {}).get("dwrite-arial") or {}
    status = check.get("status")
    arial_found = bool(dwrite.get("arial_found"))
    liberation_found = bool(dwrite.get("liberation_sans_found"))
    tahoma_found = bool(dwrite.get("tahoma_found"))

    if status is None:
        blockers.append("DWRITE_ARIAL_PROBE_MISSING")
    elif status == "PASS" or arial_found:
        blockers.append("ARIAL_ALREADY_RESOLVES")
    elif status != "FAIL":
        blockers.append("DWRITE_ARIAL_PROBE_INDETERMINATE")

    replacement: str | None = None
    if not blockers:
        if liberation_found:
            replacement = "Liberation Sans"
        elif tahoma_found:
            # Tahoma is not an Arial metric-compatible first choice. Keep this
            # as observation only rather than silently substituting it.
            blockers.append("NO_VALIDATED_ARIAL_REPLACEMENT_FOUND")
        else:
            blockers.append("NO_VALIDATED_ARIAL_REPLACEMENT_FOUND")

    approved = not blockers and replacement is not None
    registry = None
    if approved:
        registry = {
            "key": r"HKEY_CURRENT_USER\Software\Wine\Fonts\Replacements",
            "value_name": "Arial",
            "value_type": "REG_SZ",
            "value_data": replacement,
            "reg_command": (
                r'reg add "HKCU\Software\Wine\Fonts\Replacements" '
                rf'/v Arial /t REG_SZ /d "{replacement}" /f'
            ),
            "rollback_command": (
                r'reg delete "HKCU\Software\Wine\Fonts\Replacements" '
                r'/v Arial /f'
            ),
        }

    return {
        "schema": SCHEMA,
        "source_canary_schema": canary.get("schema"),
        "approved": approved,
        "blockers": blockers,
        "evidence": {
            "dwrite_status": status,
            "arial_found": arial_found,
            "liberation_sans_found": liberation_found,
            "tahoma_found": tahoma_found,
            "source_detail": check.get("detail"),
        },
        "replacement_family": replacement,
        "registry_plan": registry,
        "verification": [
            "Apply only to the exact Wine prefix used by the failed device canary.",
            "Re-run the identical launcher canary before launching EA App.",
            "Require dwrite-arial PASS with arial=1 after the change.",
            "If the probe still fails, rollback before trying a different font approach.",
        ],
        "physical_device_success": "UNPROVEN",
        "rule": (
            "This tool never edits a prefix. A font alias is proposed only from device evidence that Arial is missing and a validated replacement family is present."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Create an evidence-gated EA CEF Arial remediation plan")
    ap.add_argument("canary_json", type=pathlib.Path)
    ap.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = ap.parse_args()
    canary = json.loads(args.canary_json.read_text(encoding="utf-8"))
    plan = make_plan(canary)
    text = json.dumps(plan, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if plan["approved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
