#!/bin/bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
SRC="$HERE/vulkan_compute_writeback_probe.c"
PATCHER="$HERE/patch-compute-writeback-portability.py"
PATCHED_SRC="${TMPDIR:-/tmp}/madeira-detroit-vulkan-compute-writeback-standalone.c"
OUT="${VULKAN_COMPUTE_WRITEBACK_PROBE_OUT:-$HERE/vulkan_compute_writeback_probe.exe}"
VK_INCLUDE="${VULKAN_HEADERS:-$REPO_ROOT/toolchains/moltenvk-detroit-ios/include}"

find_cc() {
    if [ -n "${X86_64_W64_MINGW32_CLANG:-}" ] && [ -x "${X86_64_W64_MINGW32_CLANG}" ]; then
        printf '%s\n' "$X86_64_W64_MINGW32_CLANG"
        return 0
    fi
    if command -v x86_64-w64-mingw32-clang >/dev/null 2>&1; then
        command -v x86_64-w64-mingw32-clang
        return 0
    fi
    if command -v x86_64-w64-mingw32-gcc >/dev/null 2>&1; then
        command -v x86_64-w64-mingw32-gcc
        return 0
    fi
    local candidate
    candidate="$(find "$REPO_ROOT/toolchains" -type f \( -name 'x86_64-w64-mingw32-clang' -o -name 'x86_64-w64-mingw32-gcc' \) -perm -111 -print 2>/dev/null | head -n 1 || true)"
    if [ -n "$candidate" ]; then
        printf '%s\n' "$candidate"
        return 0
    fi
    return 1
}

CC="$(find_cc || true)"
if [ -z "$CC" ]; then
    echo "error: no x86_64 MinGW compiler was found" >&2
    exit 2
fi
if [ ! -f "$VK_INCLUDE/vulkan/vulkan.h" ]; then
    echo "error: Vulkan headers were not found at $VK_INCLUDE" >&2
    exit 3
fi
if [ ! -f "$PATCHER" ]; then
    echo "error: compute portability patcher missing: $PATCHER" >&2
    exit 4
fi

python3 "$PATCHER" "$SRC" "$PATCHED_SRC"

echo "=== Madeira Detroit compute writeback probe ==="
echo "compiler: $CC"
echo "headers:  $VK_INCLUDE"
echo "source:   $PATCHED_SRC"
echo "output:   $OUT"

"$CC" \
    -std=c11 -O2 -g \
    -Wall -Wextra -Werror -Wno-cast-function-type \
    -I"$VK_INCLUDE" \
    -o "$OUT" "$PATCHED_SRC" \
    -lkernel32

if [ -n "${TEST_BUNDLE_DIR:-}" ]; then
    mkdir -p "$TEST_BUNDLE_DIR"
    cp -f "$OUT" "$TEST_BUNDLE_DIR/vulkan_compute_writeback_probe.exe"
    echo "copied:   $TEST_BUNDLE_DIR/vulkan_compute_writeback_probe.exe"
fi

if command -v file >/dev/null 2>&1; then
    file "$OUT"
fi

echo "PASS: Detroit compute writeback probe built"
echo "Physical PASS requires MOLTENVK_ARGUMENT_BUFFER_COMPUTE_INTEGRITY=PASS."
