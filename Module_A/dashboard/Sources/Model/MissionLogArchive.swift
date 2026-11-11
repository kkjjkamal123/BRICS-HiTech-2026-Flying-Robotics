import Foundation

/// Every mission log also lives on the Desktop: ~/Desktop/BRICS Mission Logs mirrors toolkit/runs (drone missions,
/// simulations, flight-test CSVs in flight_logs/, recordings). rsync only adds and updates, nothing is deleted there.
enum MissionLogArchive {
    static var folder: URL {
        FileManager.default.homeDirectoryForCurrentUser.appending(path: "Desktop/BRICS Mission Logs")
    }

    /// Shell snippet that copies `runsDir` into the Desktop folder (used at the end of a drone log fetch).
    static func mirrorCommand(runsDir: String) -> String {
        let desk = folder.path(percentEncoded: false)
        return "mkdir -p '\(desk)' && /usr/bin/rsync -a --exclude '.DS_Store' '\(runsDir)/' '\(desk)/' && echo \"logs saved to \(desk)\""
    }

    /// Copy the local runs folder to the Desktop in the background.
    static func mirror(runsDir: URL) {
        let p = Process()
        p.executableURL = URL(filePath: "/bin/bash")
        p.arguments = ["-c", mirrorCommand(runsDir: runsDir.path(percentEncoded: false))]
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        try? p.run()
    }
}
