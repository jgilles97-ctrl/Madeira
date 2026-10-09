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