#!/bin/bash
# Build a tiny x86_64 PE for testing FEX on iOS.
# Usage: ./build.sh fib
#        ./build.sh sims4-launcher-canary
set -eu

NAME="${1:-fib}"
DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$DIR/../.." && pwd)"
TOOLCHAIN="${TOOLCHAIN:-$REPO_ROOT/toolchains/llvm-mingw-20260421-ucrt-macos-universal/bin}"
APP_BUNDLE="${APP_BUNDLE:-$REPO_ROOT/app/Madeira/arm64ec-windows}"
CC="$TOOLCHAIN/x86_64-w64-mingw32-clang"
OBJDUMP="$TOOLCHAIN/x86_64-w64-mingw32-objdump"

[ -f "$DIR/$NAME.c" ] || { echo "missing $DIR/$NAME.c" >&2; exit 2; }
[ -x "$CC" ] || { echo "missing llvm-mingw x64 compiler: $CC" >&2; exit 2; }

LIBS=(-lkernel32)
case "$NAME" in
    sims4-launcher-canary)
        # uuid provides COM interface IIDs; dwrite proves Arial resolution before EA CEF.
        LIBS+=( -lole32 -loleaut32 -luuid -ldwrite -lws2_32 -lwinhttp -ladvapi32 )
        ;;
esac

cd "$DIR"

echo "=== building $NAME.exe (x86_64 PE) ==="
"$CC" -O2 -g -Wall -Wextra -Werror=implicit-function-declaration \
    -o "$NAME.exe" "$NAME.c" "${LIBS[@]}"

ls -la "$NAME.exe"

echo ""
echo "=== copying $NAME.exe to app bundle ==="
mkdir -p "$APP_BUNDLE"
cp "$NAME.exe" "$APP_BUNDLE/$NAME.exe"
ls -la "$APP_BUNDLE/$NAME.exe"

echo ""
echo "=== sha256 ==="
if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$NAME.exe" "$APP_BUNDLE/$NAME.exe"
else
    sha256sum "$NAME.exe" "$APP_BUNDLE/$NAME.exe"
fi

echo ""
echo "=== PE/import sanity ==="
if [ -x "$OBJDUMP" ]; then
    "$OBJDUMP" -f "$NAME.exe" | head -12
    "$OBJDUMP" -p "$NAME.exe" 2>&1 \
        | grep -E "DLL Name:|DWriteCreateFactory|IsNetworkAlive|WinHttp|OpenSCManager|CoCreateInstance" \
        | head -100 || true
fi

echo ""
echo "=== entry/main symbols ==="
if [ -x "$OBJDUMP" ]; then
    "$OBJDUMP" --syms "$NAME.exe" 2>&1 \
        | grep -E "_main|main$|mainCRTStartup|WinMainCRTStartup" | head -5 || true
fi

echo ""
echo "Done. Add $NAME.exe as a Madeira library entry or select it in the developer launcher."
