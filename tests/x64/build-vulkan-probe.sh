#!/bin/bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
SRC="$HERE/vulkan_probe.c"
COMPUTE_SRC="$HERE/vulkan_compute_writeback_probe.c"
PATCHER="$HERE/patch-detroit-descriptor-features.py"
COMPUTE_PATCHER="$HERE/patch-compute-writeback-portability.py"
TMP_ROOT="${TMPDIR:-/tmp}"
PATCHED_SRC="$TMP_ROOT/madeira-detroit-vulkan-probe-patched.c"
PATCHED_COMPUTE_SRC="$TMP_ROOT/madeira-detroit-vulkan-compute-writeback-patched.c"
CAP_OBJ="$TMP_ROOT/madeira-detroit-vulkan-probe.o"
COMPUTE_OBJ="$TMP_ROOT/madeira-detroit-vulkan-compute-writeback.o"
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
if [ ! -f "$PATCHER" ]; then
    echo "error: Detroit descriptor feature patcher is missing: $PATCHER" >&2
    exit 4
fi
if [ ! -f "$COMPUTE_SRC" ]; then
    echo "error: Detroit compute writeback canary source is missing: $COMPUTE_SRC" >&2
    exit 5
fi
if [ ! -f "$COMPUTE_PATCHER" ]; then
    echo "error: Detroit compute portability patcher is missing: $COMPUTE_PATCHER" >&2
    exit 6
fi

python3 "$PATCHER" "$SRC" "$PATCHED_SRC"
python3 "$COMPUTE_PATCHER" "$COMPUTE_SRC" "$PATCHED_COMPUTE_SRC"

echo "=== Madeira Windows x64 Detroit capability probe ==="
echo "compiler: $CC"
echo "headers:  $VK_INCLUDE"
echo "source:   $PATCHED_SRC"
echo "compute:  $PATCHED_COMPUTE_SRC"
echo "output:   $OUT"

COMMON_FLAGS=(
    -std=c11 -O2 -g
    -Wall -Wextra -Werror -Wno-cast-function-type
    -I"$VK_INCLUDE"
)

# Build the renderer-capability half and the compute data-integrity half as
# separate objects, then link them into ONE trusted x64 canary. Renaming only the
# compute source's main() keeps the physical iPad launch surface fixed: the
# existing vulkan_probe.exe cannot report DETROIT_CAPABILITIES=PASS until the
# linked compute write/readback function also succeeds.
"$CC" "${COMMON_FLAGS[@]}" -c "$PATCHED_SRC" -o "$CAP_OBJ"
"$CC" "${COMMON_FLAGS[@]}" -Dmain=madeira_compute_writeback_main \
    -c "$PATCHED_COMPUTE_SRC" -o "$COMPUTE_OBJ"
"$CC" -o "$OUT" "$CAP_OBJ" "$COMPUTE_OBJ" -lkernel32

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

echo "PASS: Detroit Vulkan capability + compute-integrity probe built"
echo "Physical success requires renderer features AND exact compute storage-buffer writeback."
