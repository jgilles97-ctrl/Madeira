#!/bin/bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
SRC="$HERE/vulkan_probe.c"
OUT="${VULKAN_PROBE_OUT:-$HERE/vulkan_probe.exe}"
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

echo "=== Madeira Windows x64 Vulkan probe ==="
echo "compiler: $CC"
echo "headers:  $VK_INCLUDE"
echo "output:   $OUT"

# Windows GetProcAddress returns FARPROC, while Vulkan exposes exact PFN_vk*
# types. Casting that ABI-compatible Windows function pointer is required for a
# dynamically loaded Vulkan canary, but MinGW GCC diagnoses the standard idiom
# as -Wcast-function-type. Keep every other warning fatal and suppress only that
# one portability diagnostic.
"$CC" \
    -std=c11 -O2 -g \
    -Wall -Wextra -Werror -Wno-cast-function-type \
    -I"$VK_INCLUDE" \
    -o "$OUT" "$SRC" \
    -lkernel32

# Keep deployment explicit: building a probe must never silently overwrite a
# game or app-bundle file. TEST_BUNDLE_DIR is opt-in.
if [ -n "${TEST_BUNDLE_DIR:-}" ]; then
    mkdir -p "$TEST_BUNDLE_DIR"
    cp -f "$OUT" "$TEST_BUNDLE_DIR/vulkan_probe.exe"
    echo "copied:   $TEST_BUNDLE_DIR/vulkan_probe.exe"
fi

if command -v file >/dev/null 2>&1; then
    file "$OUT"
fi

echo "PASS: Vulkan probe built"
echo "Run it through Madeira/FEX/Wine. A successful headless bridge ends with RESULT=PASS."