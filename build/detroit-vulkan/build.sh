#!/bin/bash
set -euo pipefail

# Build every Madeira-side layer Detroit needs for Vulkan on a real iOS device.
# This does NOT copy Detroit game files and does not claim device compatibility;
# it produces the runtime pieces required before the three Vulkan canaries can
# be meaningful on-device.

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
FARM="$ROOT/app/Madeira/arm64ec-windows"

step() { printf '\n=== %s ===\n' "$1"; }
need_file() {
    [ -f "$1" ] || { echo "error: expected output missing: $1" >&2; exit 20; }
}

step "1/5 Detroit MoltenVK for iOS"
"$ROOT/build/moltenvk-ios/build.sh"
need_file "$ROOT/toolchains/moltenvk-detroit-ios/lib/libMoltenVK.a"
need_file "$ROOT/toolchains/moltenvk-detroit-ios/include/vulkan/vulkan.h"

step "2/5 Wine win32u host Vulkan + iOS WSI"
MADEIRA_VULKAN=1 "$ROOT/build/win32u-unix/build.sh"
need_file "$ROOT/app/Madeira/libwin32u_unix.a"

step "3/5 Wine winevulkan unix side"
MADEIRA_VULKAN=1 "$ROOT/build/ntdll-unix/build.sh"
need_file "$ROOT/app/Madeira/libntdll_unix.a"

step "4/5 Windows ARM64EC Vulkan loader + ICD"
"$ROOT/build/wine-pe/build-modules.sh" vulkan-1 winevulkan
need_file "$FARM/vulkan-1.dll"
need_file "$FARM/winevulkan.dll"

step "5/5 Static payload sanity"
python3 "$ROOT/tools/detroit_vulkan_payload.py" \
    --farm "$FARM" \
    --moltenvk "$ROOT/toolchains/moltenvk-detroit-ios" \
    --strict

cat <<'EOF'

PASS: Detroit Vulkan runtime layers built.

This is a build gate, not an iPad compatibility claim.
Next device order:
  1. vulkan_probe.exe            (instance/device)
  2. vulkan_wsi_probe.exe        (Win32 surface -> Metal surface)
  3. vulkan_swapchain_probe.exe  (120 clear/present frames)
  4. Detroit itself, using docs/detroit-m4-8gb.cfg
EOF
