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
CACHE_PATCH="$BUILD_DIR/patch_detroit_ipad_cache.py"
CACHE_PATCH_MARKER="MADEIRA_IPAD_DISK_CACHE_SPLIT_V1"

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
need shasum

SDK_PATH="$(xcrun --sdk iphoneos --show-sdk-path)"
SDK_VERSION="$(xcrun --sdk iphoneos --show-sdk-version)"
XCODE_VERSION="$(xcodebuild -version | tr '\n' ';' | sed 's/;$//')"
echo "=== Detroit MoltenVK iOS build ==="
echo "source:  $MOLTENVK_REPO"
echo "release: $MOLTENVK_RELEASE_LABEL"
echo "ref:     $MOLTENVK_REF"
echo "sdk:     $SDK_PATH ($SDK_VERSION)"
echo "xcode:   $XCODE_VERSION"
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

# Madeira's 8 GB iPad profile needs a behaviour Release003 cannot express:
# keep the process-wide MTLLibrary retention cache OFF while keeping the disk
# metallib/source cache ON. Apply a tiny fail-closed source patch after checkout
# so upstream identity remains auditable and the local delta is reproducible.
SHADER_MODULE="$SRC_DIR/MoltenVK/MoltenVK/GPUObjects/MVKShaderModule.mm"
[ -f "$SHADER_MODULE" ] || {
    echo "error: Detroit MoltenVK shader module missing: $SHADER_MODULE" >&2
    exit 7
}
python3 "$CACHE_PATCH" "$SHADER_MODULE"
grep -q "$CACHE_PATCH_MARKER" "$SHADER_MODULE" || {
    echo "error: Detroit iPad shader-cache split did not apply" >&2
    exit 8
}

# Release003 depends on matching SPIRV-Cross changes. Always run the project's
# dependency resolver instead of reusing a random system SPIRV-Cross build.
# Force private Metal APIs off at compile time. MoltenVK defaults this to 0, but
# making it explicit prevents a developer shell/project setting from silently
# producing a different renderer than the one we qualified.
export GCC_PREPROCESSOR_DEFINITIONS='$(inherited) MVK_USE_METAL_PRIVATE_API=0'
(
    cd "$SRC_DIR"
    ./fetchDependencies --ios --parallel-build
    make ios
)

candidate_is_ios_device() {
    local candidate="$1"
    local archs=""
    local loads=""
    local platforms=""

    archs="$(xcrun lipo -archs "$candidate" 2>/dev/null || true)"
    # Release003's device payload is intentionally single-architecture. Reject
    # fat/simulator/macOS archives rather than trying to guess which slice to use.
    if [ "$archs" != "arm64" ]; then
        return 1
    fi

    # vtool does not reliably inspect static archives. otool does, including the
    # LC_BUILD_VERSION carried by each Mach-O object inside libMoltenVK.a.
    loads="$(xcrun otool -l "$candidate" 2>/dev/null || true)"
    if [ -z "$loads" ]; then
        return 1
    fi

    if echo "$loads" | grep -q 'LC_BUILD_VERSION'; then
        platforms="$(printf '%s\n' "$loads" | awk '
            /LC_BUILD_VERSION/ { in_build = 1; next }
            in_build && /^[[:space:]]*platform[[:space:]]+/ { print $2; in_build = 0 }
        ' | sort -u)"
        # Mach-O PLATFORM_IOS is 2. PLATFORM_IOSSIMULATOR is 7. Every object
        # carrying a modern build-version command must agree on device iOS.
        if [ "$platforms" != "2" ]; then
            return 1
        fi
    else
        # Legacy fallback for objects using the older version-min command. It is
        # still fail-closed: require iPhoneOS and reject macOS explicitly.
        echo "$loads" | grep -q 'LC_VERSION_MIN_IPHONEOS' || return 1
        if echo "$loads" | grep -q 'LC_VERSION_MIN_MACOSX'; then
            return 1
        fi
    fi

    return 0
}

# Packaging layout has changed across MoltenVK versions. Do not trust a folder
# name. Inspect each produced static archive and select only a binary that proves
# it is exactly arm64 + iPhoneOS device code.
LIB_PATH=""
while IFS= read -r candidate; do
    [ -n "$candidate" ] || continue
    if candidate_is_ios_device "$candidate"; then
        LIB_PATH="$candidate"
        break
    fi
done < <(find "$SRC_DIR/Package" -type f -name 'libMoltenVK.a' -print 2>/dev/null | sort)

if [ -z "$LIB_PATH" ]; then
    echo "error: MoltenVK built, but no verified arm64 iPhoneOS libMoltenVK.a was found" >&2
    echo "Every candidate must pass both lipo architecture and Mach-O platform checks." >&2
    echo "inspect: $SRC_DIR/Package" >&2
    exit 3
fi

ARCHS="$(xcrun lipo -archs "$LIB_PATH")"
PLATFORM="iphoneos"
cp -f "$LIB_PATH" "$PREFIX/lib/libMoltenVK.a"
ARCHIVE_SHA256="$(shasum -a 256 "$PREFIX/lib/libMoltenVK.a" | awk '{print $1}')"

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
madeira_ipad_cache_split=1
madeira_ipad_cache_patch=$CACHE_PATCH_MARKER
platform=$PLATFORM
architecture=$ARCHS
private_metal_api=0
archive_sha256=$ARCHIVE_SHA256
sdk_path=$SDK_PATH
sdk_version=$SDK_VERSION
xcode_version=$XCODE_VERSION
built_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

echo "staged: $PREFIX/lib/libMoltenVK.a"
echo "commit: $ACTUAL_COMMIT"
echo "platform: $PLATFORM"
echo "architecture: $ARCHS"
echo "archive sha256: $ARCHIVE_SHA256"
echo "private Metal APIs: disabled at compile time"
echo "iPad cache split: $CACHE_PATCH_MARKER"
echo "next: run the one-tap physical Vulkan qualification gate on the M4 iPad; only then launch Detroit for shader-compilation qualification."
