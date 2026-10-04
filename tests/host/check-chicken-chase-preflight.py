#!/usr/bin/env python3
"""Host checks for tools/chicken_chase_preflight.py.

These tests exercise the decision logic without requiring game files or an iOS SDK.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools/chicken_chase_preflight.py"

spec = importlib.util.spec_from_file_location("chicken_chase_preflight", MODULE_PATH)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_renderer_priority() -> None:
    result = mod.classify_api(["gdi32.dll", "ddraw.dll", "user32.dll", "winmm.dll"])
    assert result["renderer"] == "DirectDraw", result
    assert result["renderer_risk"] == "yellow-red", result
    assert "GDI" in result["graphics"]
    assert "DirectDraw" in result["graphics"]
    assert "WinMM" in result["audio"]


def test_d3d9_path() -> None:
    result = mod.classify_api(["kernel32.dll", "user32.dll", "d3d9.dll", "dsound.dll"])
    assert result["renderer"] == "Direct3D 9", result
    assert result["renderer_risk"] == "green-yellow", result
    assert "DirectSound" in result["audio"]


def test_gdi_path() -> None:
    result = mod.classify_api(["kernel32.dll", "user32.dll", "gdi32.dll"])
    assert result["renderer"] == "GDI", result
    assert result["renderer_risk"] == "green", result


def test_managed_warning() -> None:
    pe = {"is_i386": True, "managed_dotnet": True}
    api = mod.classify_api(["mscoree.dll", "user32.dll", "gdi32.dll"])
    risks = {
        "writable_executable_sections": [],
        "high_entropy_executable_sections": [],
        "packed_or_smc_risk": False,
    }
    rec = mod.recommendation(pe, api, risks)
    assert not rec["blockers"], rec
    assert any("Managed/.NET" in warning for warning in rec["warnings"]), rec


def test_packed_warning() -> None:
    pe = {"is_i386": True, "managed_dotnet": False}
    api = mod.classify_api(["user32.dll", "gdi32.dll"])
    risks = {
        "writable_executable_sections": [".text"],
        "high_entropy_executable_sections": [],
        "packed_or_smc_risk": True,
    }
    rec = mod.recommendation(pe, api, risks)
    assert any("Writable+executable" in warning for warning in rec["warnings"]), rec


def test_wrong_arch_is_blocker() -> None:
    pe = {"is_i386": False, "managed_dotnet": False}
    api = mod.classify_api(["user32.dll", "gdi32.dll"])
    risks = {
        "writable_executable_sections": [],
        "high_entropy_executable_sections": [],
        "packed_or_smc_risk": False,
    }
    rec = mod.recommendation(pe, api, risks)
    assert rec["blockers"], rec


def test_farm_gate() -> None:
    api = mod.classify_api(["user32.dll", "gdi32.dll", "winmm.dll"])
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        farm = repo / "app/Madeira/i386-windows"
        farm.mkdir(parents=True)
        result = mod.check_madeira_farm(repo, api)
        assert not result["ready_for_i386_launch"]
        assert "ntdll.dll" in result["missing_required_modules"]

        for name in result["required_modules"]:
            (farm / name).write_bytes(b"x")
        result = mod.check_madeira_farm(repo, api)
        assert result["ready_for_i386_launch"], result
        assert not result["missing_required_modules"], result


def test_section_risk_flags() -> None:
    risks = mod.section_risks(
        [
            {
                "name": ".text",
                "characteristics": mod.SECTION_READ | mod.SECTION_EXECUTE,
                "entropy": 6.2,
            },
            {
                "name": ".packed",
                "characteristics": mod.SECTION_READ | mod.SECTION_WRITE | mod.SECTION_EXECUTE,
                "entropy": 7.8,
            },
        ]
    )
    assert risks["packed_or_smc_risk"], risks
    assert ".packed" in risks["writable_executable_sections"], risks
    assert risks["high_entropy_executable_sections"], risks


def main() -> int:
    tests = [
        test_renderer_priority,
        test_d3d9_path,
        test_gdi_path,
        test_managed_warning,
        test_packed_warning,
        test_wrong_arch_is_blocker,
        test_farm_gate,
        test_section_risk_flags,
    ]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("PASS chicken_chase_preflight (%d checks)" % len(tests))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
