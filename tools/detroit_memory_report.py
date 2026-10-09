#!/usr/bin/env python3
"""Summarize Detroit's opt-in iPad memory telemetry around shader progress.

Consumes madeira-log.txt only. It never changes the log, game, shader cache, or
configuration. The report keeps raw measurements instead of inventing a single
"safe" threshold because iPadOS memory limits can change during a session.
"""

from __future__ import annotations

import argparse
import pathlib
import re
from dataclasses import dataclass

MEMORY_RE = re.compile(
    r"\[device-memory\].*?available-mib=(?P<available>[0-9.]+)"
    r"(?:.*?footprint-mib=(?P<footprint>[0-9.]+))?"
    r"(?:.*?peak-mib=(?P<peak>[0-9.]+))?",
    re.I,
)
SHADER_RE = re.compile(r"(?:compil(?:e|ing)\s+shaders?|shaders?.*?compil).*?(?P<pct>\d{1,3})\s*%", re.I)
PRESSURE_RE = re.compile(
    r"(?:jetsam|memorystatus|out of memory|STATUS_NO_MEMORY|c0000017|"
    r"VK_ERROR_OUT_OF_(?:DEVICE|HOST)_MEMORY|kIOGPUCommandBufferCallbackErrorOutOfMemory)",
    re.I,
)


@dataclass(frozen=True)
class Sample:
    line: int
    available_mib: float
    footprint_mib: float | None
    peak_mib: float | None


def parse(text: str) -> tuple[list[Sample], list[tuple[int, int]], list[int]]:
    samples: list[Sample] = []
    progress: list[tuple[int, int]] = []
    pressure: list[int] = []
    for number, raw in enumerate(text.splitlines(), 1):
        m = MEMORY_RE.search(raw)
        if m:
            samples.append(
                Sample(
                    line=number,
                    available_mib=float(m.group("available")),
                    footprint_mib=float(m.group("footprint")) if m.group("footprint") else None,
                    peak_mib=float(m.group("peak")) if m.group("peak") else None,
                )
            )
        s = SHADER_RE.search(raw)
        if s:
            pct = max(0, min(100, int(s.group("pct"))))
            progress.append((number, pct))
        if PRESSURE_RE.search(raw):
            pressure.append(number)
    return samples, progress, pressure


def at_or_before(samples: list[Sample], line: int) -> Sample | None:
    found = None
    for sample in samples:
        if sample.line > line:
            break
        found = sample
    return found


def shader_progress_at_or_before(progress: list[tuple[int, int]], line: int) -> int | None:
    values = [pct for progress_line, pct in progress if progress_line <= line]
    return max(values) if values else None


def render(text: str) -> str:
    samples, progress, pressure = parse(text)
    out = ["# Detroit shader-memory report", ""]
    if not samples:
        out += [
            "No `[device-memory]` samples were found.",
            "Use Detroit's `docs/detroit-m4-8gb.cfg` profile and rerun so MADEIRA_DEVICE_STATS=1 is active.",
        ]
        if pressure:
            out.append(f"Memory-pressure signatures were still found on line(s): {', '.join(map(str, pressure[:10]))}")
        return "\n".join(out)

    first, last = samples[0], samples[-1]
    minimum = min(samples, key=lambda x: x.available_mib)
    footprints = [s.footprint_mib for s in samples if s.footprint_mib is not None]
    peaks = [s.peak_mib for s in samples if s.peak_mib is not None]

    out.append(f"Samples: {len(samples)}")
    out.append(f"Available memory: first {first.available_mib:.1f} MiB; last {last.available_mib:.1f} MiB; minimum {minimum.available_mib:.1f} MiB (line {minimum.line})")
    out.append(f"Headroom change: {last.available_mib - first.available_mib:+.1f} MiB")
    if footprints:
        out.append(f"Largest measured footprint: {max(footprints):.1f} MiB")
    if peaks:
        out.append(f"Largest lifetime-peak footprint reported: {max(peaks):.1f} MiB")
    out.append(f"Memory-pressure signatures: {len(pressure)}")

    if progress:
        out += ["", "Shader checkpoints:"]
        seen: set[int] = set()
        wanted = [50, 90, 95, 98, 99, 100]
        for target in wanted:
            candidates = [(line, pct) for line, pct in progress if pct >= target]
            if not candidates:
                continue
            line, pct = candidates[0]
            if pct in seen:
                continue
            seen.add(pct)
            sample = at_or_before(samples, line)
            if sample:
                out.append(
                    f"- first >= {target}%: game reported {pct}% at line {line}; latest memory sample had {sample.available_mib:.1f} MiB available"
                    + (f", {sample.footprint_mib:.1f} MiB footprint" if sample.footprint_mib is not None else "")
                )
            else:
                out.append(f"- first >= {target}%: game reported {pct}% at line {line}; no earlier memory sample")
        max_line, max_pct = max(progress, key=lambda item: item[1])
        out.append(f"Highest shader progress seen: {max_pct}% (line {max_line})")
    else:
        out += ["", "No shader-compilation percentage was found in this log."]

    out += ["", "Interpretation:"]
    if pressure:
        first_pressure = pressure[0]
        pressure_progress = shader_progress_at_or_before(progress, first_pressure)
        out.append("BLOCKED: the log contains an explicit memory-pressure/out-of-memory signature. Preserve this log and compare the headroom immediately before it.")
        if pressure_progress is not None and pressure_progress >= 98:
            out.append(
                "Late shader-cache pattern: memory pressure appeared after shader progress had reached at least 98%. "
                "That matches the known Detroit late pipeline-cache/save danger zone. Keep shader compression enabled, "
                "keep the MSL library cache disabled for the 8 GB baseline, and compare the last memory samples before the failure."
            )
    else:
        out.append("No explicit memory-pressure signature was found. Treat the measured headroom trend as evidence, not as a fixed universal safety limit.")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("log", type=pathlib.Path)
    ap.add_argument("--output", type=pathlib.Path)
    args = ap.parse_args()
    text = args.log.read_text(encoding="utf-8", errors="replace")
    report = render(text)
    if args.output:
        args.output.write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
