import Foundation
import Observation

/// One mission run folder (runs/case1_fire_YYYYMMDD_HHMMSS[_mock]) or a flight-test CSV log.
struct RunSummary: Identifiable, Hashable, Sendable {
    enum Kind: String, Sendable { case mission, hover, roam }

    let id: String
    let kind: Kind
    let folder: URL
    let date: Date
    let isMock: Bool
    let result: String
    let duration: Double
    let distance: Double
    let objects: Int
    let counts: [String: Int]
    let fps: FPSSummary?

    var title: String {
        switch kind {
        case .mission: isMock ? "Case 1 · Simulation" : "Case 1 · Mission flight"
        case .hover: "Hover test"
        case .roam: "ArUco roam test"
        }
    }
    var succeeded: Bool {
        let r = result.lowercased()
        return r.contains("completed") || r.contains("landed") || r.hasPrefix("return")
    }
}

/// fps_summary.json: camera -> span(run/airborne) -> stats
struct FPSSummary: Hashable, Sendable {
    struct Span: Hashable, Sendable { let seconds: Int; let meanFPS: Double; let pctAtLeast10: Double }
    let cameras: [String: [String: Span]]

    func best(camera: String) -> Span? { cameras[camera]?["airborne"] ?? cameras[camera]?["run"] }
}

struct RunObject: Identifiable, Hashable, Sendable {
    let id: Int
    let name: String
    let x: Double
    let y: Double
    let conf: Double
    let hits: Int
    let firstSeen: Date?
    let confirmed: Date?
    let snapshot: URL?
}

struct RunEvent: Identifiable, Hashable, Sendable {
    let id: Int
    let time: Date
    let camera: String
    let name: String
    let conf: Double
    let x: Double
    let y: Double
    let confirmedNow: Bool
}

struct FPSPoint: Identifiable, Hashable, Sendable {
    let id: Int
    let second: Int
    let camera: String
    let fps: Double
}

struct RunDetail: Sendable {
    var objects: [RunObject] = []
    var events: [RunEvent] = []
    var path: [SIMD2<Double>] = []
    var fpsSeries: [FPSPoint] = []
    var snapshots: [URL] = []
    var log: [String] = []
    var area: [Double]?
    var home: [Double]?
    var report: URL?
    var altitude: [(t: Double, z: Double)] = []
}

@MainActor
@Observable
final class RunsStore {
    private(set) var runs: [RunSummary] = []
    private(set) var isLoading = false
    var root: URL

    init(root: URL) { self.root = root }

    var missionRuns: [RunSummary] { runs.filter { $0.kind == .mission } }
    var flightTests: [RunSummary] { runs.filter { $0.kind != .mission } }

    /// Latest Case 1 mission run (real or simulated) - what the judging spec is evaluated against.
    var latestCase1: RunSummary? { runs.first { $0.kind == .mission && $0.id.hasPrefix("case1") && $0.duration > 1 } }

    func reload(then completion: (@MainActor () -> Void)? = nil) {
        isLoading = true
        let root = root
        Task.detached(priority: .userInitiated) {
            let found = RunsStore.scan(root: root)
            await MainActor.run {
                self.runs = found
                self.isLoading = false
                completion?()
            }
        }
    }

    nonisolated static func scan(root: URL) -> [RunSummary] {
        let fm = FileManager.default
        let runsDir = root.appending(path: "runs")
        var out: [RunSummary] = []
        let items = (try? fm.contentsOfDirectory(at: runsDir, includingPropertiesForKeys: [.contentModificationDateKey])) ?? []
        for dir in items where dir.hasDirectoryPath {
            let summaryURL = dir.appending(path: "summary.json")
            guard let data = try? Data(contentsOf: summaryURL),
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
            let name = dir.lastPathComponent
            out.append(RunSummary(
                id: name, kind: .mission, folder: dir,
                date: Self.dateFromName(name) ?? (try? dir.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast,
                isMock: (json["mock"] as? Bool) ?? name.hasSuffix("_mock"),
                result: json["result"] as? String ?? "?",
                duration: (json["duration_s"] as? NSNumber)?.doubleValue ?? 0,
                distance: (json["distance_m"] as? NSNumber)?.doubleValue ?? 0,
                objects: (json["objects"] as? NSNumber)?.intValue ?? 0,
                counts: json["counts"] as? [String: Int] ?? [:],
                fps: Self.parseFPS(json["fps"])))
        }
        // flight-test CSV logs copied back from the drone (runs/flight_logs/*.csv)
        let logs = runsDir.appending(path: "flight_logs")
        for f in (try? fm.contentsOfDirectory(at: logs, includingPropertiesForKeys: nil)) ?? [] where f.pathExtension == "csv" {
            let n = f.deletingPathExtension().lastPathComponent
            let kind: RunSummary.Kind = n.hasPrefix("roam") ? .roam : .hover
            let rows = (try? String(contentsOf: f, encoding: .utf8))?.split(whereSeparator: \.isNewline) ?? []
            let last = rows.last.map(String.init) ?? ""
            let dur = Double(last.split(separator: ",").first ?? "") ?? 0
            out.append(RunSummary(id: "log-" + n, kind: kind, folder: f, date: Self.dateFromName(n) ?? .distantPast, isMock: false,
                                  result: last.contains("False") ? "landed" : "see log", duration: dur, distance: 0,
                                  objects: 0, counts: [:], fps: nil))
        }
        return out.sorted { $0.date > $1.date }
    }

    nonisolated static func dateFromName(_ name: String) -> Date? {
        guard let r = name.range(of: #"\d{8}_\d{6}"#, options: .regularExpression) else { return nil }
        let f = DateFormatter()
        f.dateFormat = "yyyyMMdd_HHmmss"
        f.locale = Locale(identifier: "en_US_POSIX")
        return f.date(from: String(name[r]))
    }

    nonisolated static func parseFPS(_ any: Any?) -> FPSSummary? {
        guard let dict = any as? [String: [String: [String: Any]]], !dict.isEmpty else { return nil }
        var cams: [String: [String: FPSSummary.Span]] = [:]
        for (cam, spans) in dict {
            for (span, v) in spans {
                cams[cam, default: [:]][span] = FPSSummary.Span(
                    seconds: (v["seconds"] as? NSNumber)?.intValue ?? 0,
                    meanFPS: (v["mean_fps"] as? NSNumber)?.doubleValue ?? 0,
                    pctAtLeast10: (v["pct_seconds_ge_10"] as? NSNumber)?.doubleValue ?? 0)
            }
        }
        return FPSSummary(cameras: cams)
    }

    // MARK: Detail

    nonisolated static func loadDetail(_ run: RunSummary) -> RunDetail {
        var d = RunDetail()
        let dir = run.folder
        if run.kind != .mission {
            // flight-test CSV: t, phase, armed, mode, x, y, z, ...
            let text = (try? String(contentsOf: dir, encoding: .utf8)) ?? ""
            let rows = text.split(whereSeparator: \.isNewline).map { $0.split(separator: ",", omittingEmptySubsequences: false).map(String.init) }
            guard let header = rows.first else { return d }
            let ix = header.firstIndex(of: "x"), iy = header.firstIndex(of: "y"), iz = header.firstIndex(of: "z"), it = header.firstIndex(of: "t")
            for r in rows.dropFirst() {
                if let ix, let iy, ix < r.count, iy < r.count, let x = Double(r[ix]), let y = Double(r[iy]), x.isFinite, y.isFinite {
                    d.path.append(SIMD2(x, y))
                }
                if let iz, let it, iz < r.count, let z = Double(r[iz]), let t = Double(r[it]), z.isFinite { d.altitude.append((t, z)) }
            }
            return d
        }
        let iso = DateFormatter()
        iso.locale = Locale(identifier: "en_US_POSIX")
        iso.dateFormat = "yyyy-MM-dd HH:mm:ss"
        // objects.json carries snapshot paths + times; report.csv is the human version
        if let data = try? Data(contentsOf: dir.appending(path: "objects.json")),
           let arr = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] {
            d.objects = arr.enumerated().compactMap { i, o in
                guard let name = o["name"] as? String, let x = (o["x"] as? NSNumber)?.doubleValue,
                      let y = (o["y"] as? NSNumber)?.doubleValue else { return nil }
                let snap = (o["snapshot"] as? String).map { URL(filePath: $0) }
                return RunObject(id: (o["id"] as? NSNumber)?.intValue ?? i + 1, name: name, x: x, y: y,
                                 conf: (o["conf"] as? NSNumber)?.doubleValue ?? 0, hits: (o["hits"] as? NSNumber)?.intValue ?? 0,
                                 firstSeen: (o["first_t"] as? NSNumber).map { Date(timeIntervalSince1970: $0.doubleValue) },
                                 confirmed: (o["confirmed_t"] as? NSNumber).map { Date(timeIntervalSince1970: $0.doubleValue) },
                                 snapshot: snap.flatMap { FileManager.default.fileExists(atPath: $0.path(percentEncoded: false)) ? $0 : dir.appending(path: "snapshots/" + $0.lastPathComponent) })
            }
        }
        if let text = try? String(contentsOf: dir.appending(path: "events.csv"), encoding: .utf8) {
            for (i, line) in text.split(whereSeparator: \.isNewline).dropFirst().enumerated() {
                let c = line.split(separator: ",", omittingEmptySubsequences: false).map(String.init)
                guard c.count >= 10, let t = Double(c[1]) else { continue }
                d.events.append(RunEvent(id: i, time: Date(timeIntervalSince1970: t), camera: c[2], name: c[3],
                                         conf: Double(c[4]) ?? 0, x: Double(c[5]) ?? 0, y: Double(c[6]) ?? 0, confirmedNow: c[9] == "1"))
            }
        }
        if let text = try? String(contentsOf: dir.appending(path: "path.csv"), encoding: .utf8) {
            for line in text.split(whereSeparator: \.isNewline).dropFirst() {
                let c = line.split(separator: ",").compactMap { Double($0) }
                if c.count >= 2 { d.path.append(SIMD2(c[0], c[1])) }
                if c.count >= 3 { d.altitude.append((Double(d.altitude.count), c[2])) }
            }
        }
        if let text = try? String(contentsOf: dir.appending(path: "perf.csv"), encoding: .utf8) {
            var bins: [String: [Int: Int]] = [:]
            var t0: Double?
            for line in text.split(whereSeparator: \.isNewline).dropFirst() {
                let c = line.split(separator: ",").map(String.init)
                guard c.count >= 2, let t = Double(c[0]) else { continue }
                if t0 == nil { t0 = t }
                let sec = Int(t - (t0 ?? t))
                for cam in c[1].split(separator: "+").map(String.init) { bins[cam, default: [:]][sec, default: 0] += 1 }
            }
            var i = 0
            for (cam, b) in bins.sorted(by: { $0.key < $1.key }) {
                for (sec, n) in b.sorted(by: { $0.key < $1.key }) {
                    d.fpsSeries.append(FPSPoint(id: i, second: sec, camera: cam, fps: Double(n)))
                    i += 1
                }
            }
        }
        let snaps = (try? FileManager.default.contentsOfDirectory(at: dir.appending(path: "snapshots"), includingPropertiesForKeys: nil)) ?? []
        d.snapshots = snaps.filter { ["jpg", "png"].contains($0.pathExtension.lowercased()) }.sorted { $0.lastPathComponent < $1.lastPathComponent }
        d.log = ((try? String(contentsOf: dir.appending(path: "log.txt"), encoding: .utf8)) ?? "").split(whereSeparator: \.isNewline).map(String.init)
        // "[plan] survey area [0.0, 0.0, 4.0, 4.0] at z=1.50 ..." -> area rectangle for the map
        if let line = d.log.first(where: { $0.contains("[plan] survey area [") }),
           let start = line.range(of: "area [")?.upperBound,
           let end = line[start...].firstIndex(of: "]") {
            let nums = line[start..<end].split(separator: ",").compactMap { Double($0.trimmingCharacters(in: .whitespaces)) }
            if nums.count == 4 { d.area = nums }
        }
        let report = dir.appending(path: "report.html")
        if FileManager.default.fileExists(atPath: report.path(percentEncoded: false)) { d.report = report }
        return d
    }
}
