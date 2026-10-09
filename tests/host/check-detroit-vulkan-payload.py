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


def test_expected_machine_constants() -> None:
    require(mod.ARM64EC == 0xA641, "IMAGE_FILE_MACHINE_ARM64EC constant changed")
    require(mod.AMD64 == 0x8664, "IMAGE_FILE_MACHINE_AMD64 constant changed")
    require(len(mod.ARM64EC_MODULES) == 2, "expected two ARM64EC Vulkan modules")
    require(len(mod.X64_DEVICE_CANARIES) == 4, "expected four x64 gate executables")
    require("vulkan-device-gate-x64.exe" in mod.X64_DEVICE_CANARIES, "device gate missing from x64 payload contract")
    require(
        mod.EXPECTED_IPAD_CACHE_PATCH == "MADEIRA_IPAD_DISK_CACHE_SPLIT_V1",
        "audited iPad cache patch identity changed unexpectedly",
    )


def test_build_info_parser_and_pinned_identity() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "BUILD-INFO.txt"
        path.write_text(
            "\n".join(
                [
                    f"source={mod.EXPECTED_MOLTENVK_REPO}",
                    f"release={mod.EXPECTED_MOLTENVK_RELEASE}",
                    f"ref={mod.EXPECTED_MOLTENVK_COMMIT}",
                    f"commit={mod.EXPECTED_MOLTENVK_COMMIT}",
                    "madeira_ipad_cache_split=1",
                    f"madeira_ipad_cache_patch={mod.EXPECTED_IPAD_CACHE_PATCH}",
                    "sdk=/example/iPhoneOS.sdk",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        info = mod.parse_build_info(path)
        require(info["source"] == mod.EXPECTED_MOLTENVK_REPO, "source parse failed")
        require(info["release"] == "Release003", "release parse failed")
        require(info["ref"] == mod.EXPECTED_MOLTENVK_COMMIT, "ref parse failed")
        require(info["commit"] == mod.EXPECTED_MOLTENVK_COMMIT, "commit parse failed")
        require(info["madeira_ipad_cache_split"] == "1", "iPad cache split parse failed")
        require(
            info["madeira_ipad_cache_patch"] == mod.EXPECTED_IPAD_CACHE_PATCH,
            "iPad cache patch identity parse failed",
        )
        require(
            mod.EXPECTED_MOLTENVK_COMMIT == "8b511fdc5351a37c305bc246e161796ddca56b18",
            "audited Release003 commit changed unexpectedly",
        )


def main() -> int:
    test_pe_machine()
    print("PASS test_pe_machine")
    test_expected_machine_constants()
    print("PASS test_expected_machine_constants")
    test_build_info_parser_and_pinned_identity()
    print("PASS test_build_info_parser_and_pinned_identity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
