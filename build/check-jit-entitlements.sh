#!/usr/bin/env bash
set -euo pipefail

APP="${1:-$(cd "$(dirname "$0")/.." && pwd)/../DerivedData/Device/Build/Products/Release-iphoneos/Madeira.app}"
if [[ ! -d "$APP" || ! -x "$APP/Madeira" ]]; then
  echo "JIT entitlement check: app not found: $APP" >&2
  exit 2
fi

SIGNED="$(codesign -d --entitlements :- "$APP" 2>/dev/null || true)"
PROFILE="$(security cms -D -i "$APP/embedded.mobileprovision" 2>/dev/null || true)"

has_signed_jit=0
grep -q 'com.apple.security.cs.allow-jit' <<<"$SIGNED" && has_signed_jit=1
has_debug=0
grep -q '<key>get-task-allow</key><true/>' <<<"$SIGNED" && has_debug=1

echo "JIT entitlement check: $(basename "$APP")"
echo "  get-task-allow: $([[ $has_debug -eq 1 ]] && echo granted || echo missing)"
echo "  com.apple.security.cs.allow-jit: $([[ $has_signed_jit -eq 1 ]] && echo granted || echo not-granted-by-profile)"

if [[ $has_debug -ne 1 ]]; then
  echo "JIT entitlement check failed: development debugger entitlement is absent." >&2
  exit 3
fi
if [[ $has_signed_jit -eq 0 ]]; then
  echo "JIT entitlement check: profile-backed JIT entitlement unavailable; use JITserver/StikDebug debugger attach." >&2
fi
[[ -n "$PROFILE" ]] || echo "JIT entitlement check: embedded provisioning profile could not be decoded." >&2
