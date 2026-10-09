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
need_file "$ROOT/toolchains/moltenvk-detroit-ios/BUILD-INFO.txt"

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

# Bind physical PASS proof to the runtime that actually matters, not only to the
# Windows canaries. The ordered hash covers the staged MoltenVK archive, the two
# app-facing Wine host archives, the two guest Vulkan DLLs, and the iOS bridge/
# FEX/launcher source that sits outside those archives. The resulting ID is
# embedded into the x64 controller executable. Madeira fingerprints that
# controller, so any runtime change invalidates old physical PASS proof.
RUNTIME_INPUTS=(
    "$ROOT/toolchains/moltenvk-detroit-ios/lib/libMoltenVK.a"
    "$ROOT/app/Madeira/libwin32u_unix.a"
    "$ROOT/app/Madeira/libntdll_unix.a"
    "$FARM/vulkan-1.dll"
    "$FARM/winevulkan.dll"
    "$ROOT/app/Madeira/IOSDisplayShim.m"
    "$ROOT/app/Madeira/FEXBridge.mm"
    "$ROOT/app/Madeira/FEXBridge.h"
    "$ROOT/app/Madeira/MadeiraApp.swift"
)
for runtime_input in "${RUNTIME_INPUTS[@]}"; do
    need_file "$runtime_input"
done

DETROIT_RUNTIME_BUILD_ID="$({ python3 - "${RUNTIME_INPUTS[@]}" <<'PY'
import hashlib
import pathlib
import sys

h = hashlib.sha256()
for index, raw in enumerate(sys.argv[1:]):
    path = pathlib.Path(raw)
    size = path.stat().st_size
    h.update(index.to_bytes(4, "little"))
    h.update(size.to_bytes(8, "little"))
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
print(h.hexdigest())
PY
} )"
if [[ ! "$DETROIT_RUNTIME_BUILD_ID" =~ ^[0-9a-f]{64}$ ]]; then
    echo "error: could not derive deterministic Detroit runtime build identity" >&2
    exit 21
fi
echo "Detroit runtime build ID: $DETROIT_RUNTIME_BUILD_ID"

step "5/6 Windows x64 real-device canaries + one-command gate"
TEST_BUNDLE_DIR="$FARM" \
VULKAN_PROBE_OUT="$OUT_DIR/vulkan_probe.exe" \
    "$ROOT/tests/x64/build-vulkan-probe.sh"
TEST_BUNDLE_DIR="$FARM" \
VULKAN_COMPUTE_WRITEBACK_PROBE_OUT="$OUT_DIR/vulkan_compute_writeback_probe.exe" \
    "$ROOT/tests/x64/build-vulkan-compute-writeback-probe.sh"
TEST_BUNDLE_DIR="$FARM" \
VULKAN_WSI_PROBE_OUT="$OUT_DIR/vulkan_wsi_probe.exe" \
    "$ROOT/tests/x64/build-vulkan-wsi-probe.sh"
TEST_BUNDLE_DIR="$FARM" \
VULKAN_SWAPCHAIN_PROBE_OUT="$OUT_DIR/vulkan_swapchain_probe.exe" \
    "$ROOT/tests/x64/build-vulkan-swapchain-probe.sh"
TEST_BUNDLE_DIR="$FARM" \
DETROIT_RUNTIME_BUILD_ID="$DETROIT_RUNTIME_BUILD_ID" \
VULKAN_DEVICE_GATE_OUT="$OUT_DIR/vulkan-device-gate-x64.exe" \
    "$ROOT/tests/x64/build-vulkan-device-gate.sh"
need_file "$FARM/vulkan_probe.exe"
need_file "$FARM/vulkan_compute_writeback_probe.exe"
need_file "$FARM/vulkan_wsi_probe.exe"
need_file "$FARM/vulkan_swapchain_probe.exe"
need_file "$FARM/vulkan-device-gate-x64.exe"
if ! grep -aqF "MADEIRA_DETROIT_RUNTIME_BUILD_ID=$DETROIT_RUNTIME_BUILD_ID" "$FARM/vulkan-device-gate-x64.exe"; then
    echo "error: packaged device gate is not bound to the just-built Detroit runtime" >&2
    exit 22
fi

step "6/6 Static payload sanity"
python3 "$ROOT/tools/detroit_vulkan_payload.py" \
    --farm "$FARM" \
    --moltenvk "$ROOT/toolchains/moltenvk-detroit-ios" \
    --expected-moltenvk-commit "$EXPECTED_MOLTENVK_COMMIT" \
    --strict

cat <<EOF

PASS: Detroit Vulkan runtime layers and on-device gate built.
Runtime identity: $DETROIT_RUNTIME_BUILD_ID

This is a build gate, not an iPad compatibility claim.
The five fixed x64 test executables are now bundled with Madeira, and the gate
itself is bound to the exact local graphics/runtime inputs above.

On the physical M4 iPad, open Madeira and tap:

  Detroit graphics test

Keep Madeira in the foreground until the test finishes. A valid PASS requires:
  DETROIT_CAPABILITIES=PASS
  MOLTENVK_ARGUMENT_BUFFER_COMPUTE_INTEGRITY=PASS
  VULKAN_DEVICE=PASS
  WIN32_SURFACE=PASS
  PRESENTED_120_FRAMES=PASS
  FOREGROUND_INTEGRITY=PASS
  OVERALL=PASS
  NEXT_GATE=detroit-process-and-shader-compilation

Madeira will show "Detroit graphics test — Passed" only when proof matches the
currently installed test/runtime payload. Do not move to Detroit itself before
that current-payload physical proof is green.
EOF