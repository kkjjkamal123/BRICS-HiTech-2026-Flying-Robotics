import Foundation
import Observation

enum MissionSource: String, CaseIterable, Identifiable {
    case drone, simulator
    var id: String { rawValue }
    var title: String { self == .drone ? "TECHNIC 6S" : "Simulator" }
}

/// User-editable settings, persisted in UserDefaults.
@MainActor
@Observable
final class DashboardSettings {
    private let defaults = UserDefaults.standard

    var droneHost: String { didSet { defaults.set(droneHost, forKey: "droneHost") } }
    var sshUser: String { didSet { defaults.set(sshUser, forKey: "sshUser") } }
    /// The drone's login password (TECHNIC default: orangepi). Used automatically, so no pairing step is needed.
    var sshPassword: String { didSet { defaults.set(sshPassword, forKey: "sshPassword") } }
    var missionPort: Int { didSet { defaults.set(missionPort, forKey: "missionPort") } }
    var videoPort: Int { didSet { defaults.set(videoPort, forKey: "videoPort") } }
    var simulatorPort: Int { didSet { defaults.set(simulatorPort, forKey: "simulatorPort") } }
    var missionSource: MissionSource { didSet { defaults.set(missionSource.rawValue, forKey: "missionSource") } }
    var toolkitPath: String { didSet { defaults.set(toolkitPath, forKey: "toolkitPath") } }
    var teamName: String { didSet { defaults.set(teamName, forKey: "teamName") } }
    /// Addresses used before (newest first), offered as quick-fill in the address popover.
    private(set) var recentHosts: [String] { didSet { defaults.set(recentHosts, forKey: "recentHosts") } }

    init() {
        droneHost = defaults.string(forKey: "droneHost") ?? "10.42.0.1"
        recentHosts = defaults.stringArray(forKey: "recentHosts") ?? []
        sshUser = defaults.string(forKey: "sshUser") ?? "orangepi"
        sshPassword = defaults.string(forKey: "sshPassword") ?? "orangepi"
        missionPort = DashboardSettings.int(defaults, "missionPort") ?? 8090
        videoPort = DashboardSettings.int(defaults, "videoPort") ?? 8080
        simulatorPort = DashboardSettings.int(defaults, "simulatorPort") ?? 8095
        missionSource = MissionSource(rawValue: defaults.string(forKey: "missionSource") ?? "") ?? .drone
        toolkitPath = defaults.string(forKey: "toolkitPath") ?? DashboardSettings.detectToolkit()?.path(percentEncoded: false) ?? ""
        teamName = defaults.string(forKey: "teamName") ?? "Chennai Institute of Technology"
    }

    /// Reads an Int that may come from UserDefaults (Int) or a launch argument like `-simulatorPort 8097` (String).
    private static func int(_ d: UserDefaults, _ key: String) -> Int? {
        if let i = d.object(forKey: key) as? Int { return i }
        if let s = d.string(forKey: key), let i = Int(s) { return i }
        return nil
    }

    func rememberHost(_ host: String) {
        recentHosts = Array(([host] + recentHosts.filter { $0 != host }).prefix(5))
    }

    /// Whatever the user typed or pasted ("http://10.1.2.3:8090/", "orangepi@10.1.2.3", " 10.1.2.3 ") -> bare host.
    /// Only letters, digits, dots and dashes survive, because the host ends up in ssh/scp commands.
    static func cleanHost(_ raw: String) -> String {
        var s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if let r = s.range(of: "://") { s = String(s[r.upperBound...]) }
        if let at = s.lastIndex(of: "@") { s = String(s[s.index(after: at)...]) }
        if let slash = s.firstIndex(of: "/") { s = String(s[..<slash]) }
        if let colon = s.firstIndex(of: ":") { s = String(s[..<colon]) }
        s = s.replacingOccurrences(of: ",", with: ".")
        return String(s.unicodeScalars.filter { $0.isASCII && (CharacterSet.alphanumerics.contains($0) || $0 == "." || $0 == "-") }.map(Character.init))
    }

    var toolkitRoot: URL { URL(filePath: toolkitPath, directoryHint: .isDirectory) }
    var pythonURL: URL { toolkitRoot.appending(path: ".venv/bin/python") }
    var sshTarget: String { "\(sshUser)@\(droneHost)" }

    /// The toolkit folder: the app normally lives inside it (brics_toolkit/BRICS Dashboard.app).
    static func detectToolkit() -> URL? {
        let fm = FileManager.default
        var candidates: [URL] = []
        if let env = ProcessInfo.processInfo.environment["BRICS_ROOT"] { candidates.append(URL(filePath: env)) }
        var dir = Bundle.main.bundleURL
        for _ in 0..<6 {
            dir = dir.deletingLastPathComponent()
            candidates.append(dir)
        }
        candidates.append(fm.homeDirectoryForCurrentUser.appending(path: "Documents/Projects/Claude/russia/brics_toolkit"))
        return candidates.first { fm.fileExists(atPath: $0.appending(path: "drone/mission_base.py").path(percentEncoded: false)) }
    }
}
