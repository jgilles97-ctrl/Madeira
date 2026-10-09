#!/bin/bash
set -euo pipefail

# Compile Release003/Madeira Detroit MSL disk-cache source files into iPhoneOS
# .metallib files on a Mac with Xcode's Metal Toolchain installed.
#
# This intentionally does NOT use the fork's compile_msl_library_cache.sh:
# Release003 hard-codes `xcrun -sdk macosx`, which produces the wrong platform
# for Madeira's iPad runtime. Apple documents the same MSL -> Metal IR ->
# metallib flow for any SDK the app targets, so this script uses iphoneos.

usage() {
    cat <<'EOF'
Usage: compile_detroit_msl_cache_ios.sh [options] <cache-directory>

Options:
  -f, --force           Rebuild .metallib files even when newer than the source.
  --ios-min <version>   Minimum iOS deployment target. Default: 17.0.
  -h, --help            Show this help.

The cache directory is the folder containing Release003 files named
msl-v1-*.metal and matching msl-v1-*.meta files.
EOF
}

die() { printf 'error: %s\n' "$1" >&2; exit 2; }

force=0
ios_min="${DETROIT_MSL_IOS_MIN:-17.0}"
cache_dir=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        -f|--force) force=1; shift ;;
        --ios-min)
            [ "$#" -ge 2 ] || die "--ios-min requires a value"
            ios_min="$2"; shift 2 ;;
        --ios-min=*) ios_min="${1#--ios-min=}"; shift ;;
        -h|--help) usage; exit 0 ;;
        -*) die "unknown option: $1" ;;
        *)
            [ -z "$cache_dir" ] || die "only one cache directory can be specified"
            cache_dir="$1"; shift ;;
    esac
done

[ -n "$cache_dir" ] || die "cache directory is required"
[ -d "$cache_dir" ] || die "cache directory does not exist: $cache_dir"
case "$ios_min" in
    ''|*[!0-9.]*) die "--ios-min must be a numeric version such as 17.0" ;;
esac

command -v xcrun >/dev/null 2>&1 || die "xcrun is unavailable; run this on a Mac with Xcode"
if ! metal_tool="$(xcrun -sdk iphoneos -find metal 2>/dev/null)"; then
    die "iPhoneOS Metal Toolchain unavailable; install it with: xcodebuild -downloadComponent MetalToolchain"
fi
sdk_path="$(xcrun -sdk iphoneos --show-sdk-path)"

printf 'Detroit iPhoneOS MSL cache compiler\n'
printf 'cache:   %s\n' "$cache_dir"
printf 'sdk:     %s\n' "$sdk_path"
printf 'ios-min: %s\n' "$ios_min"
printf 'metal:   %s\n' "$metal_tool"

compiled=0
skipped=0
failed=0
seen=0

compile_one() {
    local metal_path="$1"
    local base="${metal_path%.metal}"
    local meta_path="${base}.meta"
    local metallib_path="${base}.metallib"
    local ir_path="${base}.madeira-ios.$$.air"
    local tmp_lib="${metallib_path}.madeira-ios.$$.tmp"
    local compile_log="${base}.madeira-ios.$$.log"
    local fp_flags="4294967295"
    local is_position_invariant="0"
    local macro_count="0"
    local key value
    local relaxed_mask=$((0x00000004 | 0x00000008 | 0x00010000 | 0x00020000))
    local fast_mask=$((0x00000001 | 0x00000002 | relaxed_mask))
    local fp_flags_num
    local math_mode="safe"
    local fp32_functions="precise"
    local metal_args=()

    if [ ! -f "$meta_path" ]; then
        printf 'FAIL missing meta: %s\n' "$meta_path" >&2
        return 1
    fi

    while IFS='=' read -r key value; do
        case "$key" in
            fp_fast_math_flags) fp_flags="$value" ;;
            is_position_invariant) is_position_invariant="$value" ;;
            macro_count) macro_count="$value" ;;
        esac
    done < "$meta_path"

    case "$fp_flags" in ''|*[!0-9]*) printf 'FAIL invalid fp_fast_math_flags in %s\n' "$meta_path" >&2; return 1 ;; esac
    case "$is_position_invariant" in ''|*[!0-9]*) printf 'FAIL invalid is_position_invariant in %s\n' "$meta_path" >&2; return 1 ;; esac
    case "$macro_count" in ''|*[!0-9]*) printf 'FAIL invalid macro_count in %s\n' "$meta_path" >&2; return 1 ;; esac

    # Release003's disk-cache loader deliberately excludes specialization-macro
    # variants. Refuse rather than creating a .metallib it would never consume.
    if [ "$macro_count" -ne 0 ]; then
        printf 'SKIP macro-specialized source: %s\n' "$metal_path"
        return 3
    fi

    if [ "$force" != "1" ] && [ -f "$metallib_path" ] && [ "$metallib_path" -nt "$metal_path" ]; then
        printf 'SKIP current: %s\n' "$metallib_path"
        return 3
    fi

    fp_flags_num=$((10#$fp_flags))
    if [ $((fp_flags_num & fast_mask)) -eq "$fast_mask" ]; then
        math_mode="fast"
        fp32_functions="fast"
    elif [ $((fp_flags_num & relaxed_mask)) -eq "$relaxed_mask" ]; then
        math_mode="relaxed"
    fi

    metal_args=("-fmetal-math-mode=$math_mode" "-fmetal-math-fp32-functions=$fp32_functions")
    if [ "$is_position_invariant" != "0" ]; then
        metal_args+=("-fpreserve-invariance")
    fi

    rm -f "$ir_path" "$tmp_lib" "$compile_log"
    if ! "$metal_tool" "${metal_args[@]}" -mios-version-min="$ios_min" -c \
            -o "$ir_path" "$metal_path" 2> "$compile_log"; then
        printf 'FAIL iPhoneOS Metal compile: %s\n' "$metal_path" >&2
        cat "$compile_log" >&2 || true
        rm -f "$ir_path" "$tmp_lib" "$compile_log"
        return 1
    fi

    # Apple documents linking one or more Metal IR inputs with the same `metal`
    # driver to create the runtime-loadable .metallib.
    if ! "$metal_tool" -o "$tmp_lib" "$ir_path" 2>> "$compile_log"; then
        printf 'FAIL iPhoneOS metallib link: %s\n' "$metal_path" >&2
        cat "$compile_log" >&2 || true
        rm -f "$ir_path" "$tmp_lib" "$compile_log"
        return 1
    fi

    [ -s "$tmp_lib" ] || {
        printf 'FAIL empty metallib: %s\n' "$metal_path" >&2
        rm -f "$ir_path" "$tmp_lib" "$compile_log"
        return 1
    }

    mv -f "$tmp_lib" "$metallib_path"
    rm -f "$ir_path" "$compile_log"
    printf 'BUILT iPhoneOS metallib: %s\n' "$metallib_path"
    return 0
}

while IFS= read -r -d '' metal_path; do
    seen=$((seen + 1))
    if compile_one "$metal_path"; then
        compiled=$((compiled + 1))
    else
        rc=$?
        if [ "$rc" -eq 3 ]; then
            skipped=$((skipped + 1))
        else
            failed=$((failed + 1))
        fi
    fi
done < <(find "$cache_dir" -type f -name 'msl-v1-*.metal' -print0 | sort -z)

printf '\nResult: sources=%d built=%d skipped=%d failed=%d\n' "$seen" "$compiled" "$skipped" "$failed"
if [ "$seen" -eq 0 ]; then
    printf 'No msl-v1-*.metal files were found. Run Detroit with disk-cache source collection enabled first.\n'
fi
[ "$failed" -eq 0 ] || exit 1
