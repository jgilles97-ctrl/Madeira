#!/usr/bin/env python3
"""Combine Madeira + Unity logs into a HunieCam-specific next-action report.

Read-only. The goal is to turn one real iPad run into the smallest useful next
experiment instead of accumulating speculative compatibility switches.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
from dataclasses import dataclass

SCHEMA = "MADEIRA_HUNIECAM_SESSION_V1"


@dataclass(frozen=True)
class Marker:
    code: str
    pattern: re.Pattern[str]
    stage: int
    meaning: str


MADEIRA_MARKERS = (
    Marker("target_started", re.compile(r"\[WineProc\]\s+Target exe:.*HunieCamStudio\.exe", re.I), 20,
           "Madeira handed the HunieCam executable to Wine."),
    Marker("wow_window", re.compile(r"\[wow-window\].*(?:adopt|reserved|window|B=)", re.I), 25,
           "A 32-bit WoW64 guest window was involved."),
    Marker("d3d9_loaded", re.compile(r"(?:d3d9(?:-emulated|shim)?\.dll|\bd3d9\b.*(?:load|unix|dxmt))", re.I), 45,
           "The Direct3D 9 path appears in the Madeira log."),
    Marker("presenting", re.compile(r"(?:Game is presenting|\[present\]|presented frame)", re.I), 60,
           "The runtime reached a presenting/rendering state."),
)

UNITY_MARKERS = (
    Marker("unity_engine", re.compile(r"Initialize engine version:\s*([0-9.]+[a-z][0-9]+)", re.I), 30,
           "Unity itself initialized."),
    Marker("gfx_device", re.compile(r"GfxDevice:\s*creating device client", re.I), 40,
           "Unity started graphics-device setup."),
    Marker("d3d9", re.compile(r"Version:\s*Direct3D\s+9", re.I), 50,
           "Unity selected Direct3D 9."),
    Marker("d3d11", re.compile(r"Version:\s*Direct3D\s+11", re.I), 50,
           "Unity selected Direct3D 11 instead of the expected D3D9 baseline."),
    Marker("mono_reload", re.compile(r"Begin MonoManager ReloadAssembly", re.I), 55,
           "Unity entered managed-code/Mono assembly loading."),
    Marker("game_assembly", re.compile(r"(?:Loading|Platform assembly:).*Assembly-CSharp\.dll", re.I), 65,
           "The game's main managed assembly was loaded."),
    Marker("input_init", re.compile(r"Input.*Initialized|Initialize input|Using input", re.I), 70,
           "Unity reported input initialization."),
    Marker("first_scene", re.compile(r"UnloadTime:|Unloading .* unused Assets|Loaded scene", re.I), 75,
           "Unity progressed beyond early engine/assembly startup into scene/asset work."),
)

FATALS = (
    ("jit_missing", re.compile(r"\[jit-debugger\]\s*attached=0\s+at the pool request", re.I)),
    ("wow_map_refused", re.compile(r"\[wow-window\].*refused.*map too small", re.I)),
    ("store_undecoded", re.compile(r"\[store-undecoded\]", re.I)),
    ("missing_dll", re.compile(r"(?:err:module:import_dll|library .{1,100}\.dll.{0,40}(?:not found|missing))", re.I)),
    ("access_violation", re.compile(r"(?:0x)?c0000005", re.I)),
    ("no_memory", re.compile(r"(?:0x)?c0000017", re.I)),
    ("steam_platform", re.compile(r"(?:launch refusal\s*29|invalid platform)", re.I)),
)

UNITY_FATALS = (
    ("unity_crash", re.compile(r"(?:Crash!!!|Receiving unhandled NULL exception|access violation|fatal error)", re.I)),
    ("steam_init_failed", re.compile(r"SteamAPI[_ ]Init.*(?:fail|false)|Steamworks.*(?:fail|not initialized)", re.I)),
)


def read_text(path: pathlib.Path | None) -> str:
    if path is None:
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def collect_markers(text: str, markers: tuple[Marker, ...], source: str) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    lines = text.splitlines()
    for marker in markers:
        hits = []
        for n, line in enumerate(lines, 1):
            m = marker.pattern.search(line)
            if m:
                hits.append({"line": n, "text": line[:500]})
                if len(hits) >= 3:
                    break
        if hits:
            out.append({
                "code": marker.code,
                "source": source,
                "stage": marker.stage,
                "meaning": marker.meaning,
                "samples": hits,
            })
    return out


def collect_fatals(text: str, rules: tuple[tuple[str, re.Pattern[str]], ...], source: str) -> list[dict[str, object]]:
    out = []
    lines = text.splitlines()
    for code, pattern in rules:
        samples = []
        count = 0
        for n, line in enumerate(lines, 1):
            if pattern.search(line):
                count += 1
                if len(samples) < 3:
                    samples.append({"line": n, "text": line[:500]})
        if count:
            out.append({"code": code, "source": source, "count": count, "samples": samples})
    return out


def stage_name(value: int) -> str:
    if value >= 75: return "Unity reached scene/asset work"
    if value >= 65: return "game managed assembly loaded"
    if value >= 55: return "Unity Mono/managed startup"
    if value >= 50: return "graphics API selected"
    if value >= 40: return "graphics setup"
    if value >= 30: return "Unity initialized"
    if value >= 20: return "Windows executable started"
    return "no proven game start"


def choose_next(markers: list[dict[str, object]], fatals: list[dict[str, object]], madeira: str, unity: str) -> dict[str, object]:
    fatal_codes = {str(f["code"]) for f in fatals}
    marker_codes = {str(m["code"]) for m in markers}
    all_text = madeira + "\n" + unity

    baseline = {
        "name": "clean baseline",
        "config": "",
        "arguments": "",
        "reason": "Start from current Madeira defaults. HunieCam's Unity-era Windows player normally uses D3D9; extra switches hide root causes.",
    }

    if "jit_missing" in fatal_codes:
        return {"priority": "runtime prerequisite", "action": "Fix JIT/Memory+ and rerun unchanged.", "experiment": baseline}
    if "wow_map_refused" in fatal_codes:
        return {"priority": "WoW64 address space", "action": "Capture the full address-map/JIT-pool section and fix virtual-address headroom before touching game settings.", "experiment": baseline}
    if "missing_dll" in fatal_codes:
        return {"priority": "Windows dependency", "action": "Identify the first missing DLL and satisfy only that legitimate prerequisite; do not add graphics/memory switches yet.", "experiment": baseline}

    # Unity's own Mono is not auto-detected by Madeira's Wine-Mono-specific
    # ml1282 path. This is an A/B only when the evidence points at JIT-backed
    # guest writes; it is never the title default.
    store_cost = len(re.findall(r"(?:\[store-undecoded\]|emulated-store|\[fault-cost\].*store)", all_text, re.I))
    mono_seen = bool(re.search(r"(?:HunieCamStudio_Data[/\\]Mono[/\\]mono\.dll|\bmono\.dll\b|MonoManager)", all_text, re.I))
    if "store_undecoded" in fatal_codes or (mono_seen and store_cost >= 10):
        return {
            "priority": "Unity Mono protected-memory writes",
            "action": "Preserve the baseline log, then run one controlled WoW64 RWX A/B test.",
            "experiment": {
                "name": "Unity Mono RWX plain-memory A/B",
                "config": "env.MADEIRA_WOW_RWX_PLAIN = 1",
                "arguments": "",
                "rollback": "Remove the line after the A/B run.",
                "reason": "Current Madeira auto-enables this optimization for Wine Mono, but its docs say Unity's bundled Mono is not auto-matched. In a 32-bit guest window FEX executes translated code, so this switch can eliminate host-side store emulation for guest RWX pages. Evidence is required before keeping it.",
            },
        }

    if "d3d11" in marker_codes and "d3d9" not in marker_codes:
        return {
            "priority": "graphics API selection",
            "action": "Force the old Unity player back to Direct3D 9, then compare the Unity log.",
            "experiment": {
                "name": "force Unity D3D9",
                "config": "",
                "arguments": "-force-d3d9",
                "rollback": "Remove -force-d3d9 after the comparison if it changes nothing.",
                "reason": "Unity 5-era Windows players support -force-d3d9; HunieCam is expected to use D3D9 and Madeira has a dedicated i386 D3D9 path.",
            },
        }

    graphics_reached = bool({"d3d9", "d3d9_loaded", "gfx_device"} & marker_codes)
    if graphics_reached and ("access_violation" in fatal_codes or "unity_crash" in fatal_codes):
        return {
            "priority": "D3D9 implementation A/B",
            "action": "Keep everything else identical and compare Madeira's native D3D9 frontend once.",
            "experiment": {
                "name": "native D3D9 frontend A/B",
                "config": "d3d9 = native",
                "arguments": "",
                "rollback": "Remove `d3d9 = native` if it does not move the failure deeper or fix rendering.",
                "reason": "Madeira provides separate translated and native D3D9 frontends. This is useful only after CPU/Unity startup reaches graphics.",
            },
        }

    if "steam_init_failed" in fatal_codes:
        return {
            "priority": "Steam integration",
            "action": "Compare legitimate Madeira Dock launch with the direct-game run; keep runtime/graphics settings identical.",
            "experiment": {"name": "Dock versus direct launch", "config": "", "arguments": "", "reason": "Separate Steamworks initialization from game/runtime compatibility."},
        }

    if "game_assembly" in marker_codes or "first_scene" in marker_codes:
        return {
            "priority": "device acceptance",
            "action": "Stop changing compatibility switches. Test real gameplay, pointer alignment, audio, save/relaunch, 30-minute stability, three cold launches, and suspend/resume.",
            "experiment": baseline,
        }

    return {
        "priority": "more evidence",
        "action": "Rerun the clean baseline and collect both madeira-log.txt and HunieCamStudio_Data/output_log.txt if Unity created it.",
        "experiment": baseline,
    }


def analyze(madeira_text: str, unity_text: str, preflight: dict[str, object] | None = None) -> dict[str, object]:
    markers = collect_markers(madeira_text, MADEIRA_MARKERS, "madeira") + collect_markers(unity_text, UNITY_MARKERS, "unity")
    fatals = collect_fatals(madeira_text, FATALS, "madeira") + collect_fatals(unity_text, UNITY_FATALS, "unity")
    stage = max([int(m["stage"]) for m in markers] or [0])
    result = {
        "schema": SCHEMA,
        "deepest_stage": stage,
        "deepest_stage_name": stage_name(stage),
        "markers": sorted(markers, key=lambda x: (int(x["stage"]), str(x["code"]))),
        "failures": fatals,
        "next": choose_next(markers, fatals, madeira_text, unity_text),
        "evidence": {
            "madeira_log_present": bool(madeira_text.strip()),
            "unity_log_present": bool(unity_text.strip()),
            "preflight_present": preflight is not None,
        },
    }
    if preflight is not None:
        result["preflight"] = {
            "schema": preflight.get("schema"),
            "exe_found": preflight.get("exe_found"),
            "identity": preflight.get("identity"),
            "runtime_signals": preflight.get("runtime_signals"),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="HunieCam Studio Madeira + Unity session diagnosis")
    parser.add_argument("--madeira-log", type=pathlib.Path, required=True)
    parser.add_argument("--unity-log", type=pathlib.Path)
    parser.add_argument("--preflight", type=pathlib.Path)
    parser.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = parser.parse_args()

    preflight = json.loads(read_text(args.preflight)) if args.preflight else None
    report = analyze(read_text(args.madeira_log), read_text(args.unity_log), preflight)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
