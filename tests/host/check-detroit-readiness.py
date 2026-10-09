#!/usr/bin/env python3
"""Host checks for tools/detroit_readiness.py."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "detroit_readiness.py"

spec = importlib.util.spec_from_file_location("detroit_readiness", TOOL)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def code_map(report: dict[str, object]) -> dict[str, dict[str, object]]:
    checks = report["checks"]
    assert isinstance(checks, list)
    return {str(c["code"]): c for c in checks if isinstance(c, dict)}


def test_clean_fixture(root: pathlib.Path) -> None:
    game = root / "Detroit"
    game.mkdir()
    (game / "DetroitBecomeHuman.exe").write_bytes(b"MZ" + b"x" * (10 * 1024 * 1024))
    options = game / "GraphicOptions.JSON"
    options.write_text(json.dumps({"DEPTH_OF_FIELD": 0}), encoding="utf-8")
    cache = game / "ShaderCache"
    cache.mkdir()
    (cache / "pipeline.bin").write_bytes(b"cache")
    env = root / "madeira.cfg"
    env.write_text(
        "# comments and spacing should not confuse the parser\n"
        "env.MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM = 3\n"
        "env.MVK_DTR_MSL_LIBRARY_CACHE = 0\n"
        "env.MADEIRA_DEVICE_STATS = 1\n",
        encoding="utf-8",
    )
    log = root / "madeira-log.txt"
    log.write_text("Detroit boot\nCompiling Shaders 50%\nmenu reached\n", encoding="utf-8")

    report = mod.audit(game, options, cache, env, log)
    checks = code_map(report)
    require(report["overall"] == "READY_FOR_NEXT_GATE", f"unexpected status: {report['overall']}")
    require(checks["game_exe"]["status"] == "PASS", "game executable should pass")
    require(checks["depth_of_field"]["status"] == "PASS", "DOF=0 should pass")
    require(checks["shader_compression"]["status"] == "PASS", "compression should pass")
    require("concurrent_compilation_ios_noop" not in checks,
            "clean iPad profile should not need a macOS-only concurrency setting")
    require(checks["dtr_msl_library_cache"]["status"] == "PASS", "custom MSL cache=0 should pass")
    require(checks["device_stats"]["status"] == "PASS", "device diagnostics should pass")


def test_mac_concurrency_setting_is_informational_on_ios(root: pathlib.Path) -> None:
    env = root / "madeira.cfg"
    env.write_text(
        "env.MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM = 3\n"
        "env.MVK_CONFIG_SHOULD_MAXIMIZE_CONCURRENT_COMPILATION = 1\n"
        "env.MVK_DTR_MSL_LIBRARY_CACHE = 0\n",
        encoding="utf-8",
    )
    report = mod.audit(None, None, None, env, None)
    checks = code_map(report)
    require(checks["concurrent_compilation_ios_noop"]["status"] == "INFO",
            "macOS concurrency switch should be informational, not an iPad warning")
    require(report["overall"] == "READY_FOR_NEXT_GATE",
            "an iOS-ineffective setting alone must not downgrade readiness")


def test_release003_msl_cache_warns(root: pathlib.Path) -> None:
    env = root / "madeira.cfg"
    env.write_text(
        "env.MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM = 3\n"
        "env.MVK_CONFIG_SHOULD_MAXIMIZE_CONCURRENT_COMPILATION = 1\n"
        "env.MVK_DTR_MSL_LIBRARY_CACHE = 1\n",
        encoding="utf-8",
    )
    report = mod.audit(None, None, None, env, None)
    checks = code_map(report)
    require(report["overall"] == "CAUTION", "Release003 process-wide MSL cache should warn on 8 GB baseline")
    require(checks["concurrent_compilation_ios_noop"]["status"] == "INFO",
            "concurrency=1 must not be mislabeled as the memory risk on iOS")
    require(checks["dtr_msl_library_cache"]["status"] == "WARN", "Release003 cache=1 should warn")


def test_missing_release003_cache_setting_warns(root: pathlib.Path) -> None:
    env = root / "madeira.cfg"
    env.write_text("MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM=3\n", encoding="utf-8")
    report = mod.audit(None, None, None, env, None)
    checks = code_map(report)
    require(checks["dtr_msl_library_cache"]["status"] == "WARN",
            "Release003 default-on MSL cache must be explicit for the 8 GB baseline")


def test_last_assignment_wins_and_comments_are_ignored(root: pathlib.Path) -> None:
    env = root / "madeira.cfg"
    env.write_text(
        "# env.MVK_DTR_MSL_LIBRARY_CACHE = 1\n"
        "env.MVK_DTR_MSL_LIBRARY_CACHE = 1 # old experiment\n"
        "env.MVK_DTR_MSL_LIBRARY_CACHE = 0 # final override\n"
        "env.MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM = 3\n",
        encoding="utf-8",
    )
    report = mod.audit(None, None, None, env, None)
    checks = code_map(report)
    require(checks["dtr_msl_library_cache"]["status"] == "PASS",
            "last active assignment should win over comments and earlier value")


def test_known_shader_failures(root: pathlib.Path) -> None:
    log = root / "bad.log"
    log.write_text(
        "[mvk-error] VK_ERROR_INITIALIZATION_FAILED: Render pipeline compile failed\n"
        "Blending is enabled but MTLPixelFormatR32Uint is not blendable\n"
        "Vertex attribute in_color(3) is missing from the vertex descriptor\n"
        "Vertex Function(main0): missing Buffer binding at index 19 for spvDrawIndex[0]\n"
        "Fragment input(s) user(locn10) mismatching vertex shader output type(s) or not written\n"
        "Compiling Shaders 98%\n"
        "jetsam: process killed for memory pressure\n",
        encoding="utf-8",
    )
    report = mod.audit(None, None, None, None, log)
    checks = code_map(report)
    expected = {
        "mvk_init_failure",
        "r32uint_blending",
        "missing_vertex_attribute",
        "draw_index_binding",
        "locn10_interface",
        "shader_98_percent",
        "memory_pressure",
    }
    require(expected.issubset(checks), f"missing findings: {sorted(expected - set(checks))}")
    require(report["overall"] == "BLOCKED", "known hard failures should block the next gate")


def test_vulkan_loader_layer_failures(root: pathlib.Path) -> None:
    log = root / "loader.log"
    log.write_text(
        "err:module:import_dll Library vulkan-1.dll not found, status c0000135\n"
        "winevulkan.dll failed to load\n"
        "Failed to load Wine graphics driver supporting Vulkan\n"
        "[madeira-vulkan] display shim exports unavailable: create=(nil) get=(nil) release=(nil)\n",
        encoding="utf-8",
    )
    report = mod.audit(None, None, None, None, log)
    checks = code_map(report)
    expected = {
        "guest_vulkan_loader_missing",
        "guest_winevulkan_missing",
        "wine_vulkan_driver_unavailable",
        "ios_vulkan_surface_bridge_missing",
    }
    require(expected.issubset(checks), f"missing Vulkan-layer findings: {sorted(expected - set(checks))}")
    require(report["overall"] == "BLOCKED", "guest/driver Vulkan failures must block Detroit")


def test_no_destructive_behavior(root: pathlib.Path) -> None:
    cache = root / "ShaderCache"
    cache.mkdir()
    payload = cache / "keep.bin"
    payload.write_bytes(b"do-not-delete")
    before = payload.read_bytes()
    mod.audit(None, None, cache, None, None)
    require(payload.exists(), "audit deleted a cache file")
    require(payload.read_bytes() == before, "audit modified a cache file")


def main() -> int:
    for test in (
        test_clean_fixture,
        test_mac_concurrency_setting_is_informational_on_ios,
        test_release003_msl_cache_warns,
        test_missing_release003_cache_setting_warns,
        test_last_assignment_wins_and_comments_are_ignored,
        test_known_shader_failures,
        test_vulkan_loader_layer_failures,
        test_no_destructive_behavior,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            test(root)
            print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
