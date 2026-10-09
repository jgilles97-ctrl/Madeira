#!/usr/bin/env python3
"""Patch Detroit MoltenVK so disk shader caching can run without the RAM cache.

Release003 couples its process-wide MTLLibrary cache and its disk-source/
metallib cache behind MVK_DTR_MSL_LIBRARY_CACHE. That is a poor fit for the
8 GB iPad target: retaining every compiled MTLLibrary costs memory, while disk
cache hits/source dumps are useful precisely when RAM is tight.

The patch is intentionally tiny and fail-closed. Default Release003 behaviour
is unchanged: MVK_DTR_MSL_LIBRARY_DISK_CACHE inherits the process-cache setting
when it is not explicitly set. Madeira's Detroit profile may therefore use:

    MVK_DTR_MSL_LIBRARY_CACHE=0
    MVK_DTR_MSL_LIBRARY_DISK_CACHE=1

In that mode a precompiled .metallib is loaded when available. On a miss,
MoltenVK compiles normally and may dump the MSL source/meta files, but it does
NOT insert/retain the resulting MTLLibrary in Release003's global process map.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

PATCH_MARKER = "MADEIRA_IPAD_DISK_CACHE_SPLIT_V1"

OLD_DISK_SWITCH = (
    "static bool mvkDTRMSLLibraryDiskCacheEnabled() { return "
    "mvkDTRMSLLibraryCacheEnabled() && mvkDTRMSLLibraryDiskCacheDir() != nil; }"
)
NEW_DISK_SWITCH = f'''/* {PATCH_MARKER}: disk cache may be enabled independently from the\n * process-wide MTLLibrary retention cache. The default inherits Release003's\n * original process-cache switch, preserving upstream behaviour unless Madeira\n * opts into the low-memory iPad mode explicitly. */\nstatic bool mvkDTRMSLLibraryDiskCacheEnabled() {{\n\treturn mvkDTRBoolEnvValue("MVK_DTR_MSL_LIBRARY_DISK_CACHE", mvkDTRMSLLibraryCacheEnabled()) &&\n\t\t   mvkDTRMSLLibraryDiskCacheDir() != nil;\n}}'''

KEY_END = '''\tkey.fpFastMathFlags = shaderConversionResultInfo.entryPoint.fpFastMathFlags;\n\tkey.isPositionInvariant = shaderConversionResultInfo.isPositionInvariant;\n\n\tbool shouldCompile = false;'''

LOW_MEMORY_BRANCH = '''\tkey.fpFastMathFlags = shaderConversionResultInfo.entryPoint.fpFastMathFlags;\n\tkey.isPositionInvariant = shaderConversionResultInfo.isPositionInvariant;\n\n\t/* MADEIRA_IPAD_DISK_CACHE_SPLIT_V1: disk-only mode deliberately bypasses\n\t * mvkDTRGetMSLLibraryCacheEntry(). This prevents the global unordered_map\n\t * from retaining every MTLLibrary while still allowing an on-disk metallib\n\t * hit or a source dump after an ordinary in-process compile. Concurrent\n\t * misses may compile the same MSL more than once; that is an intentional\n\t * memory-for-CPU tradeoff for the 8 GB iPad baseline. */\n\tif ( !processCacheEnabled ) {\n\t\tif (diskCacheEnabled) {\n\t\t\tid<MTLLibrary> diskLib = mvkDTRLoadMSLLibraryFromDisk(mtlDevice, key, compileNanos);\n\t\t\tif (diskLib) {\n\t\t\t\tdiskCacheHit = true;\n\t\t\t\treturn diskLib;\n\t\t\t}\n\t\t}\n\n\t\tuint64_t start = mvkGetTimestamp();\n\t\tid<MTLLibrary> lib = slc->newMTLLibrary(nsSrc, shaderConversionResultInfo, macroDef);\n\t\tcompileNanos = mvkGetElapsedNanoseconds(start);\n\t\tif (lib && diskCacheEnabled) { mvkDTRDumpMSLLibraryDiskCacheSource(key, msl, compileNanos); }\n\t\treturn lib;\n\t}\n\n\tbool shouldCompile = false;'''


def patch_text(text: str) -> str:
    if PATCH_MARKER in text:
        # A source tree can be reused between builds. Accept an already-patched
        # checkout only if both halves of the contract are present.
        required = (
            'MVK_DTR_MSL_LIBRARY_DISK_CACHE',
            'if ( !processCacheEnabled )',
            'mvkDTRLoadMSLLibraryFromDisk(mtlDevice, key, compileNanos)',
            'mvkDTRDumpMSLLibraryDiskCacheSource(key, msl, compileNanos)',
        )
        missing = [needle for needle in required if needle not in text]
        if missing:
            raise ValueError(f"partial/stale Madeira cache patch: missing {missing}")
        return text

    if text.count(OLD_DISK_SWITCH) != 1:
        raise ValueError("Release003 disk-cache switch anchor missing or ambiguous")
    if text.count(KEY_END) != 1:
        raise ValueError("Release003 shader-cache flow anchor missing or ambiguous")

    text = text.replace(OLD_DISK_SWITCH, NEW_DISK_SWITCH, 1)
    text = text.replace(KEY_END, LOW_MEMORY_BRANCH, 1)
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=pathlib.Path)
    args = ap.parse_args()

    original = args.source.read_text(encoding="utf-8")
    try:
        patched = patch_text(original)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if patched != original:
        args.source.write_text(patched, encoding="utf-8")
        print(f"patched Detroit MoltenVK iPad disk-cache split: {args.source}")
    else:
        print(f"Detroit MoltenVK iPad disk-cache split already present: {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
