#!/usr/bin/env python3
"""Summarize performance/thermal evidence from a HunieCam Madeira run.

This parser does not invent an FPS result when the log has no samples. It is
intended to stop performance guesses from turning into compatibility switches.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import statistics
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_PERFORMANCE_V1"
FPS_RE = re.compile(r"(?:\bfps\b|frame-rate|framerate)\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", re.I)
FRAME_MS_RE = re.compile(r"(?:frame(?:time|_ms| ms)|frametime)\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*(?:ms)?", re.I)
DEVICE_RE = re.compile(r"\[device-load\].*?thermal=([a-z]+).*?low-power=([01]).*?capture=([01])", re.I)


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def analyze(text: str) -> dict[str, Any]:
    fps = [float(x) for x in FPS_RE.findall(text)]
    frame_ms = [float(x) for x in FRAME_MS_RE.findall(text)]
    devices = DEVICE_RE.findall(text)
    thermals = [t.lower() for t, _, _ in devices]
    low_power_seen = any(lp == "1" for _, lp, _ in devices)
    capture_seen = any(cap == "1" for _, _, cap in devices)

    fps_median = statistics.median(fps) if fps else None
    fps_p05 = percentile(fps, 0.05)
    fps_p95 = percentile(fps, 0.95)
    frame_median = statistics.median(frame_ms) if frame_ms else None
    thermal_bad = any(t in {"serious", "critical"} for t in thermals)
    runaway = bool(fps and max(fps) > 125)

    warnings: list[str] = []
    if not fps and not frame_ms:
        warnings.append("No FPS or frame-time samples were found; performance remains unproven.")
    if thermal_bad:
        warnings.append("Serious/critical thermal pressure occurred; do not compare this run directly with a cool baseline.")
    if low_power_seen:
        warnings.append("Low Power Mode appeared in the run and can distort performance comparisons.")
    if capture_seen:
        warnings.append("Screen capture/recording was active for at least one device-load sample and may add overhead.")
    if runaway:
        warnings.append("FPS exceeded 125; for this old Unity title verify game timing instead of treating the higher number as automatically better.")

    comparable = bool((fps or frame_ms) and not thermal_bad and not low_power_seen)
    return {
        "schema": SCHEMA,
        "fps": {
            "samples": len(fps),
            "median": fps_median,
            "p05": fps_p05,
            "p95": fps_p95,
            "min": min(fps) if fps else None,
            "max": max(fps) if fps else None,
        },
        "frame_ms": {
            "samples": len(frame_ms),
            "median": frame_median,
            "p95": percentile(frame_ms, 0.95),
        },
        "device": {
            "samples": len(devices),
            "thermal_states": sorted(set(thermals)),
            "low_power_seen": low_power_seen,
            "screen_capture_seen": capture_seen,
        },
        "runaway_fps_signal": runaway,
        "comparison_clean": comparable,
        "warnings": warnings,
        "rule": "Only compare performance between runs with actual samples and without serious thermal pressure or Low Power Mode. Compatibility success is not inferred from FPS alone.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize HunieCam Madeira performance evidence")
    parser.add_argument("log", type=pathlib.Path)
    parser.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = parser.parse_args()
    report = analyze(args.log.read_text(encoding="utf-8", errors="replace"))
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
