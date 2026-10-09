#!/usr/bin/env python3
"""Host fixtures for tools/detroit_vulkan_payload.py."""

from __future__ import annotations

import importlib.util
import pathlib
import struct
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "detroit_vulkan_payload.py"
spec = importlib.util.spec_from_file_location("detroit_vulkan_payload", TOOL)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def fake_pe(path: pathlib.Path, machine: int) -> None:
    data = bytearray(512)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x84, machine)
    path.write_bytes(data)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def good_info(lib: pathlib.Path) -> dict[str, str]:
    return {
        "source": mod.EXPECTED_MOLTENVK_REPO,
        "release": mod.EXPECTED_MOLTENVK_RELEASE,
        "ref": mod.EXPECTED_MOLTENVK_COMMIT,
        "commit": mod.EXPECTED_MOLTENVK_COMMIT,
        "madeira_ipad_cache_split": "1",
        "madeira_ipad_cache_patch": mod.EXPECTED_IPAD_CACHE_PATCH,
        "platform": mod.EXPECTED_PLATFORM,
        "architecture": mod.EXPECTED_ARCHITECTURE,
        "private_metal_api": mod.EXPECTED_PRIVATE_METAL_API,
        "archive_sha256": mod.sha256_file(lib),
        "sdk_path": "/example/Xcode/iPhoneOS.sdk",
        "sdk_version": "27.0",
        "xcode_version": "Xcode 27.0;Build version TEST",
    }


def test_pe_machine() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "module.dll"
        fake_pe(path, mod.ARM64EC)
        require(mod.pe_machine(path) == mod.ARM64EC, "ARM64EC machine parse failed")
        fake_pe(path, mod.AMD64)
        require(mod.pe_machine(path) == mod.AMD64, "x86-64 machine parse failed")
        path.write_bytes(b"not-a-pe")
        try:
            mod.pe_machine(path)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid file was accepted as PE")


def test_expected_constants() -> None:
    require(mod.ARM64EC == 0xA641, "IMAGE_FILE_MACHINE_ARM64EC constant changed")
    require(mod.AMD64 == 0x8664, "IMAGE_FILE_MACHINE_AMD64 constant changed")
    require(len(mod.ARM64EC_MODULES) == 2, "expected two ARM64EC Vulkan modules")
    require(len(mod.X64_DEVICE_CANARIES) == 4, "expected four x64 gate executables")
    require("vulkan-device-gate-x64.exe" in mod.X64_DEVICE_CANARIES, "device gate missing from x64 payload contract")
    require(mod.EXPECTED_IPAD_CACHE_PATCH == "MADEIRA_IPAD_DISK_CACHE_SPLIT_V1",
            "audited iPad cache patch identity changed unexpectedly")
    require(mod.EXPECTED_PLATFORM == "iphoneos", "payload must target iPhoneOS device")
    require(mod.EXPECTED_ARCHITECTURE == "arm64", "payload must target arm64")
    require(mod.EXPECTED_PRIVATE_METAL_API == "0", "qualified baseline must use public Metal APIs")


def test_build_info_parser_and_pinned_identity() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        lib = root / "libMoltenVK.a"
        lib.write_bytes(b"deterministic-test-archive")
        expected = good_info(lib)
        path = root / "BUILD-INFO.txt"
        path.write_text("\n".join(f"{key}={value}" for key, value in expected.items()) + "\n", encoding="utf-8")
        info = mod.parse_build_info(path)
        for key, value in expected.items():
            require(info[key] == value, f"BUILD-INFO parse failed for {key}")
        require(mod.EXPECTED_MOLTENVK_COMMIT == "8b511fdc5351a37c305bc246e161796ddca56b18",
                "audited Release003 commit changed unexpectedly")


def test_good_moltenvk_provenance_passes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lib = pathlib.Path(tmp) / "libMoltenVK.a"
        lib.write_bytes(b"known-renderer-bytes")
        failures: list[str] = []
        warnings: list[str] = []
        mod.verify_moltenvk_provenance(
            lib,
            good_info(lib),
            mod.EXPECTED_MOLTENVK_COMMIT,
            failures,
            warnings,
        )
        require(not failures, f"valid provenance failed: {failures}")
        require(not warnings, f"valid provenance warned: {warnings}")


def test_mutated_archive_hash_blocks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lib = pathlib.Path(tmp) / "libMoltenVK.a"
        lib.write_bytes(b"original-renderer")
        info = good_info(lib)
        lib.write_bytes(b"mutated-renderer-after-build-info")
        failures: list[str] = []
        mod.verify_moltenvk_provenance(
            lib,
            info,
            mod.EXPECTED_MOLTENVK_COMMIT,
            failures,
            [],
        )
        require(any("SHA-256" in item for item in failures),
                "renderer mutation after BUILD-INFO did not block payload")


def test_wrong_platform_arch_or_private_api_blocks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lib = pathlib.Path(tmp) / "libMoltenVK.a"
        lib.write_bytes(b"known-renderer")
        cases = (
            ("platform", "iossimulator", "platform"),
            ("architecture", "x86_64", "architecture"),
            ("private_metal_api", "1", "private_metal_api"),
        )
        for field, value, expected_text in cases:
            info = good_info(lib)
            info[field] = value
            failures: list[str] = []
            mod.verify_moltenvk_provenance(
                lib,
                info,
                mod.EXPECTED_MOLTENVK_COMMIT,
                failures,
                [],
            )
            require(any(expected_text in item for item in failures),
                    f"bad {field}={value!r} did not block payload: {failures}")


def test_missing_toolchain_provenance_blocks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lib = pathlib.Path(tmp) / "libMoltenVK.a"
        lib.write_bytes(b"known-renderer")
        info = good_info(lib)
        for key in ("sdk_path", "sdk_version", "xcode_version"):
            broken = dict(info)
            broken.pop(key)
            failures: list[str] = []
            mod.verify_moltenvk_provenance(
                lib,
                broken,
                mod.EXPECTED_MOLTENVK_COMMIT,
                failures,
                [],
            )
            require(any(key in item for item in failures), f"missing {key} provenance did not block")


def main() -> int:
    tests = (
        test_pe_machine,
        test_expected_constants,
        test_build_info_parser_and_pinned_identity,
        test_good_moltenvk_provenance_passes,
        test_mutated_archive_hash_blocks,
        test_wrong_platform_arch_or_private_api_blocks,
        test_missing_toolchain_provenance_blocks,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
