#!/usr/bin/env python3
"""Cheap host-side guardrails for Detroit's Vulkan bridge scaffolding.

These checks do not claim that Vulkan works on an iPad. They stop accidental
regressions in the *contract* before expensive device testing: portable probes,
Windows guest Vulkan semantics, real Win32 WSI coverage, and reuse of Madeira's
existing Metal window lifetime path.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_builder(text: str, name: str) -> None:
    require("/Users/" not in text, f"{name} contains a hard-coded Mac path")
    require("X86_64_W64_MINGW32_CLANG" in text, f"{name} lacks compiler override")
    require("VULKAN_HEADERS" in text, f"{name} lacks Vulkan-header override")
    require("-lvulkan" not in text.lower(), f"{name} must not link a host Vulkan import library")


def main() -> int:
    probe = read("tests/x64/vulkan_probe.c")
    build = read("tests/x64/build-vulkan-probe.sh")
    wsi_probe = read("tests/x64/vulkan_wsi_probe.c")
    wsi_build = read("tests/x64/build-vulkan-wsi-probe.sh")
    surface = read("build/ntdll-unix/vulkan_surface_ios.c")
    header = read("build/ntdll-unix/vulkan_surface_ios.h")
    display = read("app/Madeira/IOSDisplayShim.m")

    # Detroit's probes must be portable across developer Macs and must exercise
    # the Windows guest loader rather than accidentally bypass Wine.
    check_builder(build, "Detroit Vulkan probe builder")
    check_builder(wsi_build, "Detroit Vulkan WSI probe builder")

    for needle in (
        'LoadLibraryA("vulkan-1.dll")',
        "vkGetInstanceProcAddr",
        "vkCreateInstance",
        "vkEnumeratePhysicalDevices",
        "vkCreateDevice",
        "VK_KHR_WIN32_SURFACE_EXTENSION_NAME",
        "VK_KHR_SWAPCHAIN_EXTENSION_NAME",
        'printf("RESULT=PASS',
    ):
        require(needle in probe, f"Vulkan probe contract missing: {needle}")

    # MoltenVK exposes VK_KHR_portability_subset. If advertised, a conformant
    # application must enable it at VkDevice creation; keep the canary honest.
    require("VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME" in probe,
            "headless probe lost portability-subset handling")
    require("enabled_device_exts" in probe,
            "headless probe reports portability subset but does not enable device extensions")

    # WSI canary must cross the Win32 ABI boundary and validate present support,
    # formats, and modes. Merely checking that the extension name exists is not
    # enough to prove HWND -> CAMetalLayer works.
    for needle in (
        'LoadLibraryA("vulkan-1.dll")',
        "CreateWindowExA",
        "VK_KHR_SURFACE_EXTENSION_NAME",
        "VK_KHR_WIN32_SURFACE_EXTENSION_NAME",
        "vkCreateWin32SurfaceKHR",
        "vkGetPhysicalDeviceSurfaceSupportKHR",
        "vkGetPhysicalDeviceSurfaceCapabilitiesKHR",
        "vkGetPhysicalDeviceSurfaceFormatsKHR",
        "vkGetPhysicalDeviceSurfacePresentModesKHR",
        'printf("WIN32_SURFACE=PASS',
        'printf("RESULT=PASS',
    ):
        require(needle in wsi_probe, f"Vulkan WSI probe contract missing: {needle}")
    require("-luser32" in wsi_build.lower(), "WSI probe builder must link Win32 user32")

    # Reuse the exact Metal-layer path Madeira already keeps correct for DXMT.
    # A second HWND->CAMetalLayer registry would create lifetime and resizing
    # bugs, especially when desktop mode is enabled.
    exported = (
        "macdrv_view_create_metal_view",
        "macdrv_view_get_metal_layer",
        "macdrv_view_release_metal_view",
    )
    for symbol in exported:
        require(symbol in display, f"IOSDisplayShim no longer exports required symbol: {symbol}")
        require(symbol in surface, f"Vulkan WSI adapter no longer resolves required symbol: {symbol}")

    for symbol in (
        "madeira_vulkan_surface_bridge_ready",
        "madeira_vulkan_surface_acquire",
        "madeira_vulkan_surface_release",
    ):
        require(symbol in header, f"Vulkan WSI header missing: {symbol}")
        require(symbol in surface, f"Vulkan WSI implementation missing: {symbol}")

    require("metal_view" in header and "metal_layer" in header,
            "surface binding must preserve both retained view token and layer pointer")

    print("PASS portable Windows Vulkan headless probe contract")
    print("PASS portable Windows Vulkan WSI probe contract")
    print("PASS existing HWND -> CAMetalLayer path is reused")
    print("PASS Vulkan surface lifetime acquire/release contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
