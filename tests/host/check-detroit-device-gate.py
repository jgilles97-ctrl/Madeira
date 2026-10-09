#!/usr/bin/env python3
"""Static contract for Detroit's real-device Vulkan gate.

This does not pretend to execute an iPad. It protects the properties that make
our eventual physical-device result meaningful: strict ordered Windows canaries,
finite recovery, durable PASS proof only after 120 presented frames, separate
non-qualifying failure diagnosis, foreground-only qualification, binding to both
the exact x64 canaries and the exact local MoltenVK/Wine/FEX/iOS bridge runtime,
and a deliberately narrow one-tap route.
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
    require_order(gate, ['"vulkan_probe.exe"', '"vulkan_wsi_probe.exe"', '"vulkan_swapchain_probe.exe"'], "device gate")

    for needle, label in (
        ("CreateProcessA", "Windows child-process launch"),
        ("WaitForSingleObject", "finite child wait"),
        ("WAIT_TIMEOUT", "timeout handling"),
        ("TerminateProcess", "hung-child recovery"),
        ("GetExitCodeProcess", "child exit-code validation"),
        ("GATE_RESULT=%s:SKIP", "later-stage skip reporting"),
        ("OVERALL=FAIL", "failure summary"),
        ('printf("OVERALL=PASS', "runtime success summary"),
        ("PRESENTED_120_FRAMES=PASS", "120-frame success marker"),
        ("NEXT_GATE=detroit-process-and-shader-compilation", "next-gate marker"),
    ):
        require(gate, needle, label)

    # Success proof remains strict and success-only.
    require(gate, '#define PROOF_SCHEMA "MADEIRA_DETROIT_DEVICE_GATE_PROOF_V2"', "proof schema")
    require(gate, '#define PROOF_PATH "C:\\\\madeira-detroit-vulkan-gate.txt"', "fixed proof path")
    require(gate, "clear_stale_state();", "stale state deletion before testing")
    require(gate, "DeleteFileA(PROOF_PATH)", "stale proof removal")
    require(gate, "FILE_FLAG_WRITE_THROUGH", "durable state file create")
    require(gate, "FlushFileBuffers(file)", "proof/result flush")
    require(gate, "MoveFileExA(PROOF_TEMP_PATH, PROOF_PATH", "atomic proof publication")
    require(gate, "MOVEFILE_WRITE_THROUGH", "durable atomic rename")
    require(gate, "PROOF_RESULT=NOT_WRITTEN", "failed-gate proof suppression")
    require(gate, "FAILED_GATE=proof-publication", "proof publication failure gate")

    # Failure diagnosis is durable but deliberately NOT proof.
    require(gate, '#define RESULT_SCHEMA "MADEIRA_DETROIT_DEVICE_GATE_RESULT_V1"', "last-result schema")
    require(gate, '#define RESULT_PATH "C:\\\\madeira-detroit-vulkan-last-result.txt"', "last-result path")
    require(gate, "DeleteFileA(RESULT_PATH)", "stale last-result removal")
    require(gate, "static void write_last_result", "non-qualifying result writer")
    require(gate, "LAST_RESULT_RECORD=PASS", "last-result publication marker")
    require(gate, 'write_last_result(0, 0, "FAIL", "payload-fingerprint"', "payload fingerprint failure record")
    require(gate, 'write_last_result(payload_hash, 1, "FAIL", stages[i].name', "stage failure record")
    require(gate, 'write_last_result(payload_hash, 1, "FAIL", "foreground-integrity"', "foreground failure record")
    require(gate, 'write_last_result(payload_hash, 1, "FAIL", "proof-publication"', "proof-publication failure record")
    require(gate, 'write_last_result(payload_hash, 1, "PASS", "none"', "successful last-result record")
    require_order(
        gate,
        ["write_full_pass_proof(payload_hash)", 'write_last_result(payload_hash, 1, "PASS", "none"', 'printf("OVERALL=PASS'],
        "success proof/result publication",
    )

    require(gate, "FNV64_OFFSET", "Windows payload fingerprint offset")
    require(gate, "FNV64_PRIME", "Windows payload fingerprint prime")
    require(gate, "payload_fingerprint(&payload_hash)", "pre-test payload fingerprint")
    require(gate, '"PAYLOAD_FNV64=%016llx', "payload identity in Windows output/proof")
    require(gate, "FAILED_GATE=payload-fingerprint", "fingerprint failure gate")

    # The gate executable itself carries a deterministic ID derived from runtime
    # inputs. Fingerprinting the executable therefore binds physical proof to the
    # renderer/runtime as well as to the canary programs.
    require(builder, "DETROIT_RUNTIME_BUILD_ID", "runtime identity builder input")
    require(builder, "MADEIRA_DETROIT_RUNTIME_BUILD_ID=", "embedded runtime identity marker")
    require(builder, "standalone-unbound", "explicit non-qualification identity for standalone CI builds")
    require(builder, 'grep -aqF "MADEIRA_DETROIT_RUNTIME_BUILD_ID=$RUNTIME_BUILD_ID"', "linker retention check")
    require(builder, "64 lowercase hexadecimal characters", "strict runtime identity format")

    for needle, label in (
        ("RUNTIME_INPUTS=(", "ordered runtime identity inputs"),
        ("toolchains/moltenvk-detroit-ios/lib/libMoltenVK.a", "MoltenVK archive in runtime identity"),
        ("app/Madeira/libwin32u_unix.a", "Wine win32u host archive in runtime identity"),
        ("app/Madeira/libntdll_unix.a", "Wine ntdll/winevulkan host archive in runtime identity"),
        ("vulkan-1.dll", "guest Vulkan loader in runtime build"),
        ("winevulkan.dll", "guest Wine Vulkan ICD in runtime build"),
        ("app/Madeira/IOSDisplayShim.m", "iOS Metal display bridge in runtime identity"),
        ("app/Madeira/FEXBridge.mm", "FEX bridge in runtime identity"),
        ("app/Madeira/MadeiraApp.swift", "launcher/proof implementation in runtime identity"),
        ("hashlib.sha256()", "runtime SHA-256 derivation"),
        ('DETROIT_RUNTIME_BUILD_ID="$DETROIT_RUNTIME_BUILD_ID"', "runtime identity passed to gate builder"),
        ('grep -aqF "MADEIRA_DETROIT_RUNTIME_BUILD_ID=$DETROIT_RUNTIME_BUILD_ID"', "packaged gate runtime binding check"),
    ):
        require(orchestrator, needle, label)

    require(gate, '#define FOREGROUND_INVALID_PATH "C:\\\\madeira-detroit-vulkan-gate-invalid.txt"', "foreground marker path")
    require(gate, "DeleteFileA(FOREGROUND_INVALID_PATH)", "foreground marker reset at gate start")
    require(gate, "GetFileAttributesA(FOREGROUND_INVALID_PATH)", "foreground marker check")
    require(gate, "FOREGROUND_GUARD_ARMED=1", "foreground guard log marker")
    require(gate, "FOREGROUND_INTEGRITY=PASS", "foreground proof field")
    require(gate, "FAILED_GATE=foreground-integrity", "foreground failure gate")
    require(gate, "rerun-graphics-test-with-Madeira-kept-in-foreground", "plain foreground recovery action")
    require_order(
        gate,
        ["payload_fingerprint(&payload_hash)", "run_stage(&stages[i])", "foreground_integrity_ok()", "write_full_pass_proof(payload_hash)", 'printf("OVERALL=PASS'],
        "payload/foreground-bound runtime proof flow",
    )

    require(swapchain, "sci.presentMode = VK_PRESENT_MODE_FIFO_KHR", "FIFO presentation mode")
    if "sci.presentMode = VK_PRESENT_MODE_IMMEDIATE_KHR" in swapchain:
        raise AssertionError("physical baseline gate must not silently switch to immediate/uncapped presentation")
    require(swapchain, "TARGET_FRAMES 120u", "120-frame presentation duration")
    require(gate, "if (exit_code != 0)", "nonzero-child failure")
    require_order(gate, ["VULKAN_DEVICE=PASS", "WIN32_SURFACE=PASS", "PRESENTED_120_FRAMES=PASS", 'printf("OVERALL=PASS'], "final runtime PASS markers")

    require(builder, "x86_64-w64-mingw32", "x64 MinGW compiler")
    require(builder, "-Wall -Wextra -Werror", "strict compiler warnings")
    require(builder, "vulkan-device-gate-x64.exe", "x64 gate output name")
    if "-lvulkan" in builder or "-lMoltenVK" in builder:
        raise AssertionError("device gate must not link host Vulkan/MoltenVK directly")

    payload_names = (
        "vulkan_probe.exe",
        "vulkan_wsi_probe.exe",
        "vulkan_swapchain_probe.exe",
        "vulkan-device-gate-x64.exe",
    )
    for exe in payload_names:
        require(orchestrator, exe, f"packaged {exe}")
    require(orchestrator, "Detroit graphics test", "canonical physical-iPad launch instruction")
    if "MADEIRA_EXE=vulkan-device-gate-x64.exe" in orchestrator:
        raise AssertionError("orchestrator must not present the generic EXE path as the canonical physical qualification route")

    require(app, "DetroitVulkanDeviceGateLauncher", "one-tap iPad launcher")
    require(app, '"Detroit graphics test"', "plain-language iPad button")
    require(app, 'gateExecutable = "vulkan-device-gate-x64.exe"', "fixed gate executable")
    for exe in payload_names[:3]:
        require(app, f'"{exe}"', f"fixed iPad payload member {exe}")
    require(app, "guard machine == 0x8664", "on-device x86-64 PE verification")
    require(app, 'relativePath: "windows/system32/\\(gateExecutable)"', "fixed system32 gate entry")
    require(app, "resolvedSystem32.path.hasPrefix(drive.path + \"/\")", "system32 containment check")
    require(app, "ShortcutRouter.shared.pendingExe = entry.windowsPath", "reuse of normal library launch route")
    require(app, "env.MADEIRA_DEVICE_STATS = 1", "device memory telemetry profile")
    require(app, "env.MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM = 3", "Detroit shader compression profile")
    require(app, "env.MVK_DTR_MSL_LIBRARY_CACHE = 0", "8 GB RAM-cache-off profile")
    require(app, "env.MVK_DTR_MSL_LIBRARY_DISK_CACHE = 1", "persistent disk-cache-on profile")
    if "wine_process_start(" in app:
        raise AssertionError("one-tap Detroit UI must not bypass Madeira's normal JIT/library launch sequence")
    if "queryItems" in app or "URLComponents" in app:
        raise AssertionError("one-tap Detroit UI must not grow a user-controlled executable URL route")

    require(app, "DetroitVulkanDeviceGateProof", "iPad proof reader")
    require(app, 'schema = "MADEIRA_DETROIT_DEVICE_GATE_PROOF_V2"', "matching iPad proof schema")
    require(app, 'lastResultSchema = "MADEIRA_DETROIT_DEVICE_GATE_RESULT_V1"', "matching diagnostic-result schema")
    require(app, '"madeira-detroit-vulkan-last-result.txt"', "last-result reader path")
    require(app, "bundledPayloadFingerprint()", "iPad current-payload fingerprint")
    require(app, 'values["EXECUTION"] == "physical-device-local"', "physical execution marker")
    require(app, 'values["FOREGROUND_INTEGRITY"] == "PASS"', "foreground PASS proof")
    require(app, 'values["VULKAN_DEVICE"] == "PASS"', "device PASS proof")
    require(app, 'values["WIN32_SURFACE"] == "PASS"', "surface PASS proof")
    require(app, 'values["PRESENTED_120_FRAMES"] == "PASS"', "120-frame PASS proof")
    require(app, 'values["OVERALL"] == "PASS"', "overall PASS proof")
    require(app, 'values["PAYLOAD_FNV64"]?.lowercased()', "proof/current-payload identity comparison")
    require(app, "Detroit graphics test — Passed", "visible current-payload PASS status")
    require(app, "foregroundInvalidationURL", "iPad foreground marker path")
    require(app, "invalidateForForegroundLoss()", "iPad foreground invalidator")
    require(app, "library.current?.id == entryID", "only-diagnostic invalidation scope")
    require(app, "wine_process_is_running() != 0", "only-running-test invalidation scope")
    require(app, "@Environment(\\.scenePhase)", "scene phase observation")
    require(app, "if phase != .active", "inactive/background invalidation trigger")

    for needle, label in (
        ("enum Status: Equatable", "typed physical proof status"),
        ("case passed", "passed state"),
        ("case notRun", "never-run state"),
        ("case foregroundLost", "foreground-loss state"),
        ("case malformedProof", "malformed record state"),
        ("case wrongSchema", "old-schema state"),
        ("case wrongArchitecture", "wrong-architecture state"),
        ("case notPhysicalDevice", "non-physical state"),
        ("case incompletePass", "incomplete pass state"),
        ("case currentPayloadUnreadable", "unreadable current payload state"),
        ("case payloadChanged", "runtime/payload changed state"),
        ("case payloadFingerprintFailed", "payload-fingerprint failure state"),
        ("case vulkanDeviceFailed", "Vulkan-device failure state"),
        ("case win32SurfaceFailed", "Win32-surface failure state"),
        ("case presentationFailed", "120-frame presentation failure state"),
        ("case proofPublicationFailed", "proof publication failure state"),
        ("case unknownFailure", "unknown failure state"),
        ("statusFromLastResult", "non-qualifying result classifier"),
        ('case "vulkan-device": return .vulkanDeviceFailed', "Vulkan failure mapping"),
        ('case "win32-surface": return .win32SurfaceFailed', "surface failure mapping"),
        ('case "present-120": return .presentationFailed', "presentation failure mapping"),
        ('case "foreground-integrity": return .foregroundLost', "foreground failure mapping"),
        ('case "proof-publication": return .proofPublicationFailed', "proof failure mapping"),
        ("The local graphics runtime changed since the last test", "plain stale-runtime explanation"),
        ("The Detroit capability/Vulkan device test failed", "plain Detroit capability/Vulkan failure explanation"),
        ("Vulkan 1.1, compute, descriptor indexing", "plain capability failure detail"),
        ("Windows-window to iPad Metal-surface test failed", "plain surface failure explanation"),
        ("120-frame presentation test", "plain presentation failure explanation"),
        ("static var validForCurrentPayload: Bool { status.passed }", "success-only qualification Boolean"),
        ("Text(status.explanation)", "visible proof/failure explanation"),
    ):
        require(app, needle, label)

    require(shortcuts, 'url.host?.lowercased() == "play"', "existing play-only shortcut parser")
    require(shortcuts, '@Published var pendingExe: String?', "existing pending library executable route")

    print("PASS: Detroit device gate contract")
    print("PASS: durable PASS proof is published only after full physical success")
    print("PASS: failures persist only as non-qualifying diagnosis")
    print("PASS: physical proof is tied to the current x64 canaries and local graphics/runtime build")
    print("PASS: physical proof is rejected if Madeira leaves the foreground during the gate")
    print("PASS: the iPad UI explains the exact failed graphics stage when available")
    print("PASS: one-tap iPad gate remains fixed, x64-verified, contained, and library-routed")


if __name__ == "__main__":
    main()
