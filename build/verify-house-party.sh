#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_PATH="${1:-$ROOT_DIR/../DerivedData/Unsigned/Build/Products/Release-iphoneos/Madeira.app}"

[[ -d "$APP_PATH" ]] || { echo "Missing app: $APP_PATH" >&2; exit 2; }

"$ROOT_DIR/build/check-house-party-inputs.sh"

BIN="$APP_PATH/Madeira"
[[ "$(file -b "$BIN")" == *"arm64"* ]] || { echo "Madeira binary is not arm64" >&2; exit 1; }

for required in \
  "aarch64-windows/ntdll.dll" \
  "aarch64-windows/win32u.dll" \
  "arm64ec-windows/win32u.dll" \
  "prefix-template.tar.gz"; do
  [[ -f "$APP_PATH/$required" ]] || { echo "Missing runtime asset: $required" >&2; exit 1; }
done

pe_count=$(find "$APP_PATH/aarch64-windows" "$APP_PATH/arm64ec-windows" \
  -type f \( -name '*.dll' -o -name '*.exe' \) | wc -l | tr -d ' ')
(( pe_count >= 100 )) || { echo "Unexpectedly small PE runtime: $pe_count files" >&2; exit 1; }

plutil -extract UISupportedInterfaceOrientations~ipad xml1 -o - "$APP_PATH/Info.plist" >/dev/null
echo "House Party iPad artifact verified: $APP_PATH"
