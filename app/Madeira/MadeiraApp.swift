import SwiftUI
import Foundation
import Darwin

/// Lightweight process-memory sampler for long game tests.
///
/// The timer is installed once for the app, but it emits nothing unless a Wine
/// game is actually running AND the active game has MADEIRA_DEVICE_STATS=1.
/// That makes Detroit's memory-first profile opt in without changing unrelated
/// games. os_proc_available_memory() is intentionally sampled live instead of
/// cached because iPadOS can change an app's effective memory limit at runtime.
enum DeviceMemoryHeadroomDiagnostics {
    private static var timer: Timer?

    static func start() {
        guard timer == nil else { return }
        let value = Timer(timeInterval: 10, repeats: true) { _ in report() }
        timer = value
        RunLoop.main.add(value, forMode: .common)
    }

    private static func report() {
        guard wine_process_is_running() != 0 else { return }
        guard let raw = getenv("MADEIRA_DEVICE_STATS"), String(cString: raw) == "1" else { return }

        let available = UInt64(madeira_available_memory_bytes())
        var footprint: UInt64 = 0
        var peak: UInt64 = 0
        let footprintStatus = madeira_memory_footprint_bytes(&footprint, &peak)
        let mib = 1024.0 * 1024.0
        let availableMiB = Double(available) / mib

        if footprintStatus == 0 {
            let footprintMiB = Double(footprint) / mib
            let peakMiB = Double(peak) / mib
            fputs(String(format: "[device-memory] available-mib=%.1f footprint-mib=%.1f peak-mib=%.1f available-bytes=%llu footprint-bytes=%llu peak-bytes=%llu\n",
                         availableMiB, footprintMiB, peakMiB,
                         available, footprint, peak), stderr)
        } else {
            fputs(String(format: "[device-memory] available-mib=%.1f available-bytes=%llu footprint-status=%d\n",
                         availableMiB, available, footprintStatus), stderr)
        }
    }
}

/// A deliberately narrow one-tap route to Detroit's physical-device Vulkan
/// qualification gate. This is NOT a generic URL or arbitrary-EXE launcher.
/// Only the four fixed x86-64 executables produced by build/detroit-vulkan are
/// accepted, their PE machine type is checked on-device, and they are copied
/// into the existing Wine drive before the normal Madeira library launch path
/// handles JIT, FEX, Wine, presentation, cleanup, and errors.
@MainActor
enum DetroitVulkanDeviceGateLauncher {
    static let entryID = UUID(uuidString: "D37017D0-7A11-4A7E-9D30-120F4A6E0001")!
    static let gateExecutable = "vulkan-device-gate-x64.exe"
    static let payloadNames = [
        "vulkan_probe.exe",
        "vulkan_wsi_probe.exe",
        "vulkan_swapchain_probe.exe",
        gateExecutable,
    ]
    private static let fnvOffset: UInt64 = 14_695_981_039_346_656_037
    private static let fnvPrime: UInt64 = 1_099_511_628_211

    static var foregroundInvalidationURL: URL {
        LibraryModel.drive.appendingPathComponent("madeira-detroit-vulkan-gate-invalid.txt", isDirectory: false)
    }

    private enum GateError: LocalizedError {
        case payloadFolderMissing
        case payloadMissing(String)
        case payloadWrongArchitecture(String, UInt16)
        case prefixNotReady
        case unsafeSystem32
        case installFailed(String)

        var errorDescription: String? {
            switch self {
            case .payloadFolderMissing:
                return "This Madeira build does not contain the Detroit Vulkan test payload. Rebuild the Detroit Vulkan runtime first."
            case .payloadMissing(let name):
                return "The Detroit test payload is incomplete: \(name) is missing."
            case .payloadWrongArchitecture(let name, let machine):
                return String(format: "%@ is not an x86-64 Windows test program (PE machine 0x%04X).", name, machine)
            case .prefixNotReady:
                return "Madeira's Windows drive is not ready yet. Finish Madeira setup, then run the Detroit graphics test again."
            case .unsafeSystem32:
                return "Madeira refused to stage the Detroit test because the Windows system folder resolved outside its own drive."
            case .installFailed(let detail):
                return "Madeira could not stage the Detroit test files: \(detail)"
            }
        }
    }

    private static var payloadRoot: URL? {
        Bundle.main.resourceURL?.appendingPathComponent("arm64ec-windows", isDirectory: true)
    }

    /// Cheap visibility check for the button. Full validation happens on tap.
    static var payloadAvailable: Bool {
        guard let root = payloadRoot else { return false }
        return payloadNames.allSatisfy {
            var isDirectory: ObjCBool = false
            let url = root.appendingPathComponent($0, isDirectory: false)
            return FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory) && !isDirectory.boolValue
        }
    }

    /// Same deliberately simple fingerprint algorithm used by the x86-64
    /// Windows gate. It is an identity/check-for-staleness token, not a security
    /// signature. The gate executable itself contains a deterministic identity
    /// of the MoltenVK/Wine/FEX/iOS runtime built with it, so changing either a
    /// canary OR that runtime changes this fingerprint and invalidates old proof.
    static func bundledPayloadFingerprint() throws -> UInt64 {
        guard let root = payloadRoot else { throw GateError.payloadFolderMissing }
        var hash = fnvOffset
        let separator: UInt8 = 0xff

        func absorb(_ bytes: some Sequence<UInt8>) {
            for byte in bytes {
                hash ^= UInt64(byte)
                hash = hash &* fnvPrime
            }
        }

        for name in payloadNames {
            absorb(name.utf8)
            absorb(CollectionOfOne(separator))
            let url = root.appendingPathComponent(name, isDirectory: false)
            guard FileManager.default.fileExists(atPath: url.path) else { throw GateError.payloadMissing(name) }
            let handle = try FileHandle(forReadingFrom: url)
            defer { try? handle.close() }
            while let data = try handle.read(upToCount: 64 * 1024), !data.isEmpty {
                absorb(data)
            }
        }
        return hash
    }

    private static func peMachine(_ url: URL) throws -> UInt16 {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        let dos = try handle.read(upToCount: 64) ?? Data()
        guard dos.count == 64, dos[0] == 0x4d, dos[1] == 0x5a else {
            throw GateError.installFailed("\(url.lastPathComponent) has no Windows MZ header")
        }
        let peOffset = UInt64(dos[60])
            | (UInt64(dos[61]) << 8)
            | (UInt64(dos[62]) << 16)
            | (UInt64(dos[63]) << 24)
        guard peOffset >= 64, peOffset < 16 * 1024 * 1024 else {
            throw GateError.installFailed("\(url.lastPathComponent) has an invalid PE header offset")
        }
        try handle.seek(toOffset: peOffset)
        let pe = try handle.read(upToCount: 6) ?? Data()
        guard pe.count == 6, pe[0] == 0x50, pe[1] == 0x45, pe[2] == 0, pe[3] == 0 else {
            throw GateError.installFailed("\(url.lastPathComponent) has no PE signature")
        }
        return UInt16(pe[4]) | (UInt16(pe[5]) << 8)
    }

    private static func prepareEntry() throws -> LibraryEntry {
        guard let root = payloadRoot else { throw GateError.payloadFolderMissing }
        let fm = FileManager.default
        let drive = LibraryModel.drive.standardizedFileURL
        let system32 = drive.appendingPathComponent("windows/system32", isDirectory: true)
        var isDirectory: ObjCBool = false
        guard fm.fileExists(atPath: system32.path, isDirectory: &isDirectory), isDirectory.boolValue else {
            throw GateError.prefixNotReady
        }
        let resolvedSystem32 = system32.resolvingSymlinksInPath().standardizedFileURL
        guard resolvedSystem32.path.hasPrefix(drive.path + "/") else { throw GateError.unsafeSystem32 }

        for name in payloadNames {
            let source = root.appendingPathComponent(name, isDirectory: false)
            var sourceIsDirectory: ObjCBool = false
            guard fm.fileExists(atPath: source.path, isDirectory: &sourceIsDirectory), !sourceIsDirectory.boolValue else {
                throw GateError.payloadMissing(name)
            }
            let machine = try peMachine(source)
            guard machine == 0x8664 else { throw GateError.payloadWrongArchitecture(name, machine) }

            let destination = resolvedSystem32.appendingPathComponent(name, isDirectory: false)
            do {
                if fm.fileExists(atPath: destination.path) { try fm.removeItem(at: destination) }
                try fm.copyItem(at: source, to: destination)
            } catch {
                throw GateError.installFailed("\(name): \(error.localizedDescription)")
            }
        }

        var entry = LibraryEntry(
            title: "Detroit Vulkan Device Test",
            relativePath: "windows/system32/\(gateExecutable)",
            bits: 64
        )
        entry.id = entryID
        entry.graphicsAPI = "Vulkan / MoltenVK diagnostic"
        entry.resolution = "1280x720"
        entry.fpsMode = 3
        entry.liveLogs = true
        entry.performance = true
        entry.config = """
        env.MADEIRA_DEVICE_STATS = 1
        env.MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM = 3
        env.MVK_DTR_MSL_LIBRARY_CACHE = 0
        env.MVK_DTR_MSL_LIBRARY_DISK_CACHE = 1
        """

        let library = LibraryModel.shared
        library.entries = library.entries.filter {
            $0.id != entryID && $0.relativePath.lowercased() != entry.relativePath.lowercased()
        } + [entry]
        LogStore.shared.log("[detroit-gate] staged 4 verified x64 Windows canaries in C:\\windows\\system32")
        return entry
    }

    /// The physical proof is valid only if Madeira stayed active while this
    /// diagnostic's Wine process was actually running. iOS may reject Metal GPU
    /// work after backgrounding, so a run that leaves the foreground is useful
    /// diagnostic evidence but is not accepted as our graphics qualification.
    static func invalidateForForegroundLoss() {
        let library = LibraryModel.shared
        guard library.current?.id == entryID, wine_process_is_running() != 0 else { return }
        let line = "foreground-integrity=invalid\n"
        do {
            try Data(line.utf8).write(to: foregroundInvalidationURL, options: .atomic)
            LogStore.shared.log("[detroit-gate] physical proof invalidated because Madeira left the foreground", level: .error)
        } catch {
            LogStore.shared.log("[detroit-gate] could not write foreground invalidation marker: \(error.localizedDescription)", level: .error)
        }
    }

    static func launch() {
        let library = LibraryModel.shared
        guard library.enabled else {
            library.error = "The Detroit graphics test uses Madeira's normal Library launch path. Switch to the Library interface and restart Madeira, then tap the test again."
            return
        }
        guard library.current == nil, wine_process_is_running() == 0, wineserver_is_running() == 0 else {
            library.error = "Close the current Madeira session before running the Detroit graphics test."
            return
        }
        do {
            let expected = try bundledPayloadFingerprint()
            let entry = try prepareEntry()
            LogStore.shared.log(String(format: "[detroit-gate] one-tap physical-device test requested payload=%016llx", expected))
            ShortcutRouter.shared.pendingExe = entry.windowsPath
        } catch {
            let message = error.localizedDescription
            LogStore.shared.log("[detroit-gate] could not start: \(message)", level: .error)
            library.error = message
        }
    }
}

/// Strict reader for proof emitted by the x86-64 Windows controller after the
/// physical iPad actually presents 120 frames. Qualification remains success-
/// only. A separate last-result record may explain a failure, but it can never
/// satisfy validForCurrentPayload or unlock the next Detroit gate.
@MainActor
enum DetroitVulkanDeviceGateProof {
    static let schema = "MADEIRA_DETROIT_DEVICE_GATE_PROOF_V2"
    static let lastResultSchema = "MADEIRA_DETROIT_DEVICE_GATE_RESULT_V1"
    static var url: URL {
        LibraryModel.drive.appendingPathComponent("madeira-detroit-vulkan-gate.txt", isDirectory: false)
    }
    static var lastResultURL: URL {
        LibraryModel.drive.appendingPathComponent("madeira-detroit-vulkan-last-result.txt", isDirectory: false)
    }

    enum Status: Equatable {
        case passed
        case notRun
        case foregroundLost
        case malformedProof
        case wrongSchema
        case wrongArchitecture
        case notPhysicalDevice
        case incompletePass
        case currentPayloadUnreadable
        case payloadChanged
        case payloadFingerprintFailed
        case vulkanDeviceFailed
        case win32SurfaceFailed
        case presentationFailed
        case proofPublicationFailed
        case unknownFailure

        var passed: Bool { self == .passed }

        var buttonTitle: String {
            switch self {
            case .passed: return "Detroit graphics test — Passed"
            case .payloadChanged: return "Detroit graphics test — Rerun needed"
            case .foregroundLost: return "Detroit graphics test — Rerun in foreground"
            case .payloadFingerprintFailed: return "Detroit graphics test — Payload failed"
            case .vulkanDeviceFailed: return "Detroit graphics test — Vulkan failed"
            case .win32SurfaceFailed: return "Detroit graphics test — Surface failed"
            case .presentationFailed: return "Detroit graphics test — Presentation failed"
            case .proofPublicationFailed: return "Detroit graphics test — Proof save failed"
            case .unknownFailure: return "Detroit graphics test — Failed"
            default: return "Detroit graphics test"
            }
        }

        var explanation: String {
            switch self {
            case .passed:
                return "Passed on this iPad with this exact local graphics runtime, including Detroit's Vulkan 1.1, compute, and descriptor-indexing baseline."
            case .notRun:
                return "Not yet proven on this iPad. Run the graphics test before launching Detroit."
            case .foregroundLost:
                return "The previous test left the foreground, so its result cannot qualify Detroit. Run it again and keep Madeira open."
            case .malformedProof:
                return "The saved test record is damaged or incomplete. Run the graphics test again."
            case .wrongSchema:
                return "The saved test record is from an older test format. Run the current graphics test again."
            case .wrongArchitecture:
                return "The saved test record did not come from the required x86-64 Windows path. Run the current graphics test again."
            case .notPhysicalDevice:
                return "The saved test record does not confirm a fully local physical-iPad run. Run the graphics test on this iPad."
            case .incompletePass:
                return "The PASS proof is missing one or more required Detroit graphics checks. Run the current test again."
            case .currentPayloadUnreadable:
                return "Madeira cannot verify the test/runtime files bundled in this app. Rebuild the Detroit Vulkan runtime."
            case .payloadChanged:
                return "The local graphics runtime changed since the last test. Rerun it so this exact runtime is physically proven."
            case .payloadFingerprintFailed:
                return "Madeira could not verify all four Windows test files. Rebuild the Detroit Vulkan runtime before testing again."
            case .vulkanDeviceFailed:
                return "The Detroit capability/Vulkan device test failed. Fix Vulkan 1.1, compute, descriptor indexing, or the Wine/MoltenVK device path before testing Detroit."
            case .win32SurfaceFailed:
                return "Vulkan started, but the Windows-window to iPad Metal-surface test failed. Fix the surface bridge before testing Detroit."
            case .presentationFailed:
                return "The surface worked, but Madeira could not complete the 120-frame presentation test. Fix swapchain/presentation before testing Detroit."
            case .proofPublicationFailed:
                return "The graphics checks passed, but Madeira could not save trustworthy PASS proof. Fix proof storage and rerun before Detroit."
            case .unknownFailure:
                return "The graphics gate failed in an unrecognized stage. Open the live log and use the first FAILED_GATE line."
            }
        }
    }

    private static func fields(at fileURL: URL) -> [String: String]? {
        guard let data = try? Data(contentsOf: fileURL), data.count > 0, data.count <= 4096,
              let text = String(data: data, encoding: .utf8) else { return nil }
        var result: [String: String] = [:]
        for raw in text.split(whereSeparator: \Character.isNewline) {
            let line = String(raw).trimmingCharacters(in: .whitespacesAndNewlines)
            guard !line.isEmpty, let equals = line.firstIndex(of: "=") else { continue }
            let key = String(line[..<equals])
            let value = String(line[line.index(after: equals)...])
            guard !key.isEmpty, result[key] == nil else { return nil }
            result[key] = value
        }
        return result
    }

    private static func currentFingerprint() -> String? {
        guard let expected = try? DetroitVulkanDeviceGateLauncher.bundledPayloadFingerprint() else { return nil }
        return String(format: "%016llx", expected)
    }

    private static func statusFromLastResult(_ values: [String: String]) -> Status {
        guard values["SCHEMA"] == lastResultSchema else { return .wrongSchema }
        guard values["ARCH"] == "x86_64-windows" else { return .wrongArchitecture }
        guard values["EXECUTION"] == "physical-device-local" else { return .notPhysicalDevice }
        guard values["OVERALL"] == "FAIL" else { return .incompletePass }

        let failedGate = values["FAILED_GATE"] ?? ""
        if failedGate == "payload-fingerprint" { return .payloadFingerprintFailed }

        guard let expected = currentFingerprint() else { return .currentPayloadUnreadable }
        guard values["PAYLOAD_FNV64"]?.lowercased() == expected else { return .payloadChanged }

        switch failedGate {
        case "vulkan-device": return .vulkanDeviceFailed
        case "win32-surface": return .win32SurfaceFailed
        case "present-120": return .presentationFailed
        case "foreground-integrity": return .foregroundLost
        case "proof-publication": return .proofPublicationFailed
        default: return .unknownFailure
        }
    }

    static var status: Status {
        let fm = FileManager.default
        if fm.fileExists(atPath: DetroitVulkanDeviceGateLauncher.foregroundInvalidationURL.path) {
            return .foregroundLost
        }

        if fm.fileExists(atPath: url.path) {
            guard let values = fields(at: url) else { return .malformedProof }
            guard values["SCHEMA"] == schema else { return .wrongSchema }
            guard values["ARCH"] == "x86_64-windows" else { return .wrongArchitecture }
            guard values["EXECUTION"] == "physical-device-local" else { return .notPhysicalDevice }
            guard values["FOREGROUND_INTEGRITY"] == "PASS",
                  values["DETROIT_CAPABILITIES"] == "PASS",
                  values["VULKAN_DEVICE"] == "PASS",
                  values["WIN32_SURFACE"] == "PASS",
                  values["PRESENTED_120_FRAMES"] == "PASS",
                  values["OVERALL"] == "PASS",
                  values["NEXT_GATE"] == "detroit-process-and-shader-compilation",
                  let recorded = values["PAYLOAD_FNV64"]?.lowercased() else { return .incompletePass }
            guard let expected = currentFingerprint() else { return .currentPayloadUnreadable }
            guard recorded == expected else { return .payloadChanged }
            return .passed
        }

        if fm.fileExists(atPath: lastResultURL.path) {
            guard let values = fields(at: lastResultURL) else { return .malformedProof }
            return statusFromLastResult(values)
        }
        return .notRun
    }

    static var validForCurrentPayload: Bool { status.passed }
}

private struct DetroitVulkanDeviceGateButton: View {
    @ObservedObject private var library = LibraryModel.shared

    var body: some View {
        if DetroitVulkanDeviceGateLauncher.payloadAvailable,
           library.enabled,
           library.current == nil,
           !library.launching {
            let status = DetroitVulkanDeviceGateProof.status
            VStack(alignment: .trailing, spacing: 6) {
                Button(action: DetroitVulkanDeviceGateLauncher.launch) {
                    Label(status.buttonTitle,
                          systemImage: status.passed ? "checkmark.shield.fill" : "checkmark.shield")
                }
                .buttonStyle(.borderedProminent)
                Text(status.explanation)
                    .font(.caption)
                    .multilineTextAlignment(.trailing)
                    .frame(maxWidth: 360, alignment: .trailing)
                    .accessibilityLabel(status.explanation)
            }
            .padding(16)
            .accessibilityHint(status.passed
                ? "Tap to repeat the local Detroit graphics qualification."
                : "Tap to verify Detroit's Vulkan capabilities, Windows surface, and 120-frame presentation path. Keep Madeira in the foreground until it finishes.")
        }
    }
}

@main
struct MadeiraApp: App {
    @Environment(\.scenePhase) private var scenePhase

    init() {
        _ = ResolutionChoices.screen
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .overlay(alignment: .bottomTrailing) {
                    DetroitVulkanDeviceGateButton()
                }
                .modifier(ClaimGamepadEvents())
                .onAppear {
                    GamepadInput.shared.start()
                    HardwareInput.shared.start()
                    DeviceMemoryHeadroomDiagnostics.start()
                    JITNetworkShortcut.shared.restoreLeftover()
                }
                .onChange(of: scenePhase) { _, phase in
                    if phase != .active {
                        DetroitVulkanDeviceGateLauncher.invalidateForForegroundLoss()
                    }
                }
                .onOpenURL { url in if !JITNetworkShortcut.shared.handle(url) { ShortcutRouter.shared.handle(url) } }
        }
    }
}