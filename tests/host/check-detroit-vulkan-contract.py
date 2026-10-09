#!/usr/bin/env python3
"""Cheap host-side guardrails for Detroit's Vulkan bridge scaffolding.

These checks do not claim that Vulkan works on an iPad. They stop accidental
regressions in the *contract* before expensive device testing: portable probes,
Windows guest Vulkan semantics, real Win32 WSI and swapchain coverage, static
MoltenVK loader wiring, deterministic link inclusion, reversible non-Vulkan
builds, and reuse of Madeira's existing Metal window lifetime path.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile

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


def exercise_driver_patcher() -> str:
    patcher = ROOT / "build/win32u-unix/patch_driver_vulkan.py"
    source = ROOT / "build/win32u-unix/driver_ios.c"
    with tempfile.TemporaryDirectory() as tmp:
        output = pathlib.Path(tmp) / "driver_ios_vulkan.c"
        subprocess.run(
            [sys.executable, str(patcher), str(source), str(output)],
            check=True,
            text=True,
            capture_output=True,
        )
        return output.read_text(encoding="utf-8")


def vulkan_init_decl(text: str) -> str:
    match = re.search(r"extern\s+UINT\s+winios_pVulkanInit\s*\([^;]+;", text, re.S)
    return match.group(0) if match else ""


def main() -> int:
    probe = read("tests/x64/vulkan_probe.c")
    build = read("tests/x64/build-vulkan-probe.sh")
    wsi_probe = read("tests/x64/vulkan_wsi_probe.c")
    wsi_build = read("tests/x64/build-vulkan-wsi-probe.sh")
    swapchain_probe = read("tests/x64/vulkan_swapchain_probe.c")
    swapchain_build = read("tests/x64/build-vulkan-swapchain-probe.sh")
    surface = read("build/ntdll-unix/vulkan_surface_ios.c")
    header = read("build/ntdll-unix/vulkan_surface_ios.h")
    display = read("app/Madeira/IOSDisplayShim.m")
    win32u_build = read("build/win32u-unix/build.sh")
    static_loader = read("build/win32u-unix/vulkan_static_ios.c")
    static_header = read("build/win32u-unix/vulkan_static_ios.h")
    ios_driver = read("build/win32u-unix/vulkan_driver_ios.c")
    driver_patcher = read("build/win32u-unix/patch_driver_vulkan.py")
    patched_driver = exercise_driver_patcher()

    # Detroit's probes must be portable across developer Macs and must exercise
    # the Windows guest loader rather than accidentally bypass Wine.
    check_builder(build, "Detroit Vulkan probe builder")
    check_builder(wsi_build, "Detroit Vulkan WSI probe builder")
    check_builder(swapchain_build, "Detroit Vulkan swapchain probe builder")

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

    require("VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME" in probe,
            "headless probe lost portability-subset handling")
    require("enabled_device_exts" in probe,
            "headless probe reports portability subset but does not enable device extensions")

    # WSI canary crosses the Win32 ABI boundary and proves the HWND can become a
    # present-capable Vulkan surface before we add swapchain/rendering complexity.
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

    # Swapchain canary is the real presentation gate: a surface-only PASS is not
    # enough. It must create swapchain images, render a clear through a render
    # pass, acquire/submit/present repeatedly, and leave machine-readable proof.
    for needle in (
        'LoadLibraryA("vulkan-1.dll")',
        "CreateWindowExA",
        "vkCreateWin32SurfaceKHR",
        "VK_KHR_SWAPCHAIN_EXTENSION_NAME",
        "vkCreateSwapchainKHR",
        "vkGetSwapchainImagesKHR",
        "vkAcquireNextImageKHR",
        "vkQueueSubmit",
        "vkQueuePresentKHR",
        "vkCmdBeginRenderPass",
        "VK_ATTACHMENT_LOAD_OP_CLEAR",
        "VK_IMAGE_LAYOUT_PRESENT_SRC_KHR",
        "TARGET_FRAMES 120u",
        'printf("SWAPCHAIN=PASS',
        'printf("CLEAR_PRESENT=PASS',
        'printf("PRESENTED_FRAMES=%u',
        'printf("RESULT=PASS',
        "NEXT_GATE=detroit-process-and-shader-compilation",
    ):
        require(needle in swapchain_probe, f"Vulkan swapchain probe contract missing: {needle}")
    require("VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME" in swapchain_probe,
            "swapchain probe lost portability-subset device handling")
    require("-luser32" in swapchain_build.lower(),
            "swapchain probe builder must link Win32 user32")

    # Reuse the exact Metal-layer path Madeira already keeps correct for DXMT.
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

    # Static MoltenVK loader: win32u takes its normal SONAME_LIBVULKAN path,
    # while dlopen/dlsym are redirected to direct static MoltenVK entry points.
    for needle in (
        "madeira_vulkan_dlopen",
        "madeira_vulkan_dlsym",
        "madeira_vulkan_dlclose",
    ):
        require(needle in static_header, f"static Vulkan loader header missing {needle}")
        require(needle in static_loader, f"static Vulkan loader implementation missing {needle}")
    require("vkGetInstanceProcAddr" in static_loader and "vkGetDeviceProcAddr" in static_loader,
            "static Vulkan loader lost MoltenVK loader entry points")
    require("MOLTENVK_IOS_PREFIX" in win32u_build, "win32u build lost MoltenVK staging override")
    require("MADEIRA_VULKAN" in win32u_build, "win32u build lost reversible Vulkan switch")
    require("vulkan_static_ios.h" in win32u_build, "Wine vulkan.c is not using the static loader preinclude")
    require("SONAME_LIBVULKAN" in win32u_build, "Wine vulkan.c is not forced through its Vulkan-enabled path")
    require("libMoltenVK.a" in win32u_build, "MoltenVK archive is not merged into the app-facing win32u archive")

    # User-driver side: map guest Win32 surfaces to Metal and hand Wine a real
    # pVulkanInit callback instead of the nulldrv STATUS_NOT_IMPLEMENTED slot.
    for needle in (
        "winios_pVulkanInit",
        "vkCreateMetalSurfaceEXT",
        "VK_STRUCTURE_TYPE_METAL_SURFACE_CREATE_INFO_EXT",
        "has_VK_KHR_win32_surface",
        "has_VK_EXT_metal_surface",
        "madeira_vulkan_surface_acquire",
        "client_surface_create",
        "client_surface_release",
    ):
        require(needle in ios_driver, f"iOS Vulkan driver contract missing: {needle}")

    # The build must compile the WSI pieces, and the generated driver must carry
    # a STRONG reference. Weak pVulkanInit inside a static archive can be left
    # unextracted by the linker, silently reverting to Wine's null Vulkan driver.
    require("vulkan_driver_ios.c" in win32u_build,
            "win32u build does not compile the iOS Vulkan user-driver")
    require("vulkan_surface_ios.c" in win32u_build,
            "win32u build does not compile the HWND -> CAMetalLayer adapter")
    require("patch_driver_vulkan.py" in win32u_build,
            "win32u build no longer wires pVulkanInit into driver_ios.c")
    require("__attribute__((weak))" not in driver_patcher,
            "Vulkan-enabled driver patcher itself must not emit a weak pVulkanInit reference")
    init_decl = vulkan_init_decl(patched_driver)
    require(init_decl, "generated Vulkan driver lacks pVulkanInit declaration")
    require("weak" not in init_decl,
            "generated Vulkan pVulkanInit declaration is weak; static archive inclusion is not guaranteed")
    require("winios_user_driver.pVulkanInit = winios_pVulkanInit" in patched_driver,
            "generated Vulkan driver does not wire pVulkanInit")

    # Reversibility: normal builds start with the historical driver, and
    # Detroit-only objects are removed first so MADEIRA_VULKAN=0 cannot inherit
    # artifacts from a prior Vulkan-enabled build.
    require('VULKAN_DRIVER_SOURCE="$BUILD_DIR/driver_ios.c"' in win32u_build,
            "normal win32u build no longer defaults to the unpatched driver source")
    for stale in ("vulkan_static_ios.o", "vulkan_driver_ios.o", "vulkan_surface_ios.o"):
        require(stale in win32u_build and "rm -f" in win32u_build,
                f"win32u build does not explicitly clean stale {stale}")

    print("PASS portable Windows Vulkan headless probe contract")
    print("PASS portable Windows Vulkan WSI probe contract")
    print("PASS real swapchain clear/present canary contract")
    print("PASS static MoltenVK loader contract")
    print("PASS Wine iOS pVulkanInit / Metal-surface contract")
    print("PASS strong static-link inclusion contract")
    print("PASS reversible Vulkan-disabled build contract")
    print("PASS existing HWND -> CAMetalLayer path is reused")
    print("PASS Vulkan surface lifetime acquire/release contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
