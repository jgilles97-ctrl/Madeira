#!/bin/bash
# Build Wine's win32u unix side as a static lib for iOS (aarch64).
# Mirrors build/ntdll-unix/build.sh — compiles unpatched upstream .c files
# with iOS clang, per-file overrides go in this dir.
set -e

BUILD_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$BUILD_DIR/../.." && pwd)"
WINE_SRC="$REPO_ROOT/wine"
WINE_BUILD="$WINE_SRC/build-macos"
NTDLL_DIR="$REPO_ROOT/build/ntdll-unix"
NTDLL_SHIMS="$NTDLL_DIR/shims"
SDK=$(xcrun --sdk iphoneos --show-sdk-path)
OBJ_DIR="$BUILD_DIR/obj"
APP_LIB="$REPO_ROOT/app/Madeira/libwin32u_unix.a"
PYTHON="${PYTHON:-python3}"

mkdir -p "$OBJ_DIR"

SUCCEEDED=0
FAILED=0
FAILED_FILES=""

FREETYPE_DIR="$REPO_ROOT/build/freetype-ios"
MOLTENVK_PREFIX="${MOLTENVK_IOS_PREFIX:-$REPO_ROOT/toolchains/moltenvk-detroit-ios}"
VULKAN_MODE="${MADEIRA_VULKAN:-auto}"
VULKAN_ENABLED=0
VULKAN_DRIVER_SOURCE="$BUILD_DIR/driver_ios.c"

# Detroit path: opt in automatically once the iOS MoltenVK archive produced by
# build/moltenvk-ios/build.sh is present. MADEIRA_VULKAN=0 forces the historical
# Vulkan-disabled build; MADEIRA_VULKAN=1 requires MoltenVK and fails early if
# staging is incomplete. This keeps normal Madeira builds reversible.
if [ "$VULKAN_MODE" != "0" ]; then
    if [ -f "$MOLTENVK_PREFIX/lib/libMoltenVK.a" ] && \
       [ -f "$MOLTENVK_PREFIX/include/vulkan/vulkan.h" ]; then
        VULKAN_ENABLED=1
    elif [ "$VULKAN_MODE" = "1" ]; then
        echo "error: MADEIRA_VULKAN=1 but MoltenVK iOS staging is incomplete" >&2
        echo "expected: $MOLTENVK_PREFIX/lib/libMoltenVK.a" >&2
        echo "run: build/moltenvk-ios/build.sh" >&2
        exit 2
    fi
fi

# Never let a prior Vulkan-enabled run leak Detroit-only objects into a later
# disabled build. The final archive gathers normal win32u objects by wildcard,
# so these must be removed before configuration is evaluated.
rm -f \
    "$OBJ_DIR/vulkan_static_ios.o" \
    "$OBJ_DIR/vulkan_driver_ios.o" \
    "$OBJ_DIR/vulkan_surface_ios.o" \
    "$OBJ_DIR/driver_ios_vulkan.c"

compile_one() {
    local src=$1
    local name=$2
    shift 2
    echo -n "  $name... "

    if xcrun -sdk iphoneos clang \
        -arch arm64 -isysroot "$SDK" -miphoneos-version-min=17.0 \
        -O2 -fPIC -fvisibility=hidden -fno-stack-protector -fno-strict-aliasing \
        -Wno-implicit-function-declaration -Wno-int-conversion \
        -include "$BUILD_DIR/config_ios.h" \
        -include "$NTDLL_SHIMS/wine_ios_exit.h" \
        -I"$BUILD_DIR" \
        -I"$WINE_BUILD/include" \
        -I"$NTDLL_SHIMS" \
        -I"$WINE_BUILD/dlls/win32u" -I"$WINE_SRC/dlls/win32u" \
        -I"$WINE_BUILD/include" -I"$WINE_SRC/include" \
        -D__WINESRC__ -D_WIN32U_ \
        -D_ACRTIMP= -DWINBASEAPI= \
        -DSYSTEMDLLPATH=\"\" \
        -DWINE_UNIX_LIB -DWINE_IOS=1 \
        -D__wine_unix_lib_init=win32u_unix_lib_init \
        -USONAME_LIBFREETYPE \
        -USONAME_LIBFONTCONFIG \
        -USONAME_LIBEGL \
        -USONAME_LIBVULKAN \
        -USONAME_LIBGNUTLS \
        -UHAVE_FT2BUILD_H \
        "$@" \
        -c "$src" -o "$OBJ_DIR/$name.o" 2>"$OBJ_DIR/$name.err"; then
        echo "OK"
        SUCCEEDED=$((SUCCEEDED + 1))
    else
        echo "FAILED"
        FAILED=$((FAILED + 1))
        FAILED_FILES="$FAILED_FILES $name"
    fi
}

echo "=== Building win32u unix (iOS) ==="

if [ "$VULKAN_ENABLED" -eq 1 ]; then
    echo "Vulkan: static MoltenVK ENABLED ($MOLTENVK_PREFIX)"

    # Generate a Vulkan-enabled copy of driver_ios.c only for this build. The
    # generated source uses a strong pVulkanInit reference, which forces the
    # static linker to include the iOS user-driver instead of silently falling
    # back to Wine's headless/null Vulkan driver.
    if ! command -v "$PYTHON" >/dev/null 2>&1; then
        echo "error: Python is required to generate the Vulkan driver wiring" >&2
        exit 3
    fi
    VULKAN_DRIVER_SOURCE="$OBJ_DIR/driver_ios_vulkan.c"
    "$PYTHON" "$BUILD_DIR/patch_driver_vulkan.py" \
        "$BUILD_DIR/driver_ios.c" "$VULKAN_DRIVER_SOURCE"

    # Strong references from this object to vkGet*ProcAddr force the matching
    # MoltenVK archive members into the final app link. Wine's vulkan.c itself
    # continues to use its normal dlfcn-shaped interface through the preinclude
    # shim below.
    compile_one "$BUILD_DIR/vulkan_static_ios.c" "vulkan_static_ios" \
        -I"$MOLTENVK_PREFIX/include"

    # Shared HWND -> CAMetalLayer lifetime adapter plus the Wine user-driver
    # callbacks that translate VK_KHR_win32_surface to VK_EXT_metal_surface.
    compile_one "$NTDLL_DIR/vulkan_surface_ios.c" "vulkan_surface_ios" \
        -I"$NTDLL_DIR"
    compile_one "$BUILD_DIR/vulkan_driver_ios.c" "vulkan_driver_ios" \
        -I"$NTDLL_DIR" \
        -I"$MOLTENVK_PREFIX/include"
else
    echo "Vulkan: disabled (build MoltenVK first, or set MADEIRA_VULKAN=1 to require it)"
fi

# All *.c files except main.c (main.c is the PE side entry — lives in win32u.dll).
# dibdrv/*.c compile as their own translation units.
for src in $WINE_SRC/dlls/win32u/*.c $WINE_SRC/dlls/win32u/dibdrv/*.c; do
    name=$(basename "$src" .c)

    # main.c is PE-side (DllMain, syscall PE wrappers) — skip.
    [ "$name" = "main" ] && continue

    # dibdrv file collisions: prefix them so we don't overwrite dc.o/bitblt.o/objects.o
    if [[ "$src" == *"/dibdrv/"* ]]; then
        name="dibdrv_$name"
    fi

    # Per-file iOS overrides (analogous to ntdll-unix's pattern).
    case "$name" in
        class)
            compile_one "$BUILD_DIR/class_ios.c" "class"
            continue
            ;;
        winstation)
            compile_one "$BUILD_DIR/winstation_ios.c" "winstation"
            continue
            ;;
        sysparams)
            compile_one "$BUILD_DIR/sysparams_ios.c" "sysparams"
            continue
            ;;
        defwnd)
            compile_one "$BUILD_DIR/defwnd_ios.c" "defwnd"
            continue
            ;;
        driver)
            compile_one "$VULKAN_DRIVER_SOURCE" "driver"
            continue
            ;;
        message)
            compile_one "$BUILD_DIR/message_ios.c" "message"
            continue
            ;;
        d3dkmt)
            # Wraps upstream d3dkmt.c: the opt-in MADEIRA_KMT_ADAPTER adapter
            # (see the header comment in d3dkmt_ios.c).
            compile_one "$BUILD_DIR/d3dkmt_ios.c" "d3dkmt"
            continue
            ;;
        syscall)
            # Wraps upstream syscall.c and adds win32u_zero_bits(), the
            # allocation ceiling of the calling pseudo-process (see the
            # header comment in syscall_ios.c).
            compile_one "$BUILD_DIR/syscall_ios.c" "syscall"
            continue
            ;;
        freetype)
            # Statically-linked freetype (build/freetype-ios). The wrapper
            # re-defines HAVE_FT2BUILD_H itself; config_ios.h's #undefs win
            # for every other TU.
            compile_one "$BUILD_DIR/freetype_ios.c" "freetype" \
                -I"$FREETYPE_DIR/build/include" \
                -I"$REPO_ROOT/research/freetype/include"
            continue
            ;;
        vulkan)
            if [ "$VULKAN_ENABLED" -eq 1 ]; then
                # Wine's Vulkan translation remains upstream. Only replace the
                # desktop dlopen/dlsym loader with our statically linked MoltenVK
                # adapter and make SONAME_LIBVULKAN take the supported path.
                compile_one "$src" "vulkan" \
                    -I"$MOLTENVK_PREFIX/include" \
                    -include "$BUILD_DIR/vulkan_static_ios.h" \
                    -DSONAME_LIBVULKAN=\"madeira-moltenvk-static\"
            else
                compile_one "$src" "vulkan"
            fi
            continue
            ;;
    esac

    compile_one "$src" "$name"
done

echo ""
echo "Results: $SUCCEEDED succeeded, $FAILED failed"
if [ -n "$FAILED_FILES" ]; then
    echo "Failed:$FAILED_FILES"
fi

if [ $FAILED -gt 0 ]; then
    echo ""
    echo "(not linking — errors in $OBJ_DIR/<name>.err)"
    exit 1
fi

echo ""
echo "=== Building libwin32u_unix.a ==="
ar rcs "$OBJ_DIR/libwin32u_unix.a" "$OBJ_DIR"/*.o

# Merge third-party static archives into one app-facing archive. This preserves
# Madeira's current Xcode project contract: it already links libwin32u_unix.a.
EXTRA_ARCHIVES=()
if [ -f "$FREETYPE_DIR/build/libfreetype.a" ]; then
    EXTRA_ARCHIVES+=("$FREETYPE_DIR/build/libfreetype.a")
    echo "will merge libfreetype.a"
else
    echo "WARNING: no libfreetype.a — fonts will be disabled"
fi
if [ "$VULKAN_ENABLED" -eq 1 ]; then
    EXTRA_ARCHIVES+=("$MOLTENVK_PREFIX/lib/libMoltenVK.a")
    echo "will merge libMoltenVK.a"
fi

if [ ${#EXTRA_ARCHIVES[@]} -gt 0 ]; then
    libtool -static -o "$OBJ_DIR/libwin32u_unix.merged.a" \
        "$OBJ_DIR/libwin32u_unix.a" "${EXTRA_ARCHIVES[@]}"
    mv -f "$OBJ_DIR/libwin32u_unix.merged.a" "$OBJ_DIR/libwin32u_unix.a"
fi

echo "Copying to app..."
cp "$OBJ_DIR/libwin32u_unix.a" "$APP_LIB"
echo "libwin32u_unix.a: $(wc -c < "$APP_LIB" | tr -d ' ') bytes"
if [ "$VULKAN_ENABLED" -eq 1 ]; then
    echo "Detroit Vulkan host loader + iOS WSI driver: staged into libwin32u_unix.a"
fi
echo "Done!"
