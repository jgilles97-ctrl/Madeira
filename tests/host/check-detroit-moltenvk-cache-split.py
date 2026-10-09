#!/usr/bin/env python3
"""Host guardrails for Madeira's Detroit MoltenVK low-memory cache split."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PATCHER = ROOT / "build/moltenvk-ios/patch_detroit_ipad_cache.py"
BUILD = ROOT / "build/moltenvk-ios/build.sh"
PROFILE = ROOT / "docs/detroit-m4-8gb.cfg"

spec = importlib.util.spec_from_file_location("patch_detroit_ipad_cache", PATCHER)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def release003_fixture() -> str:
    return "\n".join(
        [
            "static bool mvkDTRMSLLibraryCacheEnabled() { return mvkDTRBoolEnvValue(\"MVK_DTR_MSL_LIBRARY_CACHE\", true); }",
            mod.OLD_DISK_SWITCH,
            "static id<MTLLibrary> mvkDTRNewMTLLibrary() {",
            "\tbool processCacheEnabled = mvkDTRMSLLibraryCacheEnabled();",
            "\tbool diskCacheEnabled = mvkDTRMSLLibraryDiskCacheEnabled();",
            "\tMVKDTRMSLLibraryCacheKey key;",
            mod.KEY_END,
            "\tauto entry = mvkDTRGetMSLLibraryCacheEntry(key, shouldCompile);",
            "\treturn nil;",
            "}",
            "",
        ]
    )


def test_patch_semantics() -> None:
    source = release003_fixture()
    patched = mod.patch_text(source)
    require(mod.PATCH_MARKER in patched, "patch marker missing")
    require(
        'mvkDTRBoolEnvValue("MVK_DTR_MSL_LIBRARY_DISK_CACHE", mvkDTRMSLLibraryCacheEnabled())' in patched,
        "disk cache no longer defaults to historical process-cache setting",
    )
    branch = patched.index("if ( !processCacheEnabled )")
    global_cache = patched.index("mvkDTRGetMSLLibraryCacheEntry(key, shouldCompile)")
    require(branch < global_cache, "disk-only branch must run before global RAM cache insertion")
    low = patched[branch:global_cache]
    require("mvkDTRLoadMSLLibraryFromDisk" in low, "disk-only mode cannot load a precompiled metallib")
    require("slc->newMTLLibrary" in low, "disk-only cache miss cannot compile normally")
    require("mvkDTRDumpMSLLibraryDiskCacheSource" in low, "disk-only miss cannot collect MSL source")
    require("mvkDTRGetMSLLibraryCacheEntry" not in low, "disk-only branch still enters global RAM cache")
    require("entry->library" not in low, "disk-only branch still retains MTLLibrary globally")


def test_patch_is_idempotent_and_fail_closed() -> None:
    patched = mod.patch_text(release003_fixture())
    require(mod.patch_text(patched) == patched, "second patch changed already-patched source")
    try:
        mod.patch_text(release003_fixture().replace(mod.OLD_DISK_SWITCH, "// source drift"))
    except ValueError:
        pass
    else:
        raise AssertionError("patcher accepted source with a drifted Release003 disk-cache anchor")

    partial = patched.replace("mvkDTRDumpMSLLibraryDiskCacheSource(key, msl, compileNanos)", "missing_dump_call")
    try:
        mod.patch_text(partial)
    except ValueError:
        pass
    else:
        raise AssertionError("patcher accepted a partial/stale Madeira cache patch")


def test_build_records_local_delta() -> None:
    text = BUILD.read_text(encoding="utf-8")
    for needle in (
        "patch_detroit_ipad_cache.py",
        "MADEIRA_IPAD_DISK_CACHE_SPLIT_V1",
        'python3 "$CACHE_PATCH" "$SHADER_MODULE"',
        "madeira_ipad_cache_split=1",
        "madeira_ipad_cache_patch=$CACHE_PATCH_MARKER",
    ):
        require(needle in text, f"MoltenVK build lost cache-split contract: {needle}")


def test_8gb_profile_is_disk_only() -> None:
    text = PROFILE.read_text(encoding="utf-8")
    require("MVK_DTR_MSL_LIBRARY_CACHE = 0" in text, "8 GB profile must disable process-wide MTLLibrary retention")
    require("MVK_DTR_MSL_LIBRARY_DISK_CACHE = 1" in text, "8 GB profile must enable disk cache independently")
    require("MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM = 3" in text, "Detroit shader compression baseline changed")


def main() -> int:
    tests = (
        test_patch_semantics,
        test_patch_is_idempotent_and_fail_closed,
        test_build_records_local_delta,
        test_8gb_profile_is_disk_only,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
