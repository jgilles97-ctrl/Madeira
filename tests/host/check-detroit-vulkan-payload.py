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
        fake_pe(path, 0x8664)
        require(mod.pe_machine(path) == 0x8664, "x86-64 machine parse failed")
        path.write_bytes(b"not-a-pe")
        try:
            mod.pe_machine(path)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid file was accepted as PE")


def test_expected_machine_constant() -> None:
    require(mod.ARM64EC == 0xA641, "IMAGE_FILE_MACHINE_ARM64EC constant changed")


def main() -> int:
    test_pe_machine()
    print("PASS test_pe_machine")
    test_expected_machine_constant()
    print("PASS test_expected_machine_constant")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
