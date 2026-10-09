#!/usr/bin/env python3
"""Read-only verifier for Madeira's Detroit Vulkan runtime payload."""

from __future__ import annotations

import argparse
import pathlib
import struct

ARM64EC = 0xA641
AMD64 = 0x8664
EXPECTED_MOLTENVK_REPO = "https://github.com/DiAvisoo/MoltenVK-Detroit.git"
EXPECTED_MOLTENVK_RELEASE = "Release003"
EXPECTED_MOLTENVK_COMMIT = "8b511fdc5351a37c305bc246e161796ddca56b18"
EXPECTED_IPAD_CACHE_PATCH = "MADEIRA_IPAD_DISK_CACHE_SPLIT_V1"
ARM64EC_MODULES = ("vulkan-1.dll", "winevulkan.dll")
X64_DEVICE_CANARIES = (
    "vulkan_probe.exe",
    "vulkan_wsi_probe.exe",
    "vulkan_swapchain_probe.exe",
    "vulkan-device-gate-x64.exe",
)


def pe_machine(path: pathlib.Path) -> int:
    data = path.read_bytes()
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError("missing MZ header")
    peoff = struct.unpack_from("<I", data, 0x3C)[0]
    if peoff + 6 > len(data) or data[peoff : peoff + 4] != b"PE\0\0":
        raise ValueError("missing PE signature")
    return struct.unpack_from("<H", data, peoff + 4)[0]


def parse_build_info(path: pathlib.Path) -> dict[str, str]:
    info: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if key:
            info[key] = value.strip()
    return info


def verify_pe(
    path: pathlib.Path,
    expected_machine: int,
    expected_label: str,
    failures: list[str],
) -> None:
    if not path.is_file():
        failures.append(f"{path.name}: missing from Windows payload farm")
        return
    try:
        machine = pe_machine(path)
    except (OSError, ValueError) as exc:
        failures.append(f"{path.name}: invalid PE: {exc}")
        return
    if machine != expected_machine:
        failures.append(
            f"{path.name}: PE machine 0x{machine:04x}, expected {expected_label} 0x{expected_machine:04x}"
        )
        return
    print(f"PASS {path.name}: {expected_label} PE ({path.stat().st_size} bytes)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--farm", type=pathlib.Path, required=True)
    ap.add_argument("--moltenvk", type=pathlib.Path, required=True)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument(
        "--expected-moltenvk-commit",
        default=EXPECTED_MOLTENVK_COMMIT,
        help=(
            "Exact audited MoltenVK commit expected in BUILD-INFO.txt. "
            "Defaults to Detroit Release003. A deliberate fork upgrade must pass its reviewed commit explicitly."
        ),
    )
    args = ap.parse_args()

    failures: list[str] = []
    warnings: list[str] = []

    expected_commit = args.expected_moltenvk_commit.strip().lower()
    if not expected_commit or len(expected_commit) != 40 or any(c not in "0123456789abcdef" for c in expected_commit):
        failures.append("expected MoltenVK commit must be a full 40-character hexadecimal Git commit")

    for name in ARM64EC_MODULES:
        verify_pe(args.farm / name, ARM64EC, "ARM64EC", failures)

    for name in X64_DEVICE_CANARIES:
        verify_pe(args.farm / name, AMD64, "x86-64", failures)

    lib = args.moltenvk / "lib" / "libMoltenVK.a"
    header = args.moltenvk / "include" / "vulkan" / "vulkan.h"
    info_path = args.moltenvk / "BUILD-INFO.txt"
    if not lib.is_file() or lib.stat().st_size == 0:
        failures.append("MoltenVK: missing/empty lib/libMoltenVK.a")
    else:
        print(f"PASS MoltenVK archive: {lib.stat().st_size} bytes")
    if not header.is_file():
        failures.append("MoltenVK: missing Vulkan headers")
    else:
        print("PASS MoltenVK headers")

    if info_path.is_file():
        info = parse_build_info(info_path)
        source = info.get("source")
        release = info.get("release")
        ref = info.get("ref")
        commit = (info.get("commit") or "").lower() or None
        cache_split = info.get("madeira_ipad_cache_split")
        cache_patch = info.get("madeira_ipad_cache_patch")
        print(
            "INFO MoltenVK "
            f"source={source or 'unknown'} release={release or 'unknown'} "
            f"ref={ref or 'unknown'} commit={commit or 'unknown'} "
            f"ipad_cache_patch={cache_patch or 'unknown'}"
        )
        if source != EXPECTED_MOLTENVK_REPO:
            failures.append(
                f"MoltenVK source identity is {source!r}, expected {EXPECTED_MOLTENVK_REPO!r}"
            )
        if release != EXPECTED_MOLTENVK_RELEASE:
            warnings.append(
                f"MoltenVK release label is {release!r}, baseline label is {EXPECTED_MOLTENVK_RELEASE!r}"
            )
        if commit != expected_commit:
            failures.append(
                f"MoltenVK commit is {commit!r}, expected explicitly audited commit {expected_commit!r}"
            )
        if cache_split != "1" or cache_patch != EXPECTED_IPAD_CACHE_PATCH:
            failures.append(
                "MoltenVK is missing Madeira's audited iPad disk-cache/RAM-cache split; "
                f"expected madeira_ipad_cache_split=1 and madeira_ipad_cache_patch={EXPECTED_IPAD_CACHE_PATCH}"
            )
        if ref and ref.lower() != expected_commit:
            warnings.append(
                f"MoltenVK checkout ref is {ref!r}; exact commit proof comes from BUILD-INFO commit={commit or 'unknown'}"
            )
    else:
        failures.append("MoltenVK BUILD-INFO.txt missing; exact source identity cannot be proved")

    for item in warnings:
        print(f"WARN {item}")
    for item in failures:
        print(f"FAIL {item}")

    if failures:
        print("RESULT=BLOCKED")
        return 1 if args.strict else 0
    print("RESULT=READY_FOR_DEVICE_VULKAN_GATE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
