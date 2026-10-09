#!/bin/bash
set -euo pipefail

# Build every Madeira-side layer Detroit needs for Vulkan on a real iOS device.
# This does NOT copy Detroit game files and does not claim device compatibility;
# it produces the runtime pieces required before the Vulkan device gate can be
# meaningful on-device.

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
FARM="$ROOT/app/Madeira/arm64ec-windows"
OUT_DIR="${DETROIT_VULKAN_OUT:-${TMPDIR:-/tmp}/madeira-detroit-vulkan}"
BASELINE_MOLTENVK_COMMIT="8b511fdc5351a37c305bc246e161796ddca56b18"
EXPECTED_MOLTENVK_COMMIT="${MOLTENVK_DETROIT_EXPECTED_COMMIT:-$BASELINE_MOLTENVK_COMMIT}"
mkdir -p "$OUT_DIR"

step() { printf '\n=== %s ===\n' "$1"; }
need_file() {
    [ -f "$1" ] || { echo "error: expected output missing: $1" >&2; exit 20; }
}

# A deliberate MoltenVK experiment is allowed, but a different ref must be
# paired with the exact reviewed commit we expect it to resolve to. That keeps
# a tag/branch from silently moving underneath a supposedly reproducible test.
if [ -n "${MOLTENVK_DETROIT_REF:-}" ] && [ "$MOLTENVK_DETROIT_REF" != "$BASELINE_MOLTENVK_COMMIT" ] && \
   [ -z "${MOLTENVK_DETROIT_EXPECTED_COMMIT:-}" ]; then
    echo "error: MOLTENVK_DETROIT_REF overrides the audited Detroit baseline" >&2
    echo "set MOLTENVK_DETROIT_EXPECTED_COMMIT to the exact reviewed 40-character commit too" >&2
    exit 19
fi

step "1/6 Detroit MoltenVK for iOS"
"$ROOT/build/moltenvk-ios/build.sh"
need_file "$ROOT/toolchains/moltenvk-detroit-ios/lib/libMoltenVK.a"
need_file "$ROOT/toolchains/moltenvk-detroit-ios/include/vulkan/vulkan.h"

step "2/6 Wine win32u host Vulkan + iOS WSI"
MADEIRA_VULKAN=1 "$ROOT/build/win32u-unix/build.sh"
need_file "$ROOT/app/Madeira/libwin32u_unix.a"

step "3/6 Wine winevulkan unix side"
MADEIRA_VULKAN=1 "$ROOT/build/ntdll-unix/build.sh"
need_file "$ROOT/app/Madeira/libntdll_unix.a"

step "4/6 Windows ARM64EC Vulkan loader + ICD"
"$ROOT/build/wine-pe/build-modules.sh" vulkan-1 winevulkan
need_file "$FARM/vulkan-1.dll"
need_file "$FARM/winevulkan.dll"

step "5/6 Windows x64 real-device canaries + one-command gate"
TEST_BUNDLE_DIR="$FARM" \
VULKAN_PROBE_OUT="$OUT_DIR/vulkan_probe.exe" \
    "$ROOT/tests/x64/build-vulkan-probe.sh"
TEST_BUNDLE_DIR="$FARM" \
VULKAN_WSI_PROBE_OUT="$OUT_DIR/vulkan_wsi_probe.exe" \
    "$ROOT/tests/x64/build-vulkan-wsi-probe.sh"
TEST_BUNDLE_DIR="$FARM" \
VULKAN_SWAPCHAIN_PROBE_OUT="$OUT_DIR/vulkan_swapchain_probe.exe" \
    "$ROOT/tests/x64/build-vulkan-swapchain-probe.sh"
TEST_BUNDLE_DIR="$FARM" \
VULKAN_DEVICE_GATE_OUT="$OUT_DIR/vulkan-device-gate-x64.exe" \
    "$ROOT/tests/x64/build-vulkan-device-gate.sh"
need_file "$FARM/vulkan_probe.exe"
need_file "$FARM/vulkan_wsi_probe.exe"
need_file "$FARM/vulkan_swapchain_probe.exe"
need_file "$FARM/vulkan-device-gate-x64.exe"

step "6/6 Static payload sanity"
python3 "$ROOT/tools/detroit_vulkan_payload.py" \
    --farm "$FARM" \
    --moltenvk "$ROOT/toolchains/moltenvk-detroit-ios" \
    --expected-moltenvk-commit "$EXPECTED_MOLTENVK_COMMIT" \
    --strict

cat <<'EOF'

PASS: Detroit Vulkan runtime layers and on-device gate built.

This is a build gate, not an iPad compatibility claim.
The four x64 test executables are now copied into the Madeira ARM64EC bundle.
On the physical iPad, launch:

  MADEIRA_EXE=vulkan-device-gate-x64.exe

That one Windows/FEX/Wine process runs, in order:
  1. vulkan_probe.exe            (instance/device)
  2. vulkan_wsi_probe.exe        (Win32 surface -> Metal surface)
  3. vulkan_swapchain_probe.exe  (120 clear/present frames)

Do not move to Detroit until its log ends with:
  VULKAN_DEVICE=PASS
  WIN32_SURFACE=PASS
  PRESENTED_120_FRAMES=PASS
  OVERALL=PASS
  NEXT_GATE=detroit-process-and-shader-compilation

After that gate passes, launch Detroit itself using docs/detroit-m4-8gb.cfg.
EOF
