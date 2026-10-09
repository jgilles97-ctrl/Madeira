#!/usr/bin/env python3
"""Build a provenance-locked record for one HunieCam/Madeira device attempt.

A run record joins the owned-build identity, exact launch profile, session depth,
and optional performance summary. It lets later A/B comparisons refuse to
compare different game binaries or silently different baseline settings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_RUN_RECORD_V1"


def load(path: pathlib.Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    if not profile:
        return {}
    source = profile.get("entry_fragment") if isinstance(profile.get("entry_fragment"), dict) else profile
    fps = source.get("fps")
    if fps is None and "fpsMode" in source:
        fps = 60 if source.get("fpsMode") == 1 else source.get("fpsMode")
    return {
        "launch_mode": source.get("launch_mode", source.get("launchMode")),
        "resolution": source.get("resolution"),
        "display": source.get("display"),
        "fps": fps,
        "bits": source.get("bits"),
        "config": str(source.get("config", "")).strip(),
        "arguments": str(source.get("arguments", "")).strip(),
        "relative_executable": source.get("relative_executable", source.get("relativePath")),
    }


def build(
    preflight: dict[str, Any] | None,
    session: dict[str, Any] | None,
    profile: dict[str, Any] | None,
    performance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    identity = (preflight or {}).get("identity", {}) if isinstance((preflight or {}).get("identity"), dict) else {}
    exe_hash = identity.get("exe_sha256")
    build_material = {
        "steam_app_id": (preflight or {}).get("steam_app_id"),
        "exe_sha256": exe_hash,
        "assembly_csharp_sha256": identity.get("assembly_csharp_sha256"),
        "unity_mono_sha256": identity.get("unity_mono_sha256"),
        "root_steam_api_sha256": identity.get("root_steam_api_sha256"),
        "plugin_steam_api_sha256": identity.get("plugin_steam_api_sha256"),
    }
    if not exe_hash:
        errors.append("Owned executable SHA-256 is missing; this run cannot be provenance-locked.")

    normalized_profile = normalize_profile(profile)
    required_profile = ("launch_mode", "resolution", "display", "fps", "config", "arguments")
    missing_profile = [key for key in required_profile if normalized_profile.get(key) is None]
    if missing_profile:
        errors.append("Launch profile is incomplete: " + ", ".join(missing_profile))

    session_preflight = (session or {}).get("preflight") if isinstance((session or {}).get("preflight"), dict) else None
    if session_preflight:
        sess_identity = session_preflight.get("identity", {}) if isinstance(session_preflight.get("identity"), dict) else {}
        session_hash = sess_identity.get("exe_sha256")
        if session_hash and exe_hash and session_hash != exe_hash:
            errors.append("Session report embeds a different executable hash than the supplied preflight.")

    pe = identity.get("pe", {}) if isinstance(identity.get("pe"), dict) else {}
    if normalized_profile.get("bits") is not None and pe.get("is_32bit_x86"):
        if int(normalized_profile["bits"]) != 32:
            errors.append("Owned executable is i386 but the recorded launch profile is not 32-bit.")

    perf = performance or {}
    if perf and not perf.get("comparison_clean", False):
        warnings.append("Performance evidence is not clean/comparable; keep it as diagnostics, not a benchmark result.")

    failures = sorted({str(x.get("code")) for x in (session or {}).get("failures", []) if isinstance(x, dict) and x.get("code")})
    markers = sorted({str(x.get("code")) for x in (session or {}).get("markers", []) if isinstance(x, dict) and x.get("code")})

    build_fingerprint = _sha(build_material) if exe_hash else None
    profile_fingerprint = _sha(normalized_profile) if not missing_profile else None
    comparison_key = _sha({"build": build_fingerprint, "profile": normalized_profile}) if build_fingerprint and profile_fingerprint else None

    return {
        "schema": SCHEMA,
        "title": "HunieCam Studio",
        "steam_app_id": 426000,
        "build": {
            "fingerprint_sha256": build_fingerprint,
            "material": build_material,
        },
        "profile": normalized_profile,
        "profile_sha256": profile_fingerprint,
        "comparison_key_sha256": comparison_key,
        "session": {
            "schema": (session or {}).get("schema"),
            "deepest_stage": int((session or {}).get("deepest_stage", 0)),
            "deepest_stage_name": (session or {}).get("deepest_stage_name"),
            "failure_codes": failures,
            "marker_codes": markers,
        },
        "performance": {
            "schema": perf.get("schema") if perf else None,
            "comparison_clean": perf.get("comparison_clean") if perf else None,
            "fps_median": ((perf.get("fps") or {}).get("median") if isinstance(perf.get("fps"), dict) else None) if perf else None,
        },
        "ready_for_comparison": not errors,
        "errors": errors,
        "warnings": warnings,
        "rule": "Only compare runs when the owned-build fingerprint is identical. Profile changes must be deliberate and visible; different binaries are never an A/B test.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Build one HunieCam Madeira provenance-locked run record")
    p.add_argument("--preflight", type=pathlib.Path, required=True)
    p.add_argument("--session", type=pathlib.Path, required=True)
    p.add_argument("--profile", type=pathlib.Path, required=True)
    p.add_argument("--performance", type=pathlib.Path)
    p.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    report = build(load(args.preflight), load(args.session), load(args.profile), load(args.performance))
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["ready_for_comparison"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
