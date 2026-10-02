#!/bin/bash
# One-command, read-only-source House Party Mac advance cycle.
# Finds the known owned build/archive, fingerprints it, probes GPTK/Metal,
# then runs isolated CrossOver backend smoke tests. Sources stay untouched.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE="${HOUSE_PARTY_PORT_ROOT:-$HOME/Library/Application Support/Cenluma/HousePartyPort}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RESULTS="${HOUSE_PARTY_RESULTS:-$BASE/results/$STAMP}"
SOURCE="${HOUSE_PARTY_SOURCE_DIR:-}"
ARCHIVE="${HOUSE_PARTY_ARCHIVE:-}"
SECONDS="${HOUSE_PARTY_SMOKE_SECONDS:-45}"
mkdir -p "$RESULTS" "$BASE/staging"

log() { printf '[house-party-cycle] %s\n' "$*"; }

find_source_root() {
  local base="$1" exe
  exe="$(find "$base" -maxdepth 4 -type f -iname 'HouseParty.exe' -print -quit 2>/dev/null || true)"
  [[ -n "$exe" ]] || return 1
  dirname "$exe"
}

if [[ -z "$SOURCE" ]]; then
  for d in \
    "$HOME/Games/HouseParty" \
    "$HOME/CenlumaPorts/staging/HouseParty" \
    "$BASE/staging/owned-build"; do
    if [[ -d "$d" ]] && find "$d" -maxdepth 4 -type f -iname 'HouseParty.exe' -print -quit | grep -q .; then
      SOURCE="$(find_source_root "$d")"
      break
    fi
  done
fi

if [[ -z "$SOURCE" && -z "$ARCHIVE" ]]; then
  for a in \
    "$HOME/.joey-local/projects/house-party-ipad/incoming/House-Party-AnkerGames.zip" \
    "$HOME/Downloads/House-Party-AnkerGames.zip"; do
    if [[ -f "$a" ]]; then ARCHIVE="$a"; break; fi
  done
fi

ARCHIVE_HASH=""
if [[ -z "$SOURCE" && -n "$ARCHIVE" ]]; then
  [[ -f "$ARCHIVE" ]] || { echo "Owned archive not found: $ARCHIVE" >&2; exit 2; }
  ARCHIVE_HASH="$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')"
  DEST="$BASE/staging/owned-build-${ARCHIVE_HASH:0:12}"
  MARKER="$DEST/.source-sha256"
  if [[ ! -f "$MARKER" || "$(cat "$MARKER" 2>/dev/null || true)" != "$ARCHIVE_HASH" ]]; then
    log "extracting owned archive into derived staging: $DEST"
    rm -rf "$DEST.tmp"
    mkdir -p "$DEST.tmp"
    ditto -x -k "$ARCHIVE" "$DEST.tmp"
    printf '%s\n' "$ARCHIVE_HASH" > "$DEST.tmp/.source-sha256"
    rm -rf "$DEST"
    mv "$DEST.tmp" "$DEST"
  else
    log "reusing derived extraction: $DEST"
  fi
  SOURCE="$(find_source_root "$DEST" || true)"
fi

[[ -n "$SOURCE" && -d "$SOURCE" ]] || {
  echo "Could not find HouseParty.exe. Set HOUSE_PARTY_SOURCE_DIR or HOUSE_PARTY_ARCHIVE." >&2
  exit 3
}
SOURCE="$(cd "$SOURCE" && pwd)"
EXE="$SOURCE/HouseParty.exe"
[[ -f "$EXE" ]] || EXE="$(find "$SOURCE" -maxdepth 2 -type f -iname 'HouseParty.exe' -print -quit)"
[[ -f "$EXE" ]] || { echo "HouseParty.exe missing under $SOURCE" >&2; exit 3; }

log "source (read-only input): $SOURCE"
log "results: $RESULTS"

python3 "$ROOT/tools/house-party/fingerprint.py" "$SOURCE" -o "$RESULTS/compatibility-manifest.json"
python3 "$ROOT/tools/house-party/reconstruction-feasibility.py" "$RESULTS/compatibility-manifest.json" -o "$RESULTS/reconstruction-feasibility.json"

bash "$ROOT/tools/house-party/check-gptk4.sh" >"$RESULTS/gptk4-environment.txt" 2>&1 || true

bash "$ROOT/tools/house-party/mac-crossover-smoke.sh" \
  --source "$SOURCE" \
  --results "$RESULTS/crossover" \
  --seconds "$SECONDS" \
  --backend all

REPO_SHA="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
SOURCE_EXE_HASH="$(shasum -a 256 "$EXE" | awk '{print $1}')"
SOURCE="$SOURCE" ARCHIVE="${ARCHIVE:-}" ARCHIVE_HASH="$ARCHIVE_HASH" \
SOURCE_EXE_HASH="$SOURCE_EXE_HASH" RESULTS="$RESULTS" REPO_SHA="$REPO_SHA" \
python3 - <<'PY'
import json, os
from pathlib import Path
root = Path(os.environ["RESULTS"])
matrix_path = root / "crossover/matrix.json"
matrix = json.loads(matrix_path.read_text()) if matrix_path.exists() else {"runs": []}
summary = {
    "schema_version": 1,
    "source_policy": "read-only",
    "source_directory": os.environ["SOURCE"],
    "source_executable_sha256": os.environ["SOURCE_EXE_HASH"],
    "archive": os.environ["ARCHIVE"] or None,
    "archive_sha256": os.environ["ARCHIVE_HASH"] or None,
    "repo_sha": os.environ["REPO_SHA"],
    "outputs": {
        "compatibility_manifest": str(root / "compatibility-manifest.json"),
        "gptk4_environment": str(root / "gptk4-environment.txt"),
        "reconstruction_feasibility": str(root / "reconstruction-feasibility.json"),
        "crossover_matrix": str(matrix_path),
    },
    "crossover": matrix,
    "validation_limit": ("Automated process survival/logging is diagnostic only. Menu, rendering, gameplay, audio/video, input and save/load require explicit runtime observation."),
}
(root / "cycle-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(root / "cycle-summary.json")
PY

log "cycle complete: $RESULTS/cycle-summary.json"
