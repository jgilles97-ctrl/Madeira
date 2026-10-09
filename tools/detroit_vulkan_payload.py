#!/usr/bin/env python3
"""Read-only verifier for Madeira's Detroit Vulkan runtime payload."""

from __future__ import annotations

import argparse
import pathlib
import struct
import sys

ARM64EC = 0xA641


def pe_machine(path: pathlib.Path) -> int:
    data = path.read_bytes()
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError("missing MZ header")
    peoff = struct.unpack_from("<I", data, 0x3C)[0]
    if peoff + 6 > len(data) or data[peoff : peoff + 4] != b"PE\0\0":
        raise ValueError("missing PE signature")
    return struct.unpack_from("<H", data, peoff + 4)[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--farm", type=pathlib.Path, required=True)
    ap.add_argument("--moltenvk", type=pathlib.Path, required=True)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    failures: list[str] = []
    warnings: list[str] = []

    for name in ("vulkan-1.dll", "winevulkan.dll"):
        path = args.farm / name
        if not path.is_file():
            failures.append(f"{name}: missing from ARM64EC DLL farm")
            continue
        try:
            machine = pe_machine(path)
        except (OSError, ValueError) as exc:
            failures.append(f"{name}: invalid PE: {exc}")
            continue
        if machine != ARM64EC:
            failures.append(f"{name}: PE machine 0x{machine:04x}, expected ARM64EC 0x{ARM64EC:04x}")
        else:
            print(f"PASS {name}: ARM64EC PE ({path.stat().st_size} bytes)")

    lib = args.moltenvk / "lib" / "libMoltenVK.a"
    header = args.moltenvk / "include" / "vulkan" / "vulkan.h"
    info = args.moltenvk / "BUILD-INFO.txt"
    if not lib.is_file() or lib.stat().st_size == 0:
        failures.append("MoltenVK: missing/empty lib/libMoltenVK.a")
    else:
        print(f"PASS MoltenVK archive: {lib.stat().st_size} bytes")
    if not header.is_file():
        failures.append("MoltenVK: missing Vulkan headers")
    else:
        print("PASS MoltenVK headers")
    if info.is_file():
        text = info.read_text(encoding="utf-8", errors="replace")
        ref = next((line.split("=", 1)[1] for line in text.splitlines() if line.startswith("ref=")), "unknown")
        print(f"INFO MoltenVK ref={ref}")
        if ref != "Release003":
            warnings.append(f"MoltenVK ref is {ref}, not the currently pinned Detroit baseline Release003")
    else:
        warnings.append("MoltenVK BUILD-INFO.txt missing; source identity is not recorded")

    for item in warnings:
        print(f"WARN {item}")
    for item in failures:
        print(f"FAIL {item}")

    if failures:
        print("RESULT=BLOCKED")
        return 1 if args.strict else 0
    print("RESULT=READY_FOR_DEVICE_VULKAN_PROBES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
