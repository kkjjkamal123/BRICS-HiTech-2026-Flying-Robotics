import Foundation
import Observation

/// Live battery of the real drone, with or without a mission running.
/// Keeps one SSH command open that streams the flight controller's battery topic (about every 2 s). Nothing is
/// installed on the drone: the stream stops when the dashboard quits.
@MainActor
@Observable
final class BatteryMonitor {
    private(set) var voltage: Double?            // pack voltage, V
    private(set) var fcPercent: Double?          // the flight controller's own estimate, 0...100
    private(set) var updated: Date?

    private var process: Process?
    private var task: Task<Void, Never>?
    private var target = ""

    /// Battery level 0...100: the flight controller's estimate when it gives one, otherwise from the voltage.
    var percent: Double? {
        guard isFresh else { return nil }
        if let p = fcPercent { return p }
        return voltage.map { Self.percent(cellVoltage: $0 / 6) }
    }
    var isFresh: Bool { updated.map { Date().timeIntervalSince($0) < 12 } ?? false }

    /// Resting LiPo curve, per cell. Under load the voltage sags, so in flight this reads a little low.
    static func percent(cellVoltage v: Double) -> Double {
        let curve: [(Double, Double)] = [(3.30, 0), (3.50, 5), (3.60, 12), (3.70, 25), (3.75, 35), (3.80, 45),
                                         (3.85, 55), (3.90, 63), (3.95, 71), (4.00, 79), (4.10, 90), (4.20, 100)]
        if v <= curve[0].0 { return 0 }
        for i in 1..<curve.count where v <= curve[i].0 {
            let (v0, p0) = curve[i - 1], (v1, p1) = curve[i]
            return p0 + (p1 - p0) * (v - v0) / (v1 - v0)
        }
        return 100
    }

    /// Start (or restart for a new address). `sshTarget` nil = stop (simulator selected).
    func follow(sshTarget: String?, password: String) {
        let wanted = sshTarget ?? ""
        guard wanted != target || (process == nil && !wanted.isEmpty) else { return }
        stop()
        target = wanted
        guard !wanted.isEmpty else { return }
        task = Task { [weak self] in
            while !Task.isCancelled {
                await self?.runOnce(sshTarget: wanted, password: password)
                try? await Task.sleep(for: .seconds(6))          // drone off / not reachable: try again quietly
            }
        }
    }

    func stop() {
        task?.cancel()
        task = nil
        process?.terminate()
        process = nil
        voltage = nil
        fcPercent = nil
        updated = nil
    }

    private func runOnce(sshTarget: String, password: String) async {
        let p = Process()
        p.executableURL = DroneLink.ssh
        p.arguments = DroneLink.sshOptions + [sshTarget, "source /opt/ros/noetic/setup.bash; exec rostopic echo -p /mavros/battery"]
        p.environment = ProcessInfo.processInfo.environment.merging(DroneLink.sshEnvironment(password: password)) { _, new in new }
        p.standardInput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        let out = Pipe()
        p.standardOutput = out
        do { try p.run() } catch { return }
        process = p
        var columns: [String] = []
        do {
            for try await line in out.fileHandleForReading.bytes.lines {
                if Task.isCancelled { break }
                let parts = line.split(separator: ",", omittingEmptySubsequences: false).map(String.init)
                if line.hasPrefix("%") {
                    columns = parts
                    continue
                }
                guard let vi = columns.firstIndex(of: "field.voltage"), vi < parts.count, let v = Double(parts[vi]),
                      v > 5, v < 30 else { continue }
                voltage = v
                if let pi = columns.firstIndex(of: "field.percentage"), pi < parts.count, let f = Double(parts[pi]), f > 0, f <= 1 {
                    fcPercent = f * 100
                } else {
                    fcPercent = nil
                }
                updated = .now
            }
        } catch {}
        if p.isRunning { p.terminate() }
        if process === p { process = nil }
    }
}
