import Foundation
import Observation

/// Mission settings the operator changes in the dashboard (Mission settings sheet). They are sent to the mission
/// as `--set KEY=VALUE` arguments every time it starts (drone and simulator), so the YAML on the drone never has
/// to be edited. The mission checks them again (common/mission_settings.py) and refuses unsafe values.
@MainActor
@Observable
final class MissionSettings {
    private let defaults = UserDefaults.standard

    /// The venue: official ArUco map aruco_map_750x450_id100 (origin at the field centre), case1_fire.yaml values.
    enum Venue {
        static let markerField: [Double] = [-3.0, -1.5, 3.0, 1.5]       // outer marker centres
        static let area: [Double] = [-2.5, -1.0, 2.5, 1.0]
        static let fence: [Double] = [-3.0, -1.5, 3.0, 1.5]
        static let home: [Double] = [0.0, 0.0]
        static let altitude = 1.5
        static let spacing = 0.8
        static let overlap = 0.3
        static let speed = 0.4
        static let fireC = 100.0
        static let maxAltitude = 3.0                                     // safety.max_altitude
        static let maxTime = 540.0                                       // safety.max_time, s
        /// Thermal camera (survey_camera) 256 x 192, horizontal FOV 56 deg -> vertical FOV from the same focal length.
        static let thermalHFOV = 56.0
        static var thermalVFOV: Double {
            let fx = 128.0 / tan(thermalHFOV / 2 * .pi / 180)
            return 2 * atan(96.0 / fx) * 180 / .pi
        }
        /// The mission refuses a geofence reaching more than this beyond the markers (no position out there).
        static let markerTolerance = 0.3
        /// Bounding box of the marker centres the mission reports (the map loaded on the drone), else the official field.
        static func markerField(from markers: [[Double]]?) -> [Double] {
            let pts = (markers ?? []).filter { $0.count >= 2 }
            guard pts.count >= 2 else { return markerField }
            let xs = pts.map { $0[0] }, ys = pts.map { $0[1] }
            return [xs.min()!, ys.min()!, xs.max()!, ys.max()!]
        }
    }

    /// Scan area [x0, y0, x1, y1] in aruco_map metres: the rectangle the lawn-mower survey covers.
    var area: [Double] { didSet { changed("ms.area", area) } }
    /// Geofence [x0, y0, x1, y1]: leaving it = land at once. Waypoints outside are skipped.
    var fence: [Double] { didSet { changed("ms.fence", fence) } }
    var home: [Double] { didSet { changed("ms.home", home) } }
    var altitude: Double { didSet { changed("ms.altitude", altitude) } }
    var spacingAuto: Bool { didSet { defaults.set(spacingAuto, forKey: "ms.spacingAuto") } }
    var spacing: Double { didSet { changed("ms.spacing", spacing) } }
    var overlap: Double { didSet { changed("ms.overlap", overlap) } }
    var speed: Double { didSet { changed("ms.speed", speed) } }
    var fireC: Double { didSet { changed("ms.fireC", fireC) } }

    /// The floor markers (outer marker centres). The boundary can never be set beyond them.
    var markerField: [Double] = Venue.markerField { didSet { if markerField != oldValue { normalize() } } }
    /// What the last edit had to limit ("Boundary x to limited to 3.00 m: last floor marker"), shown in the sheet.
    private(set) var adjustment: String?

    /// Hard limits of every setting. Values outside are pulled back as they are typed, so nothing unsafe can be set.
    enum Limit {
        static let altitude = 0.5...2.5
        static let spacing = 0.2...2.0
        static let overlap = 0.0...0.6
        static let speed = 0.1...0.8
        static let fireC = 40.0...400.0
        static let minFence = 1.0          // m, smallest boundary side
        static let minArea = 0.5           // m, smallest scan-area side
    }

    @ObservationIgnored private var normalizing = false

    init() {
        area = Self.box(defaults, "ms.area") ?? Venue.area
        fence = Self.box(defaults, "ms.fence") ?? Venue.fence
        home = (defaults.array(forKey: "ms.home") as? [Double]).flatMap { $0.count == 2 ? $0 : nil } ?? Venue.home
        altitude = defaults.object(forKey: "ms.altitude") as? Double ?? Venue.altitude
        spacingAuto = defaults.object(forKey: "ms.spacingAuto") as? Bool ?? true
        spacing = defaults.object(forKey: "ms.spacing") as? Double ?? Venue.spacing
        overlap = defaults.object(forKey: "ms.overlap") as? Double ?? Venue.overlap
        speed = defaults.object(forKey: "ms.speed") as? Double ?? Venue.speed
        fireC = defaults.object(forKey: "ms.fireC") as? Double ?? Venue.fireC
        normalize()                         // values saved by an older version are pulled into the limits too
        adjustment = nil
    }

    private func changed(_ key: String, _ value: Any) {
        guard !normalizing else { return }
        normalize()
    }

    /// Pulls every value into its limits: boundary inside the marker field, scan area and home inside the boundary,
    /// from < to with a minimum size, flight values inside their ranges. Then saves everything.
    private func normalize() {
        normalizing = true
        defer { normalizing = false }
        var notes: [String] = []
        func r(_ v: Double) -> Double { (v * 100).rounded() / 100 }
        func clamp(_ v: Double, _ lo: Double, _ hi: Double, _ what: String) -> Double {
            let c = r(min(max(v.isFinite ? v : lo, lo), max(lo, hi)))
            if abs(c - v) > 0.005 { notes.append(String(format: "%@ limited to %.2f", what, c)) }
            return c
        }
        let m = markerField
        var f = fence.count == 4 ? fence : Venue.fence
        f[0] = clamp(f[0], m[0], m[2] - Limit.minFence, "Boundary x from")
        f[2] = clamp(f[2], f[0] + Limit.minFence, m[2], "Boundary x to")
        f[1] = clamp(f[1], m[1], m[3] - Limit.minFence, "Boundary y from")
        f[3] = clamp(f[3], f[1] + Limit.minFence, m[3], "Boundary y to")
        var a = area.count == 4 ? area : Venue.area
        a[0] = clamp(a[0], f[0], f[2] - Limit.minArea, "Scan area x from")
        a[2] = clamp(a[2], a[0] + Limit.minArea, f[2], "Scan area x to")
        a[1] = clamp(a[1], f[1], f[3] - Limit.minArea, "Scan area y from")
        a[3] = clamp(a[3], a[1] + Limit.minArea, f[3], "Scan area y to")
        var h = home.count == 2 ? home : Venue.home
        h[0] = clamp(h[0], f[0], f[2], "Home x")
        h[1] = clamp(h[1], f[1], f[3], "Home y")
        if fence != f { fence = f }
        if area != a { area = a }
        if home != h { home = h }
        let alt = clamp(altitude, Limit.altitude.lowerBound, Limit.altitude.upperBound, "Altitude")
        if alt != altitude { altitude = alt }
        let sp = clamp(spacing, Limit.spacing.lowerBound, Limit.spacing.upperBound, "Line spacing")
        if sp != spacing { spacing = sp }
        let ov = clamp(overlap, Limit.overlap.lowerBound, Limit.overlap.upperBound, "Overlap")
        if ov != overlap { overlap = ov }
        let v = clamp(speed, Limit.speed.lowerBound, Limit.speed.upperBound, "Speed")
        if v != speed { speed = v }
        let t = clamp(fireC, Limit.fireC.lowerBound, Limit.fireC.upperBound, "Fire temperature")
        if t != fireC { fireC = t }
        adjustment = notes.isEmpty ? nil : notes.joined(separator: " · ")
        defaults.set(fence, forKey: "ms.fence"); defaults.set(area, forKey: "ms.area"); defaults.set(home, forKey: "ms.home")
        defaults.set(altitude, forKey: "ms.altitude"); defaults.set(spacing, forKey: "ms.spacing")
        defaults.set(overlap, forKey: "ms.overlap"); defaults.set(speed, forKey: "ms.speed"); defaults.set(fireC, forKey: "ms.fireC")
    }

    private static func box(_ d: UserDefaults, _ key: String) -> [Double]? {
        (d.array(forKey: key) as? [Double]).flatMap { $0.count == 4 ? $0 : nil }
    }

    func resetToVenue() {
        fence = Venue.fence; area = Venue.area; home = Venue.home
        altitude = Venue.altitude; spacingAuto = true; spacing = Venue.spacing; overlap = Venue.overlap
        speed = Venue.speed; fireC = Venue.fireC
    }

    var isVenueDefault: Bool {
        func same(_ a: [Double], _ b: [Double]) -> Bool { zip(a, b).allSatisfy { abs($0 - $1) < 0.005 } }
        return same(area, Venue.area) && same(fence, Venue.fence) && same(home, Venue.home)
            && same([altitude, overlap, speed, fireC], [Venue.altitude, Venue.overlap, Venue.speed, Venue.fireC]) && spacingAuto
    }

    /// Fence = the whole marker field (the widest boundary the mission accepts).
    func fenceToMarkerField(_ field: [Double]) { markerField = field; fence = field }
    /// Scan area = fence minus a margin on every side.
    func areaInsideFence(margin: Double) {
        area = [fence[0] + margin, fence[1] + margin, fence[2] - margin, fence[3] - margin]
    }

    // MARK: survey geometry (same maths as mission_base.survey_waypoints / geometry.lawnmower)

    /// Ground strip the thermal camera sees at the survey altitude: (across the line, along the line) in metres.
    var footprint: (width: Double, height: Double) {
        (2 * altitude * tan(Venue.thermalHFOV / 2 * .pi / 180), 2 * altitude * tan(Venue.thermalVFOV / 2 * .pi / 180))
    }
    /// What `step: auto` gives: the narrower side of the camera view minus the overlap.
    var autoSpacing: Double { max(0.2, min(footprint.width, footprint.height) * (1 - overlap)) }
    var effectiveSpacing: Double { spacingAuto ? autoSpacing : spacing }

    /// y of every survey line. Lines are spread evenly from y0 to y1, at most `effectiveSpacing` apart.
    var surveyLines: [Double] {
        let y0 = area[1], y1 = area[3]
        guard y1 > y0, effectiveSpacing > 0 else { return [y0] }
        let n = max(1, Int(ceil((y1 - y0) / effectiveSpacing - 1e-9)))
        return (0...n).map { y0 + (y1 - y0) * Double($0) / Double(n) }
    }
    /// Real gap between lines after spreading them evenly (can be a bit less than the setting).
    var actualSpacing: Double {
        let l = surveyLines
        return l.count > 1 ? l[1] - l[0] : 0
    }
    /// Survey path length and the time it takes at `speed` (straight lines, no inspection hovers).
    var surveyLength: Double {
        let l = surveyLines
        return Double(l.count) * (area[2] - area[0]) + (l.last! - l.first!)
    }
    var surveySeconds: Double { surveyLength / max(0.05, speed) }

    // MARK: checks

    /// Blocking problems: the mission would refuse them (or fly something unsafe). Run mission stays disabled.
    func problems(markerField: [Double]) -> [String] {
        var p: [String] = []
        let tol = 0.05
        if area[0] >= area[2] || area[1] >= area[3] { p.append("Scan area: x from must be less than x to, and y from less than y to.") }
        if fence[0] >= fence[2] || fence[1] >= fence[3] { p.append("Boundary: x from must be less than x to, and y from less than y to.") }
        if area[0] < fence[0] - tol || area[1] < fence[1] - tol || area[2] > fence[2] + tol || area[3] > fence[3] + tol {
            p.append("The scan area goes outside the boundary. Waypoints out there would be skipped.")
        }
        if !(fence[0] - tol...fence[2] + tol).contains(home[0]) || !(fence[1] - tol...fence[3] + tol).contains(home[1]) {
            p.append("Home is outside the boundary.")
        }
        let over = [markerField[0] - fence[0], markerField[1] - fence[1], fence[2] - markerField[2], fence[3] - markerField[3]].max() ?? 0
        if over > Venue.markerTolerance {
            p.append(String(format: "The boundary reaches %.2f m past the floor markers. Beyond the markers the drone has no position, so the drone refuses to fly.", over))
        }
        if altitude > Venue.maxAltitude - 0.2 { p.append(String(format: "Altitude must stay at least 0.2 m below the %.1f m safety ceiling.", Venue.maxAltitude)) }
        if altitude < 0.5 { p.append("Altitude must be at least 0.5 m.") }
        if !spacingAuto, !(0.2...3.0).contains(spacing) { p.append("Line spacing must be 0.2 to 3.0 m.") }
        if !(30...1000).contains(fireC) { p.append("Fire temperature must be 30 to 1000 °C.") }
        return p
    }

    /// Not blocking, but worth knowing before take-off.
    var warnings: [String] {
        var w: [String] = []
        let strip = min(footprint.width, footprint.height)
        if effectiveSpacing > strip {
            w.append(String(format: "Gaps: the lines are %.2f m apart but the thermal camera only sees a %.2f m strip at %.1f m. A small heat source between lines can be missed.",
                            effectiveSpacing, strip, altitude))
        }
        if surveySeconds > Venue.maxTime * 0.8 {
            w.append(String(format: "The survey alone takes about %.0f s; the mission lands at %.0f s (time limit). Use wider spacing, a smaller area or more speed.",
                            surveySeconds, Venue.maxTime))
        }
        if altitude < 1.0 { w.append("Below 1 m the cameras see a small patch and the floor markers can drop out of view.") }
        if fireC < 60 { w.append(String(format: "%.0f °C is close to warm laptops, people and batteries: expect false fire alarms.", fireC)) }
        return w
    }

    // MARK: command line

    private func n(_ v: Double) -> String {
        var s = String(format: "%.2f", v)
        while s.hasSuffix("0") { s.removeLast() }
        if s.hasSuffix(".") { s.removeLast() }
        return s == "-0" ? "0" : s
    }
    private func list(_ v: [Double]) -> String { "[" + v.map(n).joined(separator: ",") + "]" }

    /// `--set` arguments for drone/case1_fire.py. Every value is sent, so the run never depends on the YAML defaults.
    var setArguments: [String] {
        let pairs = ["area=\(list(area))", "safety.fence=\(list(fence))", "home=\(list(home))",
                     "altitude=\(n(altitude))", spacingAuto ? "step=auto" : "step=\(n(spacing))",
                     "overlap=\(n(overlap))", "speed=\(n(speed))", "fire_c=\(n(fireC))"]
        return pairs.flatMap { ["--set", $0] }
    }

    /// Short text for cards: "5.0 × 2.0 m · 1.5 m · auto 0.84 m · ≥ 100 °C"
    var summary: String {
        String(format: "%.1f × %.1f m · alt %.1f m · lines %@%.2f m · fire ≥ %.0f °C",
               area[2] - area[0], area[3] - area[1], altitude, spacingAuto ? "auto " : "", effectiveSpacing, fireC)
    }
}
