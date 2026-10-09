#!/usr/bin/env python3
"""Static contract for Detroit's real-device Vulkan gate.

This does not pretend to execute an iPad. It protects the properties that make
our eventual physical-device result meaningful: the controller itself is an
x64 Windows program, runs all three canaries through Wine/FEX in a strict order,
has finite timeouts, stops on the first failure, only reports success after the
120-frame presentation stage succeeds, and the iPad app exposes a deliberately
narrow one-tap route to that fixed diagnostic without becoming an arbitrary EXE
launcher.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "tests/x64/vulkan_device_gate.c"
BUILDER = ROOT / "tests/x64/build-vulkan-device-gate.sh"
SWAPCHAIN_PROBE = ROOT / "tests/x64/vulkan_swapchain_probe.c"
ORCHESTRATOR = ROOT / "build/detroit-vulkan/build.sh"
APP = ROOT / "app/Madeira/MadeiraApp.swift"
SHORTCUTS = ROOT / "app/Madeira/SavesAndShortcuts.swift"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle}")


def require_order(text: str, needles: list[str], label: str) -> None:
    positions = []
    for needle in needles:
        pos = text.find(needle)
        if pos < 0:
            raise AssertionError(f"missing {label}: {needle}")
        positions.append(pos)
    if positions != sorted(positions):
        raise AssertionError(f"wrong {label} order: {needles}")


def main() -> None:
    gate = GATE.read_text()
    builder = BUILDER.read_text()
    swapchain = SWAPCHAIN_PROBE.read_text()
    orchestrator = ORCHESTRATOR.read_text()
    app = APP.read_text()
    shortcuts = SHORTCUTS.read_text()

    require(gate, '"vulkan_probe.exe"', "headless Vulkan canary")
    require(gate, '"vulkan_wsi_probe.exe"', "Win32-surface canary")
    require(gate, '"vulkan_swapchain_probe.exe"', "120-frame presentation canary")
    require_order(
        gate,
        ['"vulkan_probe.exe"', '"vulkan_wsi_probe.exe"', '"vulkan_swapchain_probe.exe"'],
        "device gate",
    )

    require(gate, "CreateProcessA", "Windows child-process launch")
    require(gate, "WaitForSingleObject", "finite child wait")
    require(gate, "WAIT_TIMEOUT", "timeout handling")
    require(gate, "TerminateProcess", "hung-child recovery")
    require(gate, "GetExitCodeProcess", "child exit-code validation")
    require(gate, "GATE_RESULT=%s:SKIP", "later-stage skip reporting")
    require(gate, "OVERALL=FAIL", "failure summary")
    require(gate, "OVERALL=PASS", "success summary")
    require(gate, "PRESENTED_120_FRAMES=PASS", "120-frame success marker")
    require(gate, "NEXT_GATE=detroit-process-and-shader-compilation", "next-gate marker")

    # Keep the baseline presentation proof display-paced. A 2026 MoltenVK
    # drawable-lifetime report specifically reproduces with uncapped/immediate
    # presentation. Detroit's first iPad target is 30 FPS, so an IMMEDIATE-mode
    # stress test belongs in a separate optional diagnostic rather than in the
    # pass/fail gate that decides whether we may move on to Detroit itself.
    require(swapchain, "sci.presentMode = VK_PRESENT_MODE_FIFO_KHR", "FIFO presentation mode")
    if "sci.presentMode = VK_PRESENT_MODE_IMMEDIATE_KHR" in swapchain:
        raise AssertionError("physical baseline gate must not silently switch to immediate/uncapped presentation")
    require(swapchain, "TARGET_FRAMES 120u", "120-frame presentation duration")

    # A zero exit code from every child is required before overall PASS.
    require(gate, "if (exit_code != 0)", "nonzero-child failure")
    require_order(
        gate,
        ["VULKAN_DEVICE=PASS", "WIN32_SURFACE=PASS", "PRESENTED_120_FRAMES=PASS", "OVERALL=PASS"],
        "final PASS markers",
    )

    # Keep the controller itself x86-64 Windows code so it cannot bypass the
    # FEX/Wine path being tested. It must not link host Vulkan directly.
    require(builder, "x86_64-w64-mingw32", "x64 MinGW compiler")
    require(builder, "-Wall -Wextra -Werror", "strict compiler warnings")
    require(builder, "vulkan-device-gate-x64.exe", "x64 gate output name")
    if "-lvulkan" in builder or "-lMoltenVK" in builder:
        raise AssertionError("device gate must not link host Vulkan/MoltenVK directly")

    # The normal Detroit Vulkan build must package the controller and all three
    # children into Madeira's Windows DLL/executable farm.
    payload_names = (
        "vulkan_probe.exe",
        "vulkan_wsi_probe.exe",
        "vulkan_swapchain_probe.exe",
        "vulkan-device-gate-x64.exe",
    )
    for exe in payload_names:
        require(orchestrator, exe, f"packaged {exe}")
    require(orchestrator, 'MADEIRA_EXE=vulkan-device-gate-x64.exe', "device launch instruction")

    # The iPad UI must expose only the fixed Detroit diagnostic. It stages the
    # known four binaries, verifies AMD64 PE machine type on the device, keeps
    # destination writes inside Madeira's own Wine drive, then hands the fixed
    # entry to the existing library/JIT/FEX/Wine route. It must not call the low-
    # level Wine process entry point directly or add an arbitrary executable URL.
    require(app, "DetroitVulkanDeviceGateLauncher", "one-tap iPad launcher")
    require(app, 'Label("Detroit graphics test"', "plain-language iPad button")
    require(app, 'gateExecutable = "vulkan-device-gate-x64.exe"', "fixed gate executable")
    for exe in payload_names[:3]:
        require(app, f'"{exe}"', f"fixed iPad payload member {exe}")
    require(app, "guard machine == 0x8664", "on-device x86-64 PE verification")
    require(app, 'relativePath: "windows/system32/\\(gateExecutable)"', "fixed system32 gate entry")
    require(app, "resolvedSystem32.path.hasPrefix(drive.path + \"/\")", "system32 containment check")
    require(app, "ShortcutRouter.shared.pendingExe = entry.windowsPath", "reuse of normal library launch route")
    require(app, "env.MADEIRA_DEVICE_STATS = 1", "device memory telemetry profile")
    require(app, "env.MVK_DTR_MSL_LIBRARY_CACHE = 0", "8 GB memory-first shader-cache profile")
    if "wine_process_start(" in app:
        raise AssertionError("one-tap Detroit UI must not bypass Madeira's normal JIT/library launch sequence")
    if "queryItems" in app or "URLComponents" in app:
        raise AssertionError("one-tap Detroit UI must not grow a user-controlled executable URL route")

    # Existing public madeira://play links remain library-restricted; this test
    # must not weaken the general shortcut parser to make the diagnostic work.
    require(shortcuts, 'url.host?.lowercased() == "play"', "existing play-only shortcut parser")
    require(shortcuts, '@Published var pendingExe: String?', "existing pending library executable route")

    print("PASS: Detroit device gate contract")
    print("PASS: one-tap iPad gate remains fixed, x64-verified, contained, and library-routed")


if __name__ == "__main__":
    main()
