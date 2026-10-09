#!/bin/bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
SRC="$HERE/vulkan_device_gate.c"
OUT="${VULKAN_DEVICE_GATE_OUT:-$HERE/vulkan-device-gate-x64.exe}"

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
    echo "set X86_64_W64_MINGW32_CLANG=/path/to/x86_64-w64-mingw32-clang-or-gcc" >&2
    exit 2
fi

echo "=== Madeira Detroit Vulkan device gate ==="
echo "compiler: $CC"
echo "output:   $OUT"

"$CC" \
    -std=c11 -O2 -g \
    -Wall -Wextra -Werror \
    -o "$OUT" "$SRC" \
    -lkernel32

if [ -n "${TEST_BUNDLE_DIR:-}" ]; then
    mkdir -p "$TEST_BUNDLE_DIR"
    cp -f "$OUT" "$TEST_BUNDLE_DIR/vulkan-device-gate-x64.exe"
    echo "copied:   $TEST_BUNDLE_DIR/vulkan-device-gate-x64.exe"
fi

if command -v file >/dev/null 2>&1; then
    file "$OUT"
fi

echo "PASS: Detroit Vulkan device gate built"
echo "Launch with MADEIRA_EXE=vulkan-device-gate-x64.exe."
echo "Success ends with OVERALL=PASS and NEXT_GATE=detroit-process-and-shader-compilation."
