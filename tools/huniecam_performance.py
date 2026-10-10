#!/usr/bin/env python3
"""Summarize performance/thermal evidence from a HunieCam Madeira run.

HunieCam itself is publicly documented as uncapped, so Cycle 5 also verifies
that Madeira's intended frame cap is actually visible in the measurements. A
performance run is not treated as clean when the requested cap appears absent.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import statistics
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_PERFORMANCE_V2"
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


def analyze(text: str, expected_fps: int | None = 60) -> dict[str, Any]:
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

    cap_verifiable = bool(expected_fps and len(fps) >= 3)
    cap_effective: bool | None = None
    if cap_verifiable and fps_median is not None and fps_p95 is not None and expected_fps:
        # A little headroom avoids rejecting ordinary counter jitter, while a
        # sustained 90/120/144 Hz run cannot pass as a 60 FPS baseline.
        cap_effective = fps_median <= expected_fps * 1.10 and fps_p95 <= expected_fps * 1.20

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
    if expected_fps is not None and not cap_verifiable:
        warnings.append(f"Not enough FPS samples exist to prove the intended {expected_fps} FPS Madeira cap was active.")
    if cap_effective is False:
        warnings.append(f"Measured FPS is inconsistent with the intended {expected_fps} FPS cap. Verify the Madeira profile before benchmarking or timing-sensitive acceptance.")

    comparable = bool((fps or frame_ms) and not thermal_bad and not low_power_seen)
    if expected_fps is not None:
        comparable = comparable and cap_effective is True

    low_perf = bool(expected_fps and fps_median is not None and fps_median < expected_fps * 0.50)
    if low_perf and not thermal_bad and not low_power_seen:
        warnings.append("Median FPS is below half the requested cap under the observed device state; keep this as a performance problem after compatibility is proven.")

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
        "fps_cap": {
            "expected": expected_fps,
            "verifiable": cap_verifiable,
            "effective": cap_effective,
            "public_title_behavior": "HunieCam Studio is publicly documented as having no native FPS cap; the requested limit is therefore a Madeira/profile control.",
        },
        "runaway_fps_signal": runaway,
        "low_performance_signal": low_perf,
        "comparison_clean": comparable,
        "warnings": warnings,
        "rule": "Only compare performance between runs with actual samples, the intended Madeira FPS cap proven active, and no serious thermal pressure or Low Power Mode. Compatibility success is not inferred from FPS alone.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize HunieCam Madeira performance evidence")
    parser.add_argument("log", type=pathlib.Path)
    parser.add_argument("--expected-fps", type=int, default=60, help="Madeira cap intended for this run; use 0 only for an intentional uncapped diagnostic")
    parser.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = parser.parse_args()
    expected = None if args.expected_fps == 0 else args.expected_fps
    report = analyze(args.log.read_text(encoding="utf-8", errors="replace"), expected)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
