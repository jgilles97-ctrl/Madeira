#!/bin/bash
# Build a local House Party test IPA from the official Madeira 0.1.1 release.
#
# No House Party files are read or embedded. Microsoft VC runtime DLLs are fetched
# from Microsoft and added only to this local derived package. The optional
# winegstreamer bridge comes from our open-source CI artifact and stays dormant
# until env.MADEIRA_WG_64BIT=1 is explicitly enabled in Documents/madeira.cfg.
set -euo pipefail

MADEIRA_VERSION="0.1.1"
MADEIRA_IPA_SHA256="045aeb8fd4c71c2e6a78fb4511f94c56f8ed7af14c47a3b0ea2937a4fc8bfcee"
MADEIRA_IPA_URL="https://github.com/willfaust/Madeira/releases/download/v${MADEIRA_VERSION}/Madeira-${MADEIRA_VERSION}.ipa"
VCREDIST_URL="https://aka.ms/vc14/vc_redist.x64.exe"
REPO="jgilles97-ctrl/Madeira"
WORKFLOW="house-party-media-build.yml"
ARTIFACT="house-party-winegstreamer-arm64ec"
BASE="${HOUSE_PARTY_PORT_ROOT:-$HOME/Library/Application Support/Cenluma/HousePartyPort}"
OUTPUT="${HOUSE_PARTY_TEST_IPA:-$BASE/packages/Madeira-${MADEIRA_VERSION}-HouseParty-test.ipa}"
MEDIA_DLL="${HOUSE_PARTY_WINEGSTREAMER_DLL:-}"

usage() {
  echo "usage: $0 [--output IPA] [--winegstreamer DLL] [--no-media]"
}
WITH_MEDIA=1
while (($#)); do
  case "$1" in
    --output) OUTPUT="${2:?}"; shift 2;;
    --winegstreamer) MEDIA_DLL="${2:?}"; shift 2;;
    --no-media) WITH_MEDIA=0; shift;;
    -h|--help) usage; exit 0;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2;;
  esac
done

for tool in curl unzip zip shasum python3; do
  command -v "$tool" >/dev/null || { echo "missing required tool: $tool" >&2; exit 3; }
done
if ! command -v 7zz >/dev/null 2>&1; then
  command -v brew >/dev/null 2>&1 || { echo "7zz is required (brew install sevenzip)" >&2; exit 3; }
  echo "Installing sevenzip with Homebrew for official VC_redist extraction..."
  brew install sevenzip
fi

mkdir -p "$(dirname "$OUTPUT")" "$BASE/cache"
TMP="$(mktemp -d "$BASE/cache/package.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

IPA="$TMP/Madeira.ipa"
echo "Downloading official Madeira ${MADEIRA_VERSION} release..."
curl -fL --retry 3 "$MADEIRA_IPA_URL" -o "$IPA"
echo "$MADEIRA_IPA_SHA256  $IPA" | shasum -a 256 -c -

echo "Downloading latest supported Microsoft x64 VC++ redistributable..."
VCEXE="$TMP/vc_redist.x64.exe"
curl -fL --retry 3 "$VCREDIST_URL" -o "$VCEXE"
VCEXE_SHA="$(shasum -a 256 "$VCEXE" | awk '{print $1}')"
mkdir -p "$TMP/vc-outer" "$TMP/vc-files"
7zz x "$VCEXE" "-o$TMP/vc-outer" -y >/dev/null
found_cab=0
while IFS= read -r -d "" candidate; do
  found_cab=1
  7zz x "$candidate" "-o$TMP/vc-files" -y >/dev/null 2>&1 || true
done < <(find "$TMP/vc-outer" -type f -path '*CABINET*' -print0)
(( found_cab )) || { echo "No CABINET payload found in Microsoft redistributable" >&2; exit 4; }

PAYLOAD="$TMP/ipa"
mkdir -p "$PAYLOAD"
unzip -q "$IPA" -d "$PAYLOAD"
APP="$(find "$PAYLOAD/Payload" -maxdepth 1 -type d -name '*.app' -print -quit)"
[[ -n "$APP" ]] || { echo "Madeira app bundle missing from IPA" >&2; exit 4; }
VCDIR="$APP/x86_64-vcruntime"
mkdir -p "$VCDIR"

required=(concrt140.dll msvcp140.dll msvcp140_1.dll msvcp140_2.dll msvcp140_atomic_wait.dll msvcp140_codecvt_ids.dll vcamp140.dll vccorlib140.dll vcomp140.dll vcruntime140.dll vcruntime140_1.dll vcruntime140_threads.dll)
python3 - "$TMP/vc-files" "$VCDIR" "${required[@]}" <<'PY'
import shutil, struct, sys
from pathlib import Path
root, out = Path(sys.argv[1]), Path(sys.argv[2])
names = sys.argv[3:]
rows = []
for name in names:
    candidates = [p for p in root.rglob("*") if p.is_file() and p.name.lower() == name.lower()]
    chosen = None
    for p in candidates:
        try:
            d = p.read_bytes()
            if len(d) < 0x100 or d[:2] != b"MZ": continue
            pe = struct.unpack_from("<I", d, 0x3c)[0]
            if d[pe:pe+4] != b"PE\\0\\0": continue
            machine = struct.unpack_from("<H", d, pe + 4)[0]
            if machine != 0x8664: continue
            magic = struct.unpack_from("<H", d, pe + 24)[0]
            dd = 112 if magic == 0x20b else 96
            cert_off, cert_size = struct.unpack_from("<II", d, pe + 24 + dd + 4 * 8)
            if not cert_size or cert_off + cert_size > len(d): continue
            chosen = p; break
        except (OSError, struct.error):
            continue
    if not chosen:
        raise SystemExit(f"missing signed x86_64 Microsoft runtime DLL: {name}")
    target = out / name
    shutil.copyfile(chosen, target)
    rows.append((name, len(target.read_bytes())))
print("VC runtime:", ", ".join(f"{n}={s}" for n, s in rows))
PY

MEDIA_SHA=""
if (( WITH_MEDIA )); then
  if [[ -z "$MEDIA_DLL" ]]; then
    if command -v gh >/dev/null 2>&1; then
      RUN="$(gh run list -R "$REPO" --workflow "$WORKFLOW" --branch joey-house-party-current --status success --limit 1 --json databaseId --jq '.[0].databaseId' 2>/dev/null || true)"
      if [[ -n "$RUN" ]]; then
        mkdir -p "$TMP/media"
        gh run download "$RUN" -R "$REPO" -n "$ARTIFACT" -D "$TMP/media"
        MEDIA_DLL="$(find "$TMP/media" -type f -name winegstreamer.dll -print -quit)"
      fi
    fi
  fi
  [[ -n "$MEDIA_DLL" && -s "$MEDIA_DLL" ]] || {
    echo "No winegstreamer.dll available. Pass --winegstreamer PATH or --no-media." >&2
    exit 5
  }
  cp "$MEDIA_DLL" "$APP/arm64ec-windows/winegstreamer.dll"
  MEDIA_SHA="$(shasum -a 256 "$MEDIA_DLL" | awk '{print $1}')"
fi

mkdir -p "$PAYLOAD/HousePartyOverlay"
MADEIRA_SHA="$MADEIRA_IPA_SHA256" VC_SHA="$VCEXE_SHA" MEDIA_SHA="$MEDIA_SHA" WITH_MEDIA="$WITH_MEDIA" \
python3 - > "$PAYLOAD/HousePartyOverlay/provenance.json" <<'PY'
import json, os
print(json.dumps({
  "schema_version": 1,
  "base": {"madeira_version": "0.1.1", "ipa_sha256": os.environ["MADEIRA_SHA"]},
  "vc_redist": {"source": "Microsoft latest-supported x64 permalink", "installer_sha256": os.environ["VC_SHA"], "dlls_embedded_locally": 12},
  "media_bridge": {"included": os.environ["WITH_MEDIA"] == "1", "sha256": os.environ["MEDIA_SHA"] or None, "enabled_by_default": False},
  "contains_house_party_game_files": False,
  "signing": "Derived IPA must be re-signed by the sideloading tool for the target device.",
}, indent=2, sort_keys=True))
PY

rm -f "$OUTPUT"
(
  cd "$PAYLOAD"
  zip -qry "$OUTPUT" Payload HousePartyOverlay
)
FINAL_SHA="$(shasum -a 256 "$OUTPUT" | awk '{print $1}')"
echo "Created: $OUTPUT"
echo "SHA-256: $FINAL_SHA"
echo "House Party game files embedded: NO"
echo "64-bit media bridge enabled by default: NO"
echo "Sideload/resign the derived IPA before installation."
