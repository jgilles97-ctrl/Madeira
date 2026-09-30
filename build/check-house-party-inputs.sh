#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_DIR="${HOUSE_PARTY_VCRUNTIME_DIR:-$ROOT_DIR/app/Madeira/x86_64-vcruntime}"
required=(concrt140.dll msvcp140.dll msvcp140_1.dll msvcp140_2.dll msvcp140_atomic_wait.dll msvcp140_codecvt_ids.dll vcamp140.dll vccorlib140.dll vcomp140.dll vcruntime140.dll vcruntime140_1.dll vcruntime140_threads.dll)
missing=()
for name in "${required[@]}"; do
  [[ -s "$RUNTIME_DIR/$name" ]] || missing+=("$name")
done
if (( ${#missing[@]} )); then
  echo "House Party preflight: missing Microsoft VC runtime files in $RUNTIME_DIR:" >&2
  printf '  %s\n' "${missing[@]}" >&2
  echo "Read tools/fetch-vcruntime.md for the official extraction workflow." >&2
  exit 2
fi
echo "House Party preflight: all ${#required[@]} VC runtime files are present."
