#!/bin/bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
SRC="$HERE/vulkan_swapchain_probe.c"
OUT="${VULKAN_SWAPCHAIN_PROBE_OUT:-$HERE/vulkan_swapchain_probe.exe}"
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
    echo "set X86_64_W64_MINGW32_CLANG=/path/to/x86_64-w64-mingw32-clang-or-gcc" >&2
    exit 2
fi

if [ ! -f "$VK_INCLUDE/vulkan/vulkan.h" ]; then
    echo "error: Vulkan headers were not found at $VK_INCLUDE" >&2
    echo "run build/moltenvk-ios/build.sh first, or set VULKAN_HEADERS=/path/to/include" >&2
    exit 3
fi

echo "=== Madeira Windows x64 Vulkan swapchain probe ==="
echo "compiler: $CC"
echo "headers:  $VK_INCLUDE"
echo "output:   $OUT"

"$CC" \
    -std=c11 -O2 -g \
    -Wall -Wextra -Werror \
    -I"$VK_INCLUDE" \
    -o "$OUT" "$SRC" \
    -lkernel32 -luser32

# Building a canary must never silently alter the app bundle. Deployment is an
# explicit opt-in so CI and local host builds remain read-only with respect to
# Madeira's runtime payload.
if [ -n "${TEST_BUNDLE_DIR:-}" ]; then
    mkdir -p "$TEST_BUNDLE_DIR"
    cp -f "$OUT" "$TEST_BUNDLE_DIR/vulkan_swapchain_probe.exe"
    echo "copied:   $TEST_BUNDLE_DIR/vulkan_swapchain_probe.exe"
fi

if command -v file >/dev/null 2>&1; then
    file "$OUT"
fi

echo "PASS: Vulkan swapchain probe built"
echo "A real iPad runtime PASS ends with CLEAR_PRESENT=PASS and RESULT=PASS."
