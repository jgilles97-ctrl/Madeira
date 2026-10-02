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
mkdir -p "$TMP/vc-outer" "$TMP/vc-burn-cabs" "$TMP/vc-expand"
7zz x "$VCEXE" "-o$TMP/vc-outer" -y >/dev/null

# Modern VC Redist is a WiX Burn bundle. 7-Zip's PE handler does not always
# expose Burn's attached container directly, so also carve every structurally
# valid CAB stream from the Microsoft installer. CAB's cbCabinet field is a
# self-delimiting size at offset 8; malformed/overlapping candidates are ignored.
python3 - "$VCEXE" "$TMP/vc-burn-cabs" <<'PY'
import struct, sys
from pathlib import Path
src, out = Path(sys.argv[1]), Path(sys.argv[2])
data = src.read_bytes()
out.mkdir(parents=True, exist_ok=True)
pos = 0; spans = []; n = 0
while True:
    pos = data.find(b"MSCF", pos)
    if pos < 0: break
    if pos + 36 > len(data):
        break
    try:
        size = struct.unpack_from("<I", data, pos + 8)[0]
        folders = struct.unpack_from("<H", data, pos + 26)[0]
        files = struct.unpack_from("<H", data, pos + 28)[0]
    except struct.error:
        pos += 4; continue
    end = pos + size
    valid = 36 <= size <= len(data) - pos and folders > 0 and files > 0
    overlaps = any(not (end <= a or pos >= b) for a, b in spans)
    if valid and not overlaps:
        n += 1
        (out / f"burn-{n}.cab").write_bytes(data[pos:end])
        spans.append((pos, end))
        pos = end
    else:
        pos += 4
if not n:
    raise SystemExit("No structurally valid Burn CAB container found in Microsoft redistributable")
print(f"Burn CAB containers carved: {n}")
PY

for cab in "$TMP"/vc-burn-cabs/*.cab; do
  name="$(basename "$cab" .cab)"
  mkdir -p "$TMP/vc-outer/$name"
  7zz x "$cab" "-o$TMP/vc-outer/$name" -y >/dev/null
done

# Recursively ask 7-Zip which payload files are archives/containers and expand
# them into isolated derived directories. The final selector below still
# requires exact DLL names, x86-64 PE machine and intact Authenticode payload.
search_dir="$TMP/vc-outer"
for round in 1 2 3 4 5 6; do
  round_dir="$TMP/vc-expand/round-$round"
  mkdir -p "$round_dir"
  expanded=0
  index=0
  while IFS= read -r -d "" candidate; do
    # Keep the recursion bounded and skip obvious final binaries. 7-Zip can
    # inspect PE files too, which would otherwise create useless resource trees.
    case "$candidate" in
      *.[dD][lL][lL]|*.[eE][xX][eE]) continue;;
    esac
    ((index+=1))
    dest="$round_dir/$index"
    if 7zz l "$candidate" >/dev/null 2>&1; then
      mkdir -p "$dest"
      if 7zz x "$candidate" "-o$dest" -y >/dev/null 2>&1; then
        ((expanded+=1))
      else
        rm -rf "$dest"
      fi
    fi
  done < <(find "$search_dir" -type f -size -128M -print0)
  search_dir="$round_dir"
  (( expanded > 0 )) || break
done
VC_FILES_ROOT="$TMP"

PAYLOAD="$TMP/ipa"
mkdir -p "$PAYLOAD"
unzip -q "$IPA" -d "$PAYLOAD"
APP="$(find "$PAYLOAD/Payload" -maxdepth 1 -type d -name '*.app' -print -quit)"
[[ -n "$APP" ]] || { echo "Madeira app bundle missing from IPA" >&2; exit 4; }
VCDIR="$APP/x86_64-vcruntime"
mkdir -p "$VCDIR"

required=(concrt140.dll msvcp140.dll msvcp140_1.dll msvcp140_2.dll msvcp140_atomic_wait.dll msvcp140_codecvt_ids.dll vcamp140.dll vccorlib140.dll vcomp140.dll vcruntime140.dll vcruntime140_1.dll vcruntime140_threads.dll)
python3 - "$VC_FILES_ROOT" "$VCDIR" "${required[@]}" <<'PY'
import shutil, struct, sys
from pathlib import Path
root, out = Path(sys.argv[1]), Path(sys.argv[2])
names = sys.argv[3:]
rows = []
for name in names:
    expected = name.lower()
    candidates = [
        p for p in root.rglob("*") if p.is_file()
        and p.name.lower() in {expected, expected + "_amd64"}
    ]
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
        same_name = [
            p for p in root.rglob("*") if p.is_file()
            and p.name.lower() in {expected, expected + "_amd64"}
        ]
        sample = []
        for p in same_name[:12]:
            try:
                d = p.read_bytes()
                pe = struct.unpack_from("<I", d, 0x3c)[0] if len(d) >= 0x40 and d[:2] == b"MZ" else -1
                machine = struct.unpack_from("<H", d, pe + 4)[0] if pe >= 0 and pe + 6 <= len(d) else -1
                sample.append(f"{p}: bytes={len(d)} machine={machine:#x}")
            except Exception as exc:
                sample.append(f"{p}: {exc}")
        available = sorted({p.name for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".dll"})
        print(f"VC extraction diagnostic: {len(same_name)} candidate(s) named {name}", file=sys.stderr)
        for line in sample:
            print("  " + line, file=sys.stderr)
        print("VC extraction diagnostic: DLL names found: " + ", ".join(available[:120]), file=sys.stderr)
        print("VC extraction diagnostic: payload inventory:", file=sys.stderr)
        seen = 0
        for base_name in ("vc-burn-cabs", "vc-outer", "vc-expand"):
            base = root / base_name
            if not base.exists(): continue
            for p in sorted(base.rglob("*")):
                if not p.is_file(): continue
                try:
                    head = p.read_bytes()[:16]
                    if head.startswith(b"MSCF"): kind = "CAB"
                    elif head.startswith(b"\\xd0\\xcf\\x11\\xe0\\xa1\\xb1\\x1a\\xe1"): kind = "OLE/MSI"
                    elif head.startswith(b"MZ"): kind = "PE"
                    elif head.startswith(b"PK\\x03\\x04"): kind = "ZIP"
                    elif head.lstrip().startswith(b"<"): kind = "XML/text"
                    else: kind = head[:8].hex()
                    rel = p.relative_to(root)
                    print(f"  {rel} bytes={p.stat().st_size} kind={kind}", file=sys.stderr)
                    seen += 1
                    if seen >= 180: break
                except OSError:
                    pass
            if seen >= 180: break
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
