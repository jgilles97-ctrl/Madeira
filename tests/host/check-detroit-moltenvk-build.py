#!/usr/bin/env python3
"""Host-side contract for the Detroit MoltenVK iOS builder.

This does not build MoltenVK on Linux. It makes the expensive macOS build fail
closed by protecting the source pin, device/architecture verification, public-
API policy, and provenance fields that the real-device qualification relies on.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
BUILD = (ROOT / "build/moltenvk-ios/build.sh").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    require(
        'MOLTENVK_DEFAULT_COMMIT="8b511fdc5351a37c305bc246e161796ddca56b18"' in BUILD,
        "Detroit MoltenVK lost the audited immutable Release003 source pin",
    )
    require(
        'MVK_USE_METAL_PRIVATE_API=0' in BUILD,
        "private Metal APIs are not forced off at compile time",
    )
    require(
        'candidate_is_ios_device()' in BUILD,
        "MoltenVK artifacts are no longer selected through a fail-closed device verifier",
    )
    require(
        'xcrun lipo -archs "$candidate"' in BUILD,
        "MoltenVK builder no longer verifies the archive architecture",
    )
    require(
        'if [ "$archs" != "arm64" ]' in BUILD,
        "MoltenVK builder no longer requires the exact arm64 device architecture",
    )
    require(
        'xcrun otool -l "$candidate"' in BUILD,
        "MoltenVK builder no longer inspects static-archive Mach-O platform metadata",
    )
    require(
        "LC_BUILD_VERSION" in BUILD and 'if [ "$platforms" != "2" ]' in BUILD,
        "MoltenVK builder no longer requires Mach-O PLATFORM_IOS",
    )
    require(
        "LC_VERSION_MIN_IPHONEOS" in BUILD and "LC_VERSION_MIN_MACOSX" in BUILD,
        "legacy platform verification is no longer fail-closed",
    )

    verify_at = BUILD.index('if candidate_is_ios_device "$candidate"; then')
    copy_at = BUILD.index('cp -f "$LIB_PATH" "$PREFIX/lib/libMoltenVK.a"')
    require(
        verify_at < copy_at,
        "MoltenVK archive is copied before its iPhoneOS identity is verified",
    )

    for field in (
        "platform=$PLATFORM",
        "architecture=$ARCHS",
        "private_metal_api=0",
        "archive_sha256=$ARCHIVE_SHA256",
        "sdk_path=$SDK_PATH",
        "sdk_version=$SDK_VERSION",
        "xcode_version=$XCODE_VERSION",
    ):
        require(field in BUILD, f"MoltenVK BUILD-INFO lost provenance field: {field}")

    require(
        'shasum -a 256 "$PREFIX/lib/libMoltenVK.a"' in BUILD,
        "staged MoltenVK archive is no longer content-fingerprinted",
    )
    require(
        'xcrun --sdk iphoneos --show-sdk-version' in BUILD,
        "iPhoneOS SDK version is no longer captured",
    )
    require(
        'xcodebuild -version' in BUILD,
        "Xcode version is no longer captured",
    )

    # The old implementation accepted an empty vtool result and therefore could
    # not prove a static archive was really an iPhoneOS device build.
    require(
        'INFO="$(xcrun vtool -show-build' not in BUILD,
        "permissive static-archive vtool validation returned",
    )

    print("PASS immutable Detroit MoltenVK source contract")
    print("PASS arm64 + iPhoneOS device artifact contract")
    print("PASS public Metal API compile-time contract")
    print("PASS MoltenVK archive/toolchain provenance contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
