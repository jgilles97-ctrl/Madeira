#!/bin/bash
# Build/package Wine's ARM64EC winegstreamer PE half for 64-bit games.
#
# Madeira's iOS-native unix side already supplies decoding through FFmpeg,
# VideoToolbox and AudioToolbox. 64-bit games need this PE module present and
# MADEIRA_WG_64BIT=1 to opt into that unix side.
set -euo pipefail
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TC="$R/toolchains/llvm-mingw-20260421-ucrt-macos-universal/bin"
B="$R/wine/build-arm64ec"
OUT="$R/app/Madeira/arm64ec-windows/winegstreamer.dll"

if [[ ! -x "$TC/arm64ec-w64-mingw32-clang" ]]; then
    echo "Missing llvm-mingw ARM64EC toolchain: $TC" >&2
    echo "See docs/BUILDING.md." >&2
    exit 2
fi
export PATH="$TC:$PATH"

if [[ ! -f "$B/config.status" ]]; then
    mkdir -p "$B"
    (
        cd "$B"
        ../configure --enable-archs=arm64ec --without-x --disable-tests --enable-winegstreamer
    )
fi

# Do not use make -C dlls/winegstreamer: that also asks for the unavailable
# GStreamer unix .so. Madeira supplies the unix-call implementation itself.
make -C "$B" dlls/winegstreamer/arm64ec-windows/winegstreamer.dll

SRC="$B/dlls/winegstreamer/arm64ec-windows/winegstreamer.dll"
[[ -s "$SRC" ]] || { echo "winegstreamer build did not produce $SRC" >&2; exit 3; }
cp "$SRC" "$OUT"

python3 - "$OUT" <<'PY'
import struct, sys
p = sys.argv[1]
d = open(p, "rb").read(0x1000)
if len(d) < 0x40 or d[:2] != b"MZ":
    raise SystemExit("not a PE file: " + p)
pe = struct.unpack_from("<I", d, 0x3c)[0]
if d[pe:pe + 4] != b"PE\0\0":
    raise SystemExit("bad PE signature: " + p)
machine = struct.unpack_from("<H", d, pe + 4)[0]
# A final ARM64EC image is intentionally identified as AMD64 (0x8664) plus
# ARM64X/CHPE metadata. 0xA641 is the intermediate COFF object identifier.
if machine not in (0x8664, 0xAA64):
    raise SystemExit("unexpected final PE machine %#x; expected AMD64/ARM64 hybrid image" % machine)
print("winegstreamer PE header:", p, "machine=%#x" % machine)
PY

READOBJ="$TC/llvm-readobj"
[[ -x "$READOBJ" ]] || { echo "Missing llvm-readobj in $TC" >&2; exit 4; }
CHPE="$("$READOBJ" --coff-load-config "$OUT" 2>/dev/null || true)"
if ! grep -q 'CHPEMetadata' <<<"$CHPE"; then
    echo "winegstreamer lacks ARM64EC/ARM64X CHPE metadata" >&2
    printf '%s\n' "$CHPE" >&2
    exit 5
fi
echo "winegstreamer ARM64EC/ARM64X metadata verified"

echo "64-bit media remains opt-in. For a test session set: env.MADEIRA_WG_64BIT = 1"
