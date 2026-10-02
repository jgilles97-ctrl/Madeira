#!/bin/bash
# Safe House Party <-> Madeira app-container transfer helper for a physical iPad.
# It never modifies the owned source tree and never uses devicectl
# --remove-existing-content. Stage refuses to overwrite an existing destination.
set -euo pipefail

MODE="${1:-probe}"; shift || true
BUNDLE_ID="${MADEIRA_BUNDLE_ID:-com.willfaust.madeora}"
DEVICE="${MADEIRA_DEVICE_ID:-}"
SOURCE="${HOUSE_PARTY_SOURCE_DIR:-}"
REMOTE="${HOUSE_PARTY_REMOTE_DIR:-Documents/wine/drive_c/Games/HouseParty}"
OUT="${HOUSE_PARTY_DEVICE_RESULTS:-$HOME/Library/Application Support/Cenluma/HousePartyPort/device-results}"

usage() {
  echo "usage: $0 probe|stage|pull-logs [--device ID] [--source DIR] [--bundle-id ID] [--out DIR]"
}
while (($#)); do
  case "$1" in
    --device) DEVICE="${2:?}"; shift 2;;
    --source) SOURCE="${2:?}"; shift 2;;
    --bundle-id) BUNDLE_ID="${2:?}"; shift 2;;
    --out) OUT="${2:?}"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2;;
  esac
done

command -v xcrun >/dev/null || { echo "Xcode/xcrun is required." >&2; exit 3; }
if [[ -z "$DEVICE" ]]; then
  # JSON is preferred on Xcode 27; fall back to the human list only when needed.
  DEVICE="$(xcrun devicectl list devices --json-output - 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); xs=d.get("result",{}).get("devices",[]); print(next((x.get("identifier","") for x in xs if x.get("identifier")), ""))' 2>/dev/null || true)"
  [[ -n "$DEVICE" ]] || DEVICE="$(xcrun devicectl list devices 2>/dev/null | awk 'NR>1 && NF {print $NF; exit}')"
fi
[[ -n "$DEVICE" ]] || { echo "No CoreDevice device found. Set MADEIRA_DEVICE_ID." >&2; exit 4; }

info() {
  xcrun devicectl device info files --device "$DEVICE" \
    --domain-type appDataContainer --domain-identifier "$BUNDLE_ID" \
    --subdirectory "${1:-Documents}"
}

case "$MODE" in
  probe)
    echo "Device: $DEVICE"
    echo "Bundle: $BUNDLE_ID"
    xcrun devicectl device info details --device "$DEVICE" | grep -E 'OS Version:|Developer Mode Status:|Pairing State:|Tunnel IP Address:|Tunnel Transport Protocol:' || true
    echo "--- Madeira Documents ---"
    info Documents || true
    ;;
  stage)
    [[ -n "$SOURCE" && -d "$SOURCE" ]] || { echo "Set --source or HOUSE_PARTY_SOURCE_DIR to the derived owned game directory." >&2; exit 5; }
    SOURCE="$(cd "$SOURCE" && pwd)"
    [[ -f "$SOURCE/HouseParty.exe" ]] || { echo "HouseParty.exe missing from source root: $SOURCE" >&2; exit 5; }
    # Prove the local source is only read during this operation.
    BEFORE="$(find "$SOURCE" -type f -print0 | sort -z | xargs -0 stat -f '%N|%z|%m' | shasum -a 256 | awk '{print $1}')"
    parent="${REMOTE%/*}"; leaf="${REMOTE##*/}"
    listing="$(info "$parent" 2>&1 || true)"
    if grep -Fq "$leaf" <<<"$listing"; then
      echo "Refusing to overwrite existing device destination: $REMOTE" >&2
      echo "Preserve/rename it in Madeira first; this helper never deletes app-container data." >&2
      exit 6
    fi
    echo "Copying derived owned game tree to $BUNDLE_ID:$REMOTE"
    xcrun devicectl device copy to --device "$DEVICE" \
      --domain-type appDataContainer --domain-identifier "$BUNDLE_ID" \
      --source "$SOURCE" --destination "$REMOTE"
    AFTER="$(find "$SOURCE" -type f -print0 | sort -z | xargs -0 stat -f '%N|%z|%m' | shasum -a 256 | awk '{print $1}')"
    [[ "$BEFORE" == "$AFTER" ]] || { echo "Source metadata changed during staging; stop and inspect." >&2; exit 7; }
    echo "PASS: source tree metadata unchanged; staged without remote deletion."
    ;;
  pull-logs)
    mkdir -p "$OUT"
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    dir="$OUT/$stamp"; mkdir -p "$dir"
    for name in madeira-log.txt madeira-log.prev.txt madeira.cfg madeira-library.json; do
      xcrun devicectl device copy from --device "$DEVICE" \
        --domain-type appDataContainer --domain-identifier "$BUNDLE_ID" \
        --source "Documents/$name" --destination "$dir/$name" >/dev/null 2>&1 || true
    done
    if [[ -s "$dir/madeira-log.txt" ]]; then
      python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/tools/madeira_log_triage.py" "$dir/madeira-log.txt" \
        --json "$dir/triage.json" --text "$dir/triage.txt" || true
    fi
    echo "$dir"
    ;;
  *) usage >&2; exit 2;;
esac
