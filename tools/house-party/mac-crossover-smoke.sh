#!/bin/bash
# Isolated CrossOver backend smoke matrix for a read-only House Party source.
# Writes only to derived copies and dedicated test bottles.
set -euo pipefail

SOURCE=""; RESULTS=""; SECONDS=45; BACKEND="all"; PREFIX="HouseParty-Port"
usage() {
  echo "usage: $0 --source DIR [--results DIR] [--seconds N] [--backend dxmt|d3dmetal|dxvk|wined3d|all] [--bottle-prefix NAME]"
}
while (($#)); do
  case "$1" in
    --source) SOURCE="${2:?}"; shift 2;;
    --results) RESULTS="${2:?}"; shift 2;;
    --seconds) SECONDS="${2:?}"; shift 2;;
    --backend) BACKEND="${2:?}"; shift 2;;
    --bottle-prefix) PREFIX="${2:?}"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2;;
  esac
done

[[ "$(uname -s)" == Darwin ]] || { echo "macOS required" >&2; exit 2; }
[[ -n "$SOURCE" ]] || { usage >&2; exit 2; }
SOURCE="$(cd "$SOURCE" && pwd)"
[[ -d "$SOURCE" ]] || { echo "source not found: $SOURCE" >&2; exit 2; }

CXROOT="/Applications/CrossOver.app/Contents/SharedSupport/CrossOver"
[[ -x "$CXROOT/bin/wine" ]] || CXROOT="$HOME/Applications/CrossOver.app/Contents/SharedSupport/CrossOver"
WINE="$CXROOT/bin/wine"; CXBOTTLE="$CXROOT/bin/cxbottle"; WINESERVER="$CXROOT/bin/wineserver"
[[ -x "$WINE" && -x "$CXBOTTLE" ]] || { echo "CrossOver CLI not found" >&2; exit 3; }
APP_ROOT="$(dirname "$(dirname "$(dirname "$CXROOT")")")"
CROSSOVER_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP_ROOT/Info.plist" 2>/dev/null || echo unknown)"

BOTTLE_ROOT="${CX_BOTTLE_PATH:-$HOME/Library/Application Support/CrossOver/Bottles}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RESULTS="${RESULTS:-$HOME/Library/Application Support/Cenluma/HousePartyPort/results/$STAMP}"
GAME="$RESULTS/work/game"
mkdir -p "$RESULTS" "$GAME"

# Source remains untouched: all runtime work uses this derived copy.
if [[ ! -f "$GAME/.derived-house-party-copy" ]]; then
  rsync -a "$SOURCE/" "$GAME/"
  touch "$GAME/.derived-house-party-copy"
fi
EXE="$(find "$GAME" -maxdepth 2 -type f -iname 'HouseParty.exe' -print -quit)"
[[ -n "$EXE" ]] || { echo "HouseParty.exe not found in derived copy" >&2; exit 4; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ ! -f "$SCRIPT_DIR/fingerprint.py" ]] || \
  python3 "$SCRIPT_DIR/fingerprint.py" "$GAME" -o "$RESULTS/compatibility-manifest.json"

set_env_key() {
  python3 - "$1" "$2" "$3" <<'PY'
from pathlib import Path
import re, sys
p, key, value = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
text = p.read_text(errors="replace") if p.exists() else ""
if "[EnvironmentVariables]" not in text:
    text += "\n[EnvironmentVariables]\n"
line = f'"{key}" = "{value}"'
pat = re.compile(rf'(?m)^\s*"{re.escape(key)}"\s*=.*$')
if pat.search(text):
    text = pat.sub(line, text)
else:
    pos = text.find("[EnvironmentVariables]")
    end = text.find("\n[", pos + 1)
    if end < 0: text = text.rstrip() + "\n" + line + "\n"
    else: text = text[:end].rstrip() + "\n" + line + "\n" + text[end:]
p.write_text(text)
PY
}

ensure_bottle() {
  local name="$1" dir="$BOTTLE_ROOT/$name"
  if [[ ! -d "$dir" ]]; then
    mkdir -p "$BOTTLE_ROOT"
    "$CXBOTTLE" --bottle "$name" --create --template win10_64 --install
  fi
  [[ -f "$dir/cxbottle.conf" ]] || { echo "missing $dir/cxbottle.conf" >&2; return 1; }
}
stop_bottle() {
  WINEPREFIX="$1" "$WINESERVER" -k >/dev/null 2>&1 || true
}

run_backend() {
  local backend="$1" suffix bottle dir conf log meta pid start end rc=null survived=false
  case "$backend" in
    dxmt) suffix="DXMT";;
    d3dmetal) suffix="D3DMetal";;
    dxvk) suffix="DXVK";;
    wined3d) suffix="Wine";;
    *) return 2;;
  esac
  bottle="${PREFIX}-${suffix}"; dir="$BOTTLE_ROOT/$bottle"; conf="$dir/cxbottle.conf"
  log="$RESULTS/${backend}.log"; meta="$RESULTS/${backend}.json"
  ensure_bottle "$bottle"
  cp "$conf" "$RESULTS/${backend}-cxbottle.before.conf"
  set_env_key "$conf" "CX_GRAPHICS_BACKEND" "$backend"
  set_env_key "$conf" "WINEMSYNC" "1"
  set_env_key "$conf" "WINED3DMETAL" "$([[ "$backend" == d3dmetal ]] && echo 1 || echo 0)"
  set_env_key "$conf" "WINEDXVK" "$([[ "$backend" == dxvk ]] && echo 1 || echo 0)"
  cp "$conf" "$RESULTS/${backend}-cxbottle.test.conf"

  stop_bottle "$dir"; start="$(date +%s)"
  (
    cd "$(dirname "$EXE")"
    export CX_ROOT="$CXROOT" CX_BOTTLE="$bottle"
    export CX_LOG="$log" CX_DEBUGMSG="+timestamp,+pid,+seh,+unwind,+process,+module,+loaddll"
    export DXMT_LOG_LEVEL=2
    exec "$WINE" --bottle "$bottle" "$EXE"
  ) >"$RESULTS/${backend}-wrapper.log" 2>&1 &
  pid=$!

  for ((i=0; i<SECONDS; i++)); do
    if ! kill -0 "$pid" 2>/dev/null; then
      wait "$pid" || rc=$?
      [[ "$rc" != null ]] || rc=0
      break
    fi
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    survived=true; stop_bottle "$dir"; wait "$pid" 2>/dev/null || true
  fi
  end="$(date +%s)"

  BACKEND_NAME="$backend" BOTTLE_NAME="$bottle" START="$start" END="$end" \
  SURVIVED="$survived" RC="$rc" LOG_PATH="$log" CROSSOVER_VERSION="$CROSSOVER_VERSION" python3 - "$meta" <<'PY'
import json, os, sys
d = {
 "backend": os.environ["BACKEND_NAME"], "bottle": os.environ["BOTTLE_NAME"],
 "crossover_version": os.environ["CROSSOVER_VERSION"],
 "observation_seconds": int(os.environ["END"])-int(os.environ["START"]),
 "launcher_survived_observation_window": os.environ["SURVIVED"] == "true",
 "launcher_exit_code": None if os.environ["RC"] == "null" else int(os.environ["RC"]),
 "log": os.environ["LOG_PATH"],
 "validation_limit": "Process survival is diagnostic only; it does not prove render/menu/gameplay."
}
open(sys.argv[1],"w").write(json.dumps(d,indent=2)+"\n")
PY
  printf '%-9s survived=%-5s exit=%s\n' "$backend" "$survived" "$rc"
}

case "$BACKEND" in
  all) for b in dxmt d3dmetal dxvk wined3d; do run_backend "$b"; done;;
  dxmt|d3dmetal|dxvk|wined3d) run_backend "$BACKEND";;
  *) echo "invalid backend: $BACKEND" >&2; exit 2;;
esac

python3 - "$RESULTS" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1]); rows=[]
for n in ("dxmt","d3dmetal","dxvk","wined3d"):
    p=root/f"{n}.json"
    if p.exists(): rows.append(json.loads(p.read_text()))
(root/"matrix.json").write_text(json.dumps({"runs":rows},indent=2)+"\n")
print(root/"matrix.json")
PY
