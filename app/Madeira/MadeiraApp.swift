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
        entry.fpsMode = 3                 // Detroit's first real target: 30 FPS.
        entry.liveLogs = true
        entry.performance = true
        entry.config = """
        env.MADEIRA_DEVICE_STATS = 1
        env.MVK_DTR_MSL_LIBRARY_CACHE = 0
        """

        // Replace only our fixed diagnostic entry. Never accept a user-supplied
        // path and never weaken madeira://play's normal library restriction.
        let library = LibraryModel.shared
        library.entries = library.entries.filter {
            $0.id != entryID && $0.relativePath.lowercased() != entry.relativePath.lowercased()
        } + [entry]
        LogStore.shared.log("[detroit-gate] staged 4 verified x64 Windows canaries in C:\\windows\\system32")
        return entry
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
            let entry = try prepareEntry()
            LogStore.shared.log("[detroit-gate] one-tap physical-device test requested")
            // ContentView already observes this value and launches matching
            // library entries through jitReadyForLaunch -> runWineFullSequence.
            ShortcutRouter.shared.pendingExe = entry.windowsPath
        } catch {
            let message = error.localizedDescription
            LogStore.shared.log("[detroit-gate] could not start: \(message)", level: .error)
            library.error = message
        }
    }
}

private struct DetroitVulkanDeviceGateButton: View {
    @ObservedObject private var library = LibraryModel.shared

    var body: some View {
        if DetroitVulkanDeviceGateLauncher.payloadAvailable,
           library.enabled,
           library.current == nil,
           !library.launching {
            Button(action: DetroitVulkanDeviceGateLauncher.launch) {
                Label("Detroit graphics test", systemImage: "checkmark.shield")
            }
            .buttonStyle(.borderedProminent)
            .padding(16)
            .accessibilityHint("Runs the local Vulkan, Windows surface, and 120-frame graphics checks on this iPad.")
        }
    }
}

@main
struct MadeiraApp: App {
    init() {
        // ml1172: read the screen on the main thread; library entries, whose
        // default Resolution comes from it, are also made on other threads.
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
                    JITNetworkShortcut.shared.restoreLeftover()   // also starts its network path monitor
                }
                // madeira://jit-network/... (the Madeira JIT shortcut returning, JITNetwork.swift),
                // else madeira://play?exe=... (Home Screen shortcuts, SavesAndShortcuts.swift).
                .onOpenURL { url in if !JITNetworkShortcut.shared.handle(url) { ShortcutRouter.shared.handle(url) } }
        }
    }
}
