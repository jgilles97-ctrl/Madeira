#!/usr/bin/env bash
set -euo pipefail

# Build and optionally install a signed arm64 device build. Xcode's GUI must
# have downloaded the manual development profile before invoking this script.
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEAM_ID="${MADEIRA_TEAM_ID:-8Y3L2GWAY4}"
BUNDLE_ID="${MADEIRA_BUNDLE_ID:-com.localcodexpad.app}"
DEVICE_ID="${MADEIRA_DEVICE_ID:-}"
DERIVED_DATA="${MADEIRA_DERIVED_DATA:-$ROOT_DIR/../DerivedData/Device}"

if [[ -z "$DEVICE_ID" ]]; then
  echo "Set MADEIRA_DEVICE_ID to the connected iPad UDID." >&2
  exit 2
fi

cd "$ROOT_DIR"
xcodebuild \
  -project app/Madeira.xcodeproj \
  -scheme Madeira \
  -configuration Release \
  -destination "id=$DEVICE_ID" \
  -derivedDataPath "$DERIVED_DATA" \
  CODE_SIGNING_ALLOWED=YES \
  CODE_SIGNING_REQUIRED=YES \
  DEVELOPMENT_TEAM="$TEAM_ID" \
  PRODUCT_BUNDLE_IDENTIFIER="$BUNDLE_ID" \
  build

APP_PATH="$DERIVED_DATA/Build/Products/Release-iphoneos/Madeira.app"
"$ROOT_DIR/build/verify-house-party.sh" "$APP_PATH"
"$ROOT_DIR/build/check-jit-entitlements.sh" "$APP_PATH"
xcrun devicectl device install app --device "$DEVICE_ID" "$APP_PATH"

echo "Installed $BUNDLE_ID on $DEVICE_ID"

# Optional post-install smoke launch. Leave unset for the normal launch-screen
# workflow; for the House Party smoke test use:
#   MADEIRA_LAUNCH_ARGS=-house-party-autostart build/ios-device.sh
if [[ -n "${MADEIRA_LAUNCH_ARGS:-}" ]]; then
  read -r -a LAUNCH_ARGS <<< "$MADEIRA_LAUNCH_ARGS"
  xcrun devicectl device process launch \
    --device "$DEVICE_ID" \
    "$BUNDLE_ID" -- "${LAUNCH_ARGS[@]}"
  echo "Launched $BUNDLE_ID with: $MADEIRA_LAUNCH_ARGS"
fi
