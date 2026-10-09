#!/bin/bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
SRC="$HERE/vulkan_wsi_probe.c"
OUT="${VULKAN_WSI_PROBE_OUT:-$HERE/vulkan_wsi_probe.exe}"
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
    local candidate
    candidate="$(find "$REPO_ROOT/toolchains" -type f -path '*/bin/x86_64-w64-mingw32-clang' -perm -111 -print 2>/dev/null | head -n 1 || true)"
    if [ -n "$candidate" ]; then
        printf '%s\n' "$candidate"
        return 0
    fi
    return 1
}

CC="$(find_cc || true)"
if [ -z "$CC" ]; then
    echo "error: x86_64-w64-mingw32-clang was not found" >&2
    echo "set X86_64_W64_MINGW32_CLANG=/path/to/x86_64-w64-mingw32-clang" >&2
    exit 2
fi

if [ ! -f "$VK_INCLUDE/vulkan/vulkan.h" ]; then
    echo "error: Vulkan headers were not found at $VK_INCLUDE" >&2
    echo "run build/moltenvk-ios/build.sh first, or set VULKAN_HEADERS=/path/to/include" >&2
    exit 3
fi

echo "=== Madeira Windows x64 Vulkan WSI probe ==="
echo "compiler: $CC"
echo "headers:  $VK_INCLUDE"
echo "output:   $OUT"

"$CC" \
    -std=c11 -O2 -g \
    -Wall -Wextra -Werror \
    -I"$VK_INCLUDE" \
    -o "$OUT" "$SRC" \
    -lkernel32 -luser32

if [ -n "${TEST_BUNDLE_DIR:-}" ]; then
    mkdir -p "$TEST_BUNDLE_DIR"
    cp -f "$OUT" "$TEST_BUNDLE_DIR/vulkan_wsi_probe.exe"
    echo "copied:   $TEST_BUNDLE_DIR/vulkan_wsi_probe.exe"
fi

if command -v file >/dev/null 2>&1; then
    file "$OUT"
fi

echo "PASS: Vulkan WSI probe built"
echo "A device PASS proves a Win32 Vulkan surface reaches an iPad-presentable Metal surface."
