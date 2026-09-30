#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${JITSERVER_DIR:-$ROOT/../jitserver}"
REPO="https://github.com/CelloSerenity/JITserver.git"
command -v cargo >/dev/null 2>&1 || { echo "Rust is required: brew install rust" >&2; exit 2; }
if ! command -v idevice_id >/dev/null 2>&1; then
  echo "Install the USB transport first: brew install libimobiledevice" >&2
  exit 2
fi
if ! idevice_id -l | grep -q .; then
  echo "No paired iOS device found. Connect the iPad by USB and trust this Mac." >&2
  exit 3
fi

# CoreDevice's tunnel is required by iOS 26+ devices even when the USB
# pairing itself is valid.  Print the state up front so a failed JIT attempt
# has an actionable diagnosis instead of looking like a no-op.
if command -v xcrun >/dev/null 2>&1; then
  DEVICE_ID="${MADEIRA_DEVICE_ID:-$(idevice_id -l | head -n 1)}"
  echo "Checking CoreDevice tunnel for $DEVICE_ID..."
  DEVICE_INFO="$(xcrun devicectl device info details --device "$DEVICE_ID" 2>&1 || true)"
  if ! grep -q 'Tunnel IP Address:' <<<"$DEVICE_INFO"; then
    echo "No CoreDevice tunnel is available. Keep the iPad wired, unlock it, and retry." >&2
    echo "$DEVICE_INFO" >&2
    exit 5
  fi
  grep -E 'OS Version:|Developer Mode Status:|Tunnel IP Address:|Tunnel Transport Protocol:|Pairing State:' <<<"$DEVICE_INFO" || true
fi

if [ ! -d "$DEST/.git" ]; then git clone "$REPO" "$DEST"; fi
git -C "$DEST" pull --ff-only

# JITserver attaches before evaluating scripts. Madeira's in-app StikDebug
# script normally attaches itself, so make a host-side copy that skips the
# duplicate vAttach which returns E96 on iOS 27.
cp "$ROOT/app/Madeira/madeira-jit.js" "$DEST/scripts/madeira-jit.js"
sed -i '' 's/let attachResponse = send_command(`vAttach;${pid.toString(16)}`);/let attachResponse = "already-attached";/' "$DEST/scripts/madeira-jit.js"
if grep -Fq 'send_command(`vAttach;${pid.toString(16)}`)' "$DEST/scripts/madeira-jit.js"; then
  echo "Failed to prepare the JITserver attach-safe Madeira script" >&2
  exit 4
fi

cargo build --release --manifest-path "$DEST/Cargo.toml"
echo "JITserver built at $DEST/target/release/JITserver"
