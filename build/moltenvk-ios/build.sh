#!/bin/bash
set -euo pipefail

# Build the Detroit-compatible MoltenVK fork for a real iOS device.
#
# This intentionally builds from source instead of committing a third-party
# binary. It is the first half of Madeira's Vulkan path: MoltenVK provides the
# Vulkan -> Metal implementation; Wine's winevulkan bridge is wired separately.
#
# Release003 is currently the Detroit-specific baseline, but the default below
# is its immutable commit rather than the movable tag. Override the repo/ref
# explicitly only when testing a newer source revision on purpose.

BUILD_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$BUILD_DIR/../.." && pwd)"

MOLTENVK_REPO="${MOLTENVK_DETROIT_REPO:-https://github.com/DiAvisoo/MoltenVK-Detroit.git}"
MOLTENVK_RELEASE_LABEL="${MOLTENVK_DETROIT_RELEASE_LABEL:-Release003}"
MOLTENVK_DEFAULT_COMMIT="8b511fdc5351a37c305bc246e161796ddca56b18"
MOLTENVK_REF="${MOLTENVK_DETROIT_REF:-$MOLTENVK_DEFAULT_COMMIT}"
WORK_ROOT="${MOLTENVK_WORK_ROOT:-$REPO_ROOT/.build/moltenvk-detroit-ios}"
SRC_DIR="$WORK_ROOT/src"
PREFIX="${MOLTENVK_IOS_PREFIX:-$REPO_ROOT/toolchains/moltenvk-detroit-ios}"

need() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "error: missing required tool: $1" >&2
        exit 2
    }
}

need git
need xcrun
need xcodebuild
need make
need cmake
need python3

SDK_PATH="$(xcrun --sdk iphoneos --show-sdk-path)"
echo "=== Detroit MoltenVK iOS build ==="
echo "source:  $MOLTENVK_REPO"
echo "release: $MOLTENVK_RELEASE_LABEL"
echo "ref:     $MOLTENVK_REF"
echo "sdk:     $SDK_PATH"
echo "prefix:  $PREFIX"

mkdir -p "$WORK_ROOT" "$PREFIX/lib" "$PREFIX/include"

if [ ! -d "$SRC_DIR/.git" ]; then
    rm -rf "$SRC_DIR"
    git clone --filter=blob:none "$MOLTENVK_REPO" "$SRC_DIR"
fi

git -C "$SRC_DIR" fetch --tags --force origin
git -C "$SRC_DIR" checkout --detach "$MOLTENVK_REF"
ACTUAL_COMMIT="$(git -C "$SRC_DIR" rev-parse HEAD)"

# When no override is supplied, fail closed if anything somehow moved us away
# from the audited Release003 commit. This protects reproducibility and makes a
# future fork upgrade an explicit review instead of an accidental source change.
if [ -z "${MOLTENVK_DETROIT_REF:-}" ] && [ "$ACTUAL_COMMIT" != "$MOLTENVK_DEFAULT_COMMIT" ]; then
    echo "error: default Detroit MoltenVK source drifted" >&2
    echo "expected: $MOLTENVK_DEFAULT_COMMIT" >&2
    echo "actual:   $ACTUAL_COMMIT" >&2
    exit 6
fi

# Release003 depends on matching SPIRV-Cross changes. Always run the project's
# dependency resolver instead of reusing a random system SPIRV-Cross build.
(
    cd "$SRC_DIR"
    ./fetchDependencies --ios --parallel-build
    make ios
)

# MoltenVK's packaging layout has changed across versions. Prefer the packaged
# iOS static archive and fail loudly rather than silently staging the macOS or
# simulator build.
LIB_PATH="$(find "$SRC_DIR/Package" -type f -name 'libMoltenVK.a' -path '*iOS*' -print 2>/dev/null | head -n 1 || true)"
if [ -z "$LIB_PATH" ]; then
    LIB_PATH="$(find "$SRC_DIR/Package" -type f -name 'libMoltenVK.a' -print 2>/dev/null | head -n 1 || true)"
fi
if [ -z "$LIB_PATH" ]; then
    echo "error: MoltenVK built, but no packaged libMoltenVK.a was found" >&2
    echo "inspect: $SRC_DIR/Package" >&2
    exit 3
fi

# Guard against accidentally packaging a simulator or macOS slice.
INFO="$(xcrun vtool -show-build "$LIB_PATH" 2>/dev/null || true)"
if [ -n "$INFO" ] && echo "$INFO" | grep -Eqi 'platform (macOS|iOSSimulator)'; then
    echo "error: refusing non-device MoltenVK archive: $LIB_PATH" >&2
    echo "$INFO" >&2
    exit 4
fi

cp -f "$LIB_PATH" "$PREFIX/lib/libMoltenVK.a"

HEADER_DIR=""
for candidate in \
    "$SRC_DIR/Package/Latest/MoltenVK/include" \
    "$SRC_DIR/MoltenVK/include" \
    "$SRC_DIR/include"; do
    if [ -d "$candidate" ]; then
        HEADER_DIR="$candidate"
        break
    fi
done
if [ -z "$HEADER_DIR" ]; then
    echo "error: could not locate MoltenVK/Vulkan headers" >&2
    exit 5
fi

rm -rf "$PREFIX/include/MoltenVK" "$PREFIX/include/vulkan"
[ -d "$HEADER_DIR/MoltenVK" ] && cp -R "$HEADER_DIR/MoltenVK" "$PREFIX/include/"
[ -d "$HEADER_DIR/vulkan" ] && cp -R "$HEADER_DIR/vulkan" "$PREFIX/include/"

cat > "$PREFIX/BUILD-INFO.txt" <<EOF
source=$MOLTENVK_REPO
release=$MOLTENVK_RELEASE_LABEL
ref=$MOLTENVK_REF
commit=$ACTUAL_COMMIT
sdk=$SDK_PATH
built_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

echo "staged: $PREFIX/lib/libMoltenVK.a"
echo "commit: $ACTUAL_COMMIT"
echo "next: wire Wine winevulkan's unix side to this archive, then run the Vulkan probe before Detroit."
