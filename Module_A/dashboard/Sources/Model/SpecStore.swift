import Foundation
import Observation

enum Verdict: String, Sendable {
    case pass, fail, pending, manual

    var title: String {
        switch self {
        case .pass: "PASS"
        case .fail: "FAIL"
        case .pending: "NOT MEASURED"
        case .manual: "EXPERT CHECK"
        }
    }
}

struct SpecItem: Identifiable, Sendable {
    let id: String
    let title: String
    let unit: String
    let threshold: String
    let method: String
    let evidence: String
    var measured: String = "—"
    var verdict: Verdict = .pending
}

struct SpecModule: Identifiable, Sendable {
    let id: String
    let title: String
    let contents: String
    let function: String
    let criterion: String
    let status: String
    let done: Bool
}

struct ChecklistItem: Identifiable, Sendable {
    let id: String
    let text: String
}

/// The approved technical specification (deliverables/case1_forest_fire/04_Test_Programme.md) as data,
/// auto-evaluated from the latest mission run where the logs allow it.
@MainActor
@Observable
final class SpecStore {
    private(set) var items: [SpecItem] = SpecStore.definitions
    let modules: [SpecModule] = SpecStore.moduleDefinitions
    let checklist: [ChecklistItem] = SpecStore.checklistDefinitions
    private(set) var checked: Set<String>
    private(set) var evaluatedRun: String?

    /// Expert tape measurements of the true target positions (C5), keyed by object id.
    var truePositions: [Int: (x: Double, y: Double)] = [:] {
        didSet {   // persist the expert's tape measurements across relaunches
            let flat = truePositions.reduce(into: [String: [Double]]()) { $0[String($1.key)] = [$1.value.x, $1.value.y] }
            UserDefaults.standard.set(flat, forKey: "truePositions")
        }
    }

    init() {
        checked = Set(UserDefaults.standard.stringArray(forKey: "checklist") ?? [])
        if let flat = UserDefaults.standard.dictionary(forKey: "truePositions") as? [String: [Double]] {
            truePositions = flat.reduce(into: [:]) { if let k = Int($1.key), $1.value.count == 2 { $0[k] = ($1.value[0], $1.value[1]) } }
        }
    }

    var checklistProgress: Double { checklist.isEmpty ? 0 : Double(checked.count) / Double(checklist.count) }
    var passCount: Int { items.filter { $0.verdict == .pass }.count }

    func toggle(_ id: String) {
        if checked.contains(id) { checked.remove(id) } else { checked.insert(id) }
        UserDefaults.standard.set(Array(checked), forKey: "checklist")
    }

    func resetChecklist() {
        checked.removeAll()
        UserDefaults.standard.set([String](), forKey: "checklist")
    }

    func evaluate(latest run: RunSummary?) {
        var it = SpecStore.definitions
        guard let run else { items = it; return }
        evaluatedRun = run.id
        let detail = RunsStore.loadDetail(run)
        func set(_ id: String, _ measured: String, _ v: Verdict) {
            if let i = it.firstIndex(where: { $0.id == id }) { it[i].measured = measured; it[i].verdict = v }
        }
        // C1 route: mission completed without abort
        let r = run.result.lowercased()
        set("C1", r.contains("completed") ? "route completed" : run.result, r.contains("completed") ? .pass : .fail)
        // C2 mAP: from the trained fire model metrics
        if let m = AIModelStore.readMAP50(root: DashboardSettings.detectToolkit()) {
            set("C2", String(format: "mAP@0.5 %.3f", m), m >= 0.85 ? .pass : .fail)
        }
        // C3 extra object
        let trees = run.counts["tree"] ?? 0
        set("C3", "\(trees) tree(s) mapped", trees >= 1 ? .pass : .fail)
        // C4 FPS on the thermal stream
        if let span = run.fps?.best(camera: "thermal") ?? run.fps?.best(camera: "rgb") {
            set("C4", String(format: "%.0f%% of %ds ≥ 10 FPS (mean %.1f)", span.pctAtLeast10, span.seconds, span.meanFPS),
                span.pctAtLeast10 > 90 ? .pass : .fail)
        }
        // C5 coordinates: needs the expert's tape measurements
        let errors = detail.objects.compactMap { o -> Double? in
            guard let t = truePositions[o.id] else { return nil }
            return hypot(o.x - t.x, o.y - t.y)
        }
        if let worst = errors.max() {
            set("C5", String(format: "max error %.2f m (%d obj)", worst, errors.count), worst <= 0.5 ? .pass : .fail)
        } else {
            set("C5", "\(detail.objects.count) object\(detail.objects.count == 1 ? "" : "s") - enter true positions", .manual)
        }
        // C6 map latency: shown with timestamps in the UI; measured from the screen recording
        set("C6", detail.events.contains(where: \.confirmedNow) ? "timestamps logged" : "no detections", .manual)
        // C7 return on command: log "[ui] operator pressed RETURN" -> "[phase] RETURN"
        if let press = detail.log.firstIndex(where: { $0.contains("operator pressed RETURN") }) {
            let t0 = SpecStore.clock(detail.log[press])
            if let ph = detail.log[press...].first(where: { $0.contains("[phase] RETURN") }), let t0, let t1 = SpecStore.clock(ph) {
                let dt = t1 - t0
                set("C7", String(format: "reaction %.0f s", dt), dt <= 2 ? .pass : .fail)
            }
        } else {
            set("C7", "RETURN not pressed in this run", .pending)
        }
        items = it
    }

    /// "12:34:56 [phase] ..." -> seconds of day
    nonisolated static func clock(_ line: String) -> Double? {
        let p = line.prefix(8).split(separator: ":").compactMap { Double($0) }
        return p.count == 3 ? p[0] * 3600 + p[1] * 60 + p[2] : nil
    }

    // MARK: Definitions (from 04_Test_Programme.md)

    static let definitions: [SpecItem] = [
        SpecItem(id: "C1", title: "Autonomous route flight", unit: "% waypoints", threshold: "100 % within 0.25 m",
                 method: "Planned waypoints vs flown path, no RC input", evidence: "log.txt · path.csv · video"),
        SpecItem(id: "C2", title: "Flame detection in thermal images", unit: "mAP@0.5", threshold: "≥ 0.85",
                 method: "Thermal frames of the scored flight, expert-checked ground truth, Ultralytics val", evidence: "frames/ · labels · mAP printout"),
        SpecItem(id: "C3", title: "Additional object (trees)", unit: "detected / present", threshold: "every tree in the area, correct class",
                 method: "Confirmed `tree` entries in objects.json vs the trees in the field", evidence: "objects.json · events.csv · snapshots"),
        SpecItem(id: "C4", title: "Onboard NPU processing rate", unit: "FPS per 1-s interval", threshold: "≥ 10 FPS for > 90 % of airborne time",
                 method: "Every perception cycle timestamped in perf.csv", evidence: "perf.csv · fps_summary.json"),
        SpecItem(id: "C5", title: "Object coordinate accuracy", unit: "m (horizontal)", threshold: "≤ 0.5 m for every object",
                 method: "Tape from the marker-map origin vs report.csv", evidence: "report.csv · tape photo"),
        SpecItem(id: "C6", title: "Live map display (type + timestamp)", unit: "s after confirmation", threshold: "≤ 2 s",
                 method: "Screen recording vs confirmation time in events.csv", evidence: "events.csv · screen recording"),
        SpecItem(id: "C7", title: "Autonomous return on command", unit: "s · m", threshold: "reaction ≤ 2 s · landing ≤ 0.5 m",
                 method: "log.txt: RETURN pressed → phase RETURN; landing vs home pad", evidence: "log.txt · path.csv · video"),
    ]

    static let moduleDefinitions: [SpecModule] = [
        SpecModule(id: "M1", title: "Flight & navigation", contents: "PX4 · SKYRIS simple_offboard · ArUco map + optical flow + rangefinder · mission planner & safety layer",
                   function: "Autonomous take-off to 1.5 m, 5 s position hold, landing (hover_test.py)",
                   criterion: "1.5 ± 0.15 m · drift ≤ 0.2 m · lands and disarms without RC", status: "Flown 9 Nov 2026", done: true),
        SpecModule(id: "M2", title: "Thermal perception", contents: "TR256i °C stream · ≥ 100 °C rule · thermal YOLO + RGB flame YOLO (RKNN NPU) · tree detector · tracker",
                   function: "Bench: drone held still 1.5 m above the lit mock campfire",
                   criterion: "fire confirmed ≤ 3 s · conf ≥ 0.5 · ≥ 10 FPS", status: "Needs trained fire model", done: false),
        SpecModule(id: "M3", title: "Ground station & logging", contents: "Operator UI :8090 · this dashboard · events.csv · report",
                   function: "Detection appears on the live map; commands acknowledged",
                   criterion: "type, X/Y, time on map · row in events.csv · command ≤ 1 s", status: "Verified in simulation", done: true),
    ]

    static let checklistDefinitions: [ChecklistItem] = [
        ChecklistItem(id: "props", text: "Props secure · battery ≥ 3.8 V/cell · frame and cables secured"),
        ChecklistItem(id: "kill", text: "RC on · kill switch on channel 8 tested (motors stop)"),
        ChecklistItem(id: "wifi", text: "Slider on AP · laptop on technic-xxxx · drone clock synchronised"),
        ChecklistItem(id: "thermal", text: "thermal_probe.py shows the thermal camera · max °C reacts to a hand"),
        ChecklistItem(id: "aruco", text: "Venue ArUco map loaded · aruco_map position valid over the field"),
        ChecklistItem(id: "dry", text: "hover_test.py --dry-run passes"),
        ChecklistItem(id: "config", text: "Mission config has measured area + home · UI shows live video and FPS"),
        ChecklistItem(id: "video", text: "Continuous video recording of the attempt started"),
    ]
}
