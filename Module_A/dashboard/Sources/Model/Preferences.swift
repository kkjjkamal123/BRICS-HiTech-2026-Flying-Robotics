import AppKit
import UserNotifications

/// Behaviour settings that are read where they act. The Settings window edits the same keys with @AppStorage,
/// so the defaults here must match the ones there.
enum Pref {
    static let launchSection = "launchSection"          // "last" or an AppSection raw value
    static let lastSection = "lastSection"
    static let keepAwake = "keepAwake"
    static let confirmQuit = "confirmQuitInFlight"
    static let autoRecord = "autoRecord"
    static let videoTelemetry = "videoTelemetry"
    static let reticle = "showReticle"
    static let mapLabels = "mapLabels"
    static let alertBanner = "alertBanner"
    static let alertSeconds = "alertSeconds"
    static let alertSound = "alertSound"
    static let alertNotify = "alertNotify"
    static let linkLostSound = "linkLostSound"
    static let batteryCaution = "batteryCaution"
    static let batteryCritical = "batteryCritical"

    // bool(forKey:) / double(forKey:) also read launch arguments like `-autoRecord YES`, which arrive as strings
    static func bool(_ key: String, _ fallback: Bool) -> Bool {
        UserDefaults.standard.object(forKey: key) == nil ? fallback : UserDefaults.standard.bool(forKey: key)
    }
    static func double(_ key: String, _ fallback: Double) -> Double {
        UserDefaults.standard.object(forKey: key) == nil ? fallback : UserDefaults.standard.double(forKey: key)
    }
    static func string(_ key: String, _ fallback: String) -> String { UserDefaults.standard.string(forKey: key) ?? fallback }
}

/// Sounds and macOS notifications for detections and link loss.
@MainActor
enum Alerts {
    static let sounds = ["Glass", "Hero", "Ping", "Submarine", "Funk", "Purr", "Tink", "Sosumi"]

    static func play(_ name: String) {
        guard !name.isEmpty else { return }
        NSSound(named: NSSound.Name(name))?.play()
    }

    static func detection(_ d: MissionDetection) {
        play(Pref.string(Pref.alertSound, "Glass"))
        notify(title: "\(Theme.label(forObject: d.name)) #\(d.id ?? 0) confirmed",
               body: String(format: "x %.2f  y %.2f m  ·  %.0f%%", d.x ?? .nan, d.y ?? .nan, (d.conf ?? 0) * 100))
    }

    static func linkLost() {
        if Pref.bool(Pref.linkLostSound, true) { play("Basso") }
        notify(title: "Drone link lost", body: "The drone stopped answering while it was flying.")
    }

    static func requestPermission() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    /// Only when the dashboard is in the background: in front, the banner and sound already say it.
    private static func notify(title: String, body: String) {
        guard Pref.bool(Pref.alertNotify, true), !NSApp.isActive else { return }
        let c = UNMutableNotificationContent()
        c.title = title
        c.body = body
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: UUID().uuidString, content: c, trigger: nil))
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    weak var model: AppModel?

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard Pref.bool(Pref.confirmQuit, true), let m = model?.mission, m.connected, MissionPhase.isAirborne(m.phase)
        else { return .terminateNow }
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = "The drone is still flying"
        alert.informativeText = "Quitting closes the live view and the Return Home and Land controls."
        alert.addButton(withTitle: "Keep Open")
        alert.addButton(withTitle: "Quit")
        return alert.runModal() == .alertSecondButtonReturn ? .terminateNow : .terminateCancel
    }
}
