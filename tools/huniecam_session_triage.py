#!/usr/bin/env python3
"""Combine Madeira + Unity logs into a HunieCam-specific next-action report.

Read-only. The goal is to turn one real iPad run into the smallest defensible
next experiment instead of accumulating speculative compatibility switches.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
from dataclasses import dataclass

SCHEMA = "MADEIRA_HUNIECAM_SESSION_V3"


@dataclass(frozen=True)
class Marker:
    code: str
    pattern: re.Pattern[str]
    stage: int
    meaning: str


MADEIRA_MARKERS = (
    Marker("target_started", re.compile(r"\[WineProc\]\s+Target exe:.*HunieCamStudio\.exe", re.I), 20, "Madeira handed HunieCamStudio.exe to Wine."),
    Marker("wow_window", re.compile(r"\[wow-window\].*(?:adopt|reserved|window|B=)", re.I), 25, "A 32-bit WoW64 guest window was involved."),
    Marker("d3d9_loaded", re.compile(r"(?:d3d9(?:-emulated|shim)?\.dll|\bd3d9\b.*(?:load|unix|dxmt))", re.I), 45, "Madeira's D3D9 path appeared."),
    Marker("presenting", re.compile(r"(?:Game is presenting|\[present\]|presented frame)", re.I), 60, "The runtime reached a presenting state."),
    Marker("hardware_pointer", re.compile(r"\[hwinput\].*(?:mouse|pointer|focus|absolute|GCMouse)", re.I), 62, "Madeira's hardware pointer path was active."),
    Marker("windows_cursor", re.compile(r"\[winios\].*cursor set", re.I), 63, "The Windows cursor bridge published a cursor."),
    Marker("wow_rwx_plain", re.compile(r"\[wow-rwx\].*(?:plain read/write|RWX memory is plain)", re.I), 64, "WoW64 plain-RWX was actually active."),
)

UNITY_MARKERS = (
    Marker("unity_engine", re.compile(r"Initialize engine version:\s*([0-9.]+[a-z][0-9]+)", re.I), 30, "Unity initialized."),
    Marker("gfx_device", re.compile(r"GfxDevice:\s*creating device client", re.I), 40, "Unity began graphics setup."),
    Marker("d3d9", re.compile(r"Version:\s*Direct3D\s+9", re.I), 50, "Unity selected Direct3D 9."),
    Marker("d3d11", re.compile(r"Version:\s*Direct3D\s+11", re.I), 50, "Unity selected Direct3D 11."),
    Marker("mono_reload", re.compile(r"Begin MonoManager ReloadAssembly", re.I), 55, "Unity entered Mono managed-code startup."),
    Marker("game_assembly", re.compile(r"(?:Loading|Platform assembly:).*Assembly-CSharp\.dll", re.I), 65, "The game's main managed assembly loaded."),
    Marker("input_init", re.compile(r"Input.*Initialized|Initialize input|Using input", re.I), 70, "Unity reported input initialization."),
    Marker("audio_init", re.compile(r"(?:FMOD.*(?:initialized|driver)|AudioManager.*(?:initialized|created)|audio.*initialized)", re.I), 71, "Unity reported audio initialization."),
    Marker("first_scene", re.compile(r"UnloadTime:|Unloading .* unused Assets|Loaded scene", re.I), 75, "Unity reached scene/asset work."),
)

FATALS = (
    ("jit_missing", re.compile(r"\[jit-debugger\]\s*attached=0\s+at the pool request", re.I)),
    ("wow_map_refused", re.compile(r"\[wow-window\].*refused.*map too small", re.I)),
    ("store_undecoded", re.compile(r"\[store-undecoded\]", re.I)),
    ("guest_breakpoint_misclassified", re.compile(r"\[store-undecoded\].*insn=0xd4200000", re.I)),
    ("writecopy_image_fault", re.compile(r"\[wr-strip-declined\].*SEC_IMAGE\s+WRITECOPY", re.I)),
    ("redelivery_storm", re.compile(r"\[redeliv\].*(?:storm|identical redeliver|terminat)", re.I)),
    ("missing_dll", re.compile(r"(?:err:module:import_dll|library .{1,100}\.dll.{0,40}(?:not found|missing))", re.I)),
    ("access_violation", re.compile(r"(?:0x)?c0000005", re.I)),
    ("no_memory", re.compile(r"(?:0x)?c0000017", re.I)),
    ("steam_platform", re.compile(r"(?:launch refusal\s*29|invalid platform)", re.I)),
    ("mono_suspend_abort", re.compile(r"Cannot transition thread.*STATE_BLOCKING.*DO_BLOCKING", re.I)),
)

UNITY_FATALS = (
    ("unity_crash", re.compile(r"(?:Crash!!!|Receiving unhandled NULL exception|access violation|fatal error)", re.I)),
    ("steam_init_failed", re.compile(r"SteamAPI[_ ]Init.*(?:fail|false)|Steamworks.*(?:fail|not initialized)", re.I)),
    ("graphics_init_failed", re.compile(r"(?:Failed to initialize graphics|Failed creating D3D|GfxDevice.*fail)", re.I)),
)


def read_text(path: pathlib.Path | None) -> str:
    return "" if path is None else path.read_text(encoding="utf-8", errors="replace")


def collect_markers(text: str, markers: tuple[Marker, ...], source: str) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    lines = text.splitlines()
    for marker in markers:
        hits = []
        for n, line in enumerate(lines, 1):
            if marker.pattern.search(line):
                hits.append({"line": n, "text": line[:500]})
                if len(hits) >= 3:
                    break
        if hits:
            out.append({"code": marker.code, "source": source, "stage": marker.stage, "meaning": marker.meaning, "samples": hits})
    return out


def collect_fatals(text: str, rules: tuple[tuple[str, re.Pattern[str]], ...], source: str) -> list[dict[str, object]]:
    out = []
    lines = text.splitlines()
    for code, pattern in rules:
        samples, count = [], 0
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
    if value >= 71: return "Unity audio/input startup"
    if value >= 65: return "game managed assembly loaded"
    if value >= 55: return "Unity Mono/managed startup"
    if value >= 50: return "graphics API selected"
    if value >= 40: return "graphics setup"
    if value >= 30: return "Unity initialized"
    if value >= 20: return "Windows executable started"
    return "no proven game start"


def baseline() -> dict[str, object]:
    return {
        "name": "clean baseline",
        "config": "",
        "arguments": "",
        "reason": "Use current Madeira defaults and no renderer override until the log proves a reason to change one variable.",
    }


def choose_next(markers: list[dict[str, object]], fatals: list[dict[str, object]], madeira: str, unity: str) -> dict[str, object]:
    fatal = {str(f["code"]) for f in fatals}
    seen = {str(m["code"]) for m in markers}
    clean = baseline()
    all_text = madeira + "\n" + unity

    if "jit_missing" in fatal:
        return {"priority": "runtime prerequisite", "action": "Fix JIT/Memory+ and rerun unchanged.", "experiment": clean}
    if "wow_map_refused" in fatal:
        return {"priority": "WoW64 address space", "action": "Fix virtual-address headroom before touching game settings.", "experiment": clean}
    if "missing_dll" in fatal:
        return {"priority": "Windows dependency", "action": "Identify the first missing DLL and satisfy only that legitimate prerequisite.", "experiment": clean}

    # #173 proves [store-undecoded] can describe a guest INT3/BRK rather than a
    # store. Never send that signature down the Mono-RWX experiment lane.
    if "guest_breakpoint_misclassified" in fatal:
        action = "Preserve the breakpoint/store-undecoded line and nearby mach-exception evidence; this is a Madeira WoW64 exception-delivery/runtime bug, not a Mono tuning result."
        if "writecopy_image_fault" in fatal:
            action += " SEC_IMAGE WRITECOPY evidence also matches upstream issue #173."
        return {"priority": "WoW64 breakpoint / self-modifying image runtime bug", "action": action, "experiment": clean, "upstream_reference": "willfaust/Madeira#173"}

    if "mono_suspend_abort" in fatal:
        return {"priority": "remove incompatible Mono suspend override", "action": "Remove mono-suspend=hybrid and rerun the clean profile.", "experiment": clean, "upstream_reference": "willfaust/Madeira#123"}

    mono_seen = bool(re.search(r"(?:HunieCamStudio_Data[/\\]Mono[/\\]mono\.dll|\bmono\.dll\b|MonoManager)", all_text, re.I))
    store_cost = len(re.findall(r"(?:\[store-undecoded\]|emulated-store|\[fault-cost\].*store)", all_text, re.I))
    if ("store_undecoded" in fatal and mono_seen) or (mono_seen and store_cost >= 10):
        return {
            "priority": "Unity Mono protected-memory writes",
            "action": "Preserve baseline evidence, then run one WoW64 RWX A/B test.",
            "experiment": {
                "name": "Unity Mono RWX plain-memory A/B",
                "config": "env.MADEIRA_WOW_RWX_PLAIN = 1",
                "arguments": "",
                "rollback": "Remove the line after the A/B run.",
                "reason": "Madeira auto-matches Wine Mono, not Unity's bundled Mono. Keep this only if a one-variable comparison proves a benefit.",
            },
            "upstream_reference": "willfaust/Madeira#123",
        }
    if "store_undecoded" in fatal and not mono_seen:
        return {"priority": "unclassified Madeira store/runtime blocker", "action": "Capture the first store-undecoded instruction/module context. Do not apply the Unity-Mono RWX switch without Mono evidence.", "experiment": clean}

    # Renderer choice by itself is not a failure. Unity 5.x players can be built
    # with different graphics APIs. Only force D3D9 if D3D11 is tied to an actual
    # graphics failure/crash, or graphics initialization fails before any API is
    # proven.
    graphics_failure = bool({"graphics_init_failed", "unity_crash", "access_violation"} & fatal)
    if "d3d11" in seen and "d3d9" not in seen and graphics_failure:
        return {
            "priority": "renderer A/B after D3D11 failure",
            "action": "Keep everything else unchanged and test -force-d3d9 once.",
            "experiment": {"name": "force Unity D3D9 after D3D11 failure", "config": "", "arguments": "-force-d3d9", "rollback": "Remove -force-d3d9 if startup does not move deeper.", "reason": "The renderer override is justified only because the selected D3D11 path is accompanied by a failure."},
        }
    if "graphics_init_failed" in fatal and not ({"d3d9", "d3d11"} & seen):
        return {
            "priority": "graphics API selection",
            "action": "Run one -force-d3d9 comparison before changing Madeira's D3D9 implementation.",
            "experiment": {"name": "force Unity D3D9 after graphics-init failure", "config": "", "arguments": "-force-d3d9", "rollback": "Remove -force-d3d9 if it does not move startup farther.", "reason": "No renderer was proven before graphics initialization failed."},
        }

    if "d3d9" in seen and graphics_failure:
        return {
            "priority": "D3D9 implementation A/B",
            "action": "Keep everything else identical and compare Madeira's native D3D9 frontend once.",
            "experiment": {"name": "native D3D9 frontend A/B", "config": "d3d9 = native", "arguments": "", "rollback": "Remove `d3d9 = native` unless it moves the failure deeper or fixes rendering.", "reason": "D3D9 was actually selected and the run then failed."},
        }

    if "steam_init_failed" in fatal:
        return {"priority": "Steam integration", "action": "Compare legitimate Madeira Dock launch with direct launch while keeping runtime/graphics settings identical.", "experiment": {"name": "Dock versus direct launch", "config": "", "arguments": "", "reason": "Separate Steamworks startup from game/runtime compatibility."}}

    if "game_assembly" in seen or "first_scene" in seen:
        return {"priority": "device acceptance", "action": "Stop changing compatibility switches. Test real gameplay, pointer grid, audio, save/relaunch, measured performance, 30-minute stability, three cold launches and two suspend/resume cycles.", "experiment": clean}

    if "d3d11" in seen and not graphics_failure:
        return {"priority": "continue clean D3D11 baseline", "action": "Do not force D3D9 merely because D3D11 was selected. Continue the clean run and collect deeper Unity/gameplay evidence.", "experiment": clean}

    return {"priority": "more evidence", "action": "Rerun the clean baseline and collect both madeira-log.txt and HunieCamStudio_Data/output_log.txt if Unity created it.", "experiment": clean}


def analyze(madeira_text: str, unity_text: str, preflight: dict[str, object] | None = None) -> dict[str, object]:
    markers = collect_markers(madeira_text, MADEIRA_MARKERS, "madeira") + collect_markers(unity_text, UNITY_MARKERS, "unity")
    fatals = collect_fatals(madeira_text, FATALS, "madeira") + collect_fatals(unity_text, UNITY_FATALS, "unity")
    stage = max([int(m["stage"]) for m in markers] or [0])
    result: dict[str, object] = {
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
            "fex_jit_dump_mentioned": bool(re.search(r"fex-jit-dump\.bin", madeira_text, re.I)),
        },
    }
    if preflight is not None:
        result["preflight"] = {"schema": preflight.get("schema"), "exe_found": preflight.get("exe_found"), "identity": preflight.get("identity"), "runtime_signals": preflight.get("runtime_signals")}
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
