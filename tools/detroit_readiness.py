#!/usr/bin/env python3
"""Read-only readiness audit for Detroit: Become Human under Madeira.

The audit deliberately does not patch, delete, or move game files. It turns the
high-signal Detroit/MoltenVK conditions we know about into a repeatable report
that can be captured before and after each iPad test.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from dataclasses import asdict, dataclass
from typing import Iterable

SCHEMA = "MADEIRA_DETROIT_READINESS_V1"


@dataclass(frozen=True)
class Check:
    code: str
    status: str  # PASS, WARN, FAIL, INFO
    summary: str
    detail: str = ""


def _size_tree(path: pathlib.Path) -> tuple[int, int]:
    total = 0
    files = 0
    if not path.exists():
        return total, files
    for child in path.rglob("*"):
        if not child.is_file():
            continue
        files += 1
        try:
            total += child.stat().st_size
        except OSError:
            pass
    return total, files


def _human_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    number = float(value)
    for unit in units:
        if number < 1024.0 or unit == units[-1]:
            return f"{number:.2f} {unit}"
        number /= 1024.0
    return f"{value} B"


def _read(path: pathlib.Path | None) -> str:
    if path is None or not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _find_first(root: pathlib.Path | None, names: Iterable[str]) -> pathlib.Path | None:
    if root is None or not root.exists():
        return None
    lowered = {name.lower() for name in names}
    for child in root.rglob("*"):
        if child.is_file() and child.name.lower() in lowered:
            return child
    return None


def _config_value(text: str, key: str) -> str | None:
    """Return the last Madeira-style KEY=value or env.KEY=value setting.

    Per-game config is intentionally line based. Ignore full-line comments and
    inline comments so a documented example does not get mistaken for an active
    setting. Last assignment wins, matching the way a user expects overrides to
    behave when a setting is repeated later in a game-specific profile.
    """

    result: str | None = None
    pattern = re.compile(rf"^(?:env\.)?{re.escape(key)}\s*=\s*(.*?)\s*$", re.I)
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = pattern.match(line)
        if match:
            result = match.group(1).strip().strip('"\'')
    return result


def audit(
    game_dir: pathlib.Path | None,
    graphics_options: pathlib.Path | None,
    shader_cache: pathlib.Path | None,
    env_file: pathlib.Path | None,
    log_file: pathlib.Path | None,
) -> dict[str, object]:
    checks: list[Check] = []

    # Game payload
    exe = _find_first(game_dir, ("DetroitBecomeHuman.exe",)) if game_dir else None
    if exe:
        try:
            size = exe.stat().st_size
        except OSError:
            size = 0
        checks.append(Check("game_exe", "PASS", "Detroit executable found", str(exe)))
        if size and size < 10 * 1024 * 1024:
            checks.append(
                Check(
                    "game_exe_size",
                    "WARN",
                    "Detroit executable is unexpectedly small",
                    _human_bytes(size),
                )
            )
    elif game_dir:
        checks.append(Check("game_exe", "FAIL", "DetroitBecomeHuman.exe was not found", str(game_dir)))
    else:
        checks.append(Check("game_exe", "INFO", "Game directory was not supplied"))

    # GraphicOptions.JSON: Detroit's current MoltenVK compatibility path has a
    # known depth-of-field rendering problem.
    if graphics_options is None:
        graphics_options = _find_first(game_dir, ("GraphicOptions.JSON",)) if game_dir else None
    if graphics_options and graphics_options.exists():
        try:
            opts = json.loads(_read(graphics_options))
            dof = opts.get("DEPTH_OF_FIELD") if isinstance(opts, dict) else None
            if dof in (0, False, "0"):
                checks.append(Check("depth_of_field", "PASS", "Depth of field is disabled", str(graphics_options)))
            else:
                checks.append(
                    Check(
                        "depth_of_field",
                        "WARN",
                        "Depth of field is not confirmed off",
                        f"DEPTH_OF_FIELD={dof!r}; historical MoltenVK Detroit builds render it incorrectly",
                    )
                )
        except (OSError, json.JSONDecodeError) as exc:
            checks.append(Check("graphics_options", "WARN", "GraphicOptions.JSON could not be parsed", str(exc)))
    else:
        checks.append(Check("graphics_options", "INFO", "GraphicOptions.JSON was not supplied/found"))

    # Shader cache. Never mutate it here.
    if shader_cache is None and game_dir:
        candidate = game_dir / "ShaderCache"
        if candidate.exists():
            shader_cache = candidate
    if shader_cache and shader_cache.exists():
        total, count = _size_tree(shader_cache)
        bin_count = sum(1 for p in shader_cache.rglob("*.bin") if p.is_file())
        bak_count = sum(1 for p in shader_cache.rglob("*.bak") if p.is_file())
        checks.append(
            Check(
                "shader_cache",
                "PASS",
                "Shader cache is present",
                f"{count} files, {_human_bytes(total)}, .bin={bin_count}, .bak={bak_count}",
            )
        )
        if total > 4 * 1024**3:
            checks.append(
                Check(
                    "shader_cache_size",
                    "WARN",
                    "Shader cache exceeds 4 GiB",
                    "Large caches are especially important to track on an 8 GB iPad because shader finalization has caused large memory spikes.",
                )
            )
    else:
        checks.append(Check("shader_cache", "INFO", "Shader cache was not supplied/found"))

    # Environment / launcher configuration. The first 8 GB iPad pass optimizes
    # for measured peak memory, not desktop assumptions.
    env_text = _read(env_file)
    if env_file:
        if not env_text:
            checks.append(Check("env_file", "FAIL", "Environment/config file could not be read", str(env_file)))
        else:
            compression = _config_value(env_text, "MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM")
            if compression == "3":
                checks.append(
                    Check(
                        "shader_compression",
                        "PASS",
                        "Detroit shader compression uses the known-good algorithm",
                        "algorithm 3 is LZ4; MoltenVK documents shader-source compression as a way to reduce large retained MSL-source memory",
                    )
                )
            elif compression is not None:
                checks.append(
                    Check(
                        "shader_compression",
                        "WARN",
                        "Detroit shader compression differs from the tested Apple-Silicon setting",
                        f"value={compression}; the first iPad profile uses 3 (LZ4)",
                    )
                )
            else:
                checks.append(
                    Check(
                        "shader_compression",
                        "WARN",
                        "MoltenVK shader compression is not visible in the supplied config",
                        "Successful full-game Apple-Silicon Detroit runs used algorithm 3, and MoltenVK documents shader-source retention as potentially significant memory use.",
                    )
                )

            # The Detroit macOS recipe sets this to 1, but current MoltenVK
            # explicitly documents this setting as having no effect on iOS or
            # tvOS. Never count 0 as an iPad memory optimization.
            concurrent = _config_value(env_text, "MVK_CONFIG_SHOULD_MAXIMIZE_CONCURRENT_COMPILATION")
            if concurrent is not None:
                checks.append(
                    Check(
                        "concurrent_compilation_ios_noop",
                        "INFO",
                        "Concurrent-compilation setting is ignored on iOS",
                        f"value={concurrent}; MoltenVK documents this switch as macOS-only, so it is not an iPad memory or speed lever",
                    )
                )

            msl_cache = _config_value(env_text, "MVK_DTR_MSL_LIBRARY_CACHE")
            if msl_cache == "0":
                checks.append(
                    Check(
                        "dtr_msl_library_cache",
                        "PASS",
                        "Release003 custom process-wide Metal library cache is disabled",
                        "memory-first 8 GB baseline; re-enable only after device measurements show the retained libraries fit comfortably",
                    )
                )
            elif msl_cache == "1":
                checks.append(
                    Check(
                        "dtr_msl_library_cache",
                        "WARN",
                        "Release003 custom Metal library cache is enabled",
                        "The Detroit fork keeps compiled MTLLibrary objects in a process-wide map for the process lifetime. This is high-risk until measured on an 8 GB iPad.",
                    )
                )
            else:
                checks.append(
                    Check(
                        "dtr_msl_library_cache",
                        "WARN",
                        "Release003 custom Metal library cache is not explicitly disabled",
                        "Its fork default is enabled; set MVK_DTR_MSL_LIBRARY_CACHE=0 for the first 8 GB iPad shader pass.",
                    )
                )

            device_stats = _config_value(env_text, "MADEIRA_DEVICE_STATS")
            if device_stats == "1":
                checks.append(
                    Check(
                        "device_stats",
                        "PASS",
                        "Madeira device diagnostics are enabled",
                        "the long shader test will record current app memory headroom, current/peak footprint, thermal state, and Low Power Mode",
                    )
                )
            else:
                checks.append(
                    Check(
                        "device_stats",
                        "INFO",
                        "Madeira device diagnostics are not enabled",
                        "MADEIRA_DEVICE_STATS=1 is recommended for the first long Detroit shader run.",
                    )
                )
    else:
        checks.append(Check("env_file", "INFO", "No Madeira/MoltenVK environment file supplied"))

    # Runtime log signatures. Order keeps lower-level loader/driver failures
    # visible before Detroit-specific shader errors.
    log_text = _read(log_file)
    known_log_rules: tuple[tuple[str, str, str, re.Pattern[str], str], ...] = (
        (
            "guest_vulkan_loader_missing",
            "FAIL",
            "Windows Vulkan loader is missing or failed to load",
            re.compile(r"(?:vulkan-1\.dll.{0,120}(?:not found|failed|cannot|c0000135)|(?:not found|failed|cannot|c0000135).{0,120}vulkan-1\.dll)", re.I),
            "Rebuild the Detroit Vulkan payload and verify ARM64EC vulkan-1.dll is in Madeira's DLL farm before changing MoltenVK.",
        ),
        (
            "guest_winevulkan_missing",
            "FAIL",
            "Wine Vulkan ICD is missing or failed to load",
            re.compile(r"(?:winevulkan(?:\.dll|\.so)?.{0,120}(?:not found|failed|cannot|c0000135)|(?:not found|failed|cannot|c0000135).{0,120}winevulkan(?:\.dll|\.so)?)", re.I),
            "Verify both ARM64EC winevulkan.dll and the compiled one-process winevulkan unix-call table.",
        ),
        (
            "wine_vulkan_driver_unavailable",
            "FAIL",
            "Wine could not obtain a Vulkan graphics driver",
            re.compile(r"Failed to load Wine graphics driver supporting Vulkan|pVulkanInit.{0,120}(?:not implemented|failed)|STATUS_NOT_IMPLEMENTED.{0,120}Vulkan", re.I),
            "Check the strong iOS pVulkanInit wiring and the win32u static MoltenVK driver before debugging Detroit.",
        ),
        (
            "ios_vulkan_surface_bridge_missing",
            "FAIL",
            "Madeira could not reach its HWND-to-Metal surface bridge",
            re.compile(r"\[madeira-vulkan\].{0,160}(?:display shim exports unavailable|WSI acquire failed|no Metal)", re.I),
            "Verify IOSDisplayShim exports and the per-window Metal-layer lifetime bridge before launching Detroit.",
        ),
        (
            "mvk_init_failure",
            "FAIL",
            "MoltenVK reported pipeline/shader initialization failure",
            re.compile(r"VK_ERROR_INITIALIZATION_FAILED", re.I),
            "Keep the first error plus the following shader/pipeline diagnostic; do not treat this as a generic FEX crash.",
        ),
        (
            "r32uint_blending",
            "FAIL",
            "Known Detroit R32Uint blending incompatibility detected",
            re.compile(r"(?:R32Uint.{0,100}blend|blend.{0,100}R32Uint)", re.I),
            "The Detroit MoltenVK fork contains a targeted workaround for this class of pipeline.",
        ),
        (
            "missing_vertex_attribute",
            "FAIL",
            "Known Detroit missing vertex-attribute pipeline failure detected",
            re.compile(r"vertex attribute .+ missing from the vertex descriptor", re.I),
            "Verify the Detroit MoltenVK compatibility patches are actually in the iOS build.",
        ),
        (
            "draw_index_binding",
            "FAIL",
            "Known spvDrawIndex binding failure detected",
            re.compile(r"spvDrawIndex|missing Buffer binding at index", re.I),
            "Verify draw-ID compatibility changes and the SPIRV-Cross revision.",
        ),
        (
            "locn10_interface",
            "FAIL",
            "Known later-game shader-interface failure detected",
            re.compile(r"user\(locn10\).{0,120}(?:mismatch|not written)", re.I),
            "This was exposed by later chapters such as On The Run; use a Detroit fork carrying the corresponding SPIRV-Cross/MoltenVK fix.",
        ),
        (
            "shader_98_percent",
            "WARN",
            "Shader compilation appears to have reached the historical 98% danger point",
            re.compile(r"(?:compil(?:e|ing) shaders?.{0,80}98%|98%.{0,80}shader)", re.I),
            "If the process dies here, inspect measured app-memory headroom and cache finalization before changing unrelated CPU translation code.",
        ),
        (
            "memory_pressure",
            "FAIL",
            "Possible memory-pressure / jetsam failure detected",
            re.compile(r"jetsam|memorystatus|out of memory|STATUS_NO_MEMORY|c0000017", re.I),
            "Preserve the log and run tools/detroit_memory_report.py; compare app headroom/footprint near the failure with shader progress, cache size, compression, and Memory+ state.",
        ),
    )

    if log_file:
        if not log_text:
            checks.append(Check("runtime_log", "FAIL", "Runtime log could not be read", str(log_file)))
        else:
            for code, status, summary, pattern, guidance in known_log_rules:
                hits = [line.strip() for line in log_text.splitlines() if pattern.search(line)]
                if hits:
                    sample = hits[0]
                    if len(sample) > 240:
                        sample = sample[:237] + "..."
                    checks.append(Check(code, status, summary, f"{guidance} First match: {sample}"))
    else:
        checks.append(Check("runtime_log", "INFO", "No runtime log supplied"))

    counts = {name: 0 for name in ("FAIL", "WARN", "PASS", "INFO")}
    for check in checks:
        counts[check.status] = counts.get(check.status, 0) + 1

    overall = "BLOCKED" if counts["FAIL"] else "CAUTION" if counts["WARN"] else "READY_FOR_NEXT_GATE"
    return {
        "schema": SCHEMA,
        "overall": overall,
        "counts": counts,
        "checks": [asdict(item) for item in checks],
        "notes": [
            "This is a readiness/triage tool, not proof that Detroit is compatible with the device.",
            "It never modifies or deletes the game, cache, configuration, or log files.",
            "The 8 GB memory profile is a conservative first-test baseline, not a claim that faster settings are impossible.",
            "MVK_CONFIG_SHOULD_MAXIMIZE_CONCURRENT_COMPILATION is not counted as an iPad optimization because MoltenVK documents it as ineffective on iOS/tvOS.",
        ],
    }


def render(report: dict[str, object]) -> str:
    lines = [
        "# Detroit / Madeira readiness",
        "",
        f"Overall: {report['overall']}",
        "",
    ]
    checks = report.get("checks", [])
    if isinstance(checks, list):
        for raw in checks:
            if not isinstance(raw, dict):
                continue
            lines.append(f"[{raw.get('status')}] {raw.get('summary')} (`{raw.get('code')}`)")
            detail = str(raw.get("detail") or "").strip()
            if detail:
                lines.append(f"  {detail}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Detroit/Madeira readiness audit")
    parser.add_argument("--game-dir", type=pathlib.Path)
    parser.add_argument("--graphics-options", type=pathlib.Path)
    parser.add_argument("--shader-cache", type=pathlib.Path)
    parser.add_argument("--env-file", type=pathlib.Path)
    parser.add_argument("--log", dest="log_file", type=pathlib.Path)
    parser.add_argument("--json", dest="json_path", type=pathlib.Path)
    parser.add_argument("--strict", action="store_true", help="return non-zero for FAIL findings")
    args = parser.parse_args()

    report = audit(
        game_dir=args.game_dir,
        graphics_options=args.graphics_options,
        shader_cache=args.shader_cache,
        env_file=args.env_file,
        log_file=args.log_file,
    )
    if args.json_path:
        args.json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(render(report))
    return 1 if args.strict and report["overall"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
