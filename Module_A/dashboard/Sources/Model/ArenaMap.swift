import Foundation

/// One floor marker of the arena, in aruco_map metres.
struct ArenaMarker: Hashable, Sendable {
    let id: Int
    let x: Double
    let y: Double
    /// Side length of the black square (m).
    let size: Double
    /// Rotation around the vertical axis (rad), counter-clockwise; 0 = marker top edge faces +y.
    let yaw: Double
}

/// The real arena floor: every ArUco marker of the official map (config/aruco_map_*.txt, the file loaded on the drone)
/// and the printed sheet they sit on. The dashboard maps draw it, so fires and flames appear on the real floor.
struct ArenaMap: Sendable, Equatable {
    let markers: [ArenaMarker]
    /// The printed floor sheet [x0, y0, x1, y1] (m).
    let sheet: [Double]
    let file: String

    /// Marker map file used by the drone. The official venue map wins; any other config/aruco_map*.txt otherwise.
    static func load(toolkit: URL) -> ArenaMap? {
        let cfg = toolkit.appending(path: "config")
        var files = [cfg.appending(path: "aruco_map_750x450_id100.txt")]
        if let all = try? FileManager.default.contentsOfDirectory(atPath: cfg.path(percentEncoded: false)) {
            files += all.filter { $0.hasPrefix("aruco_map") && $0.hasSuffix(".txt") }.sorted().map { cfg.appending(path: $0) }
        }
        for f in files {
            if let text = try? String(contentsOf: f, encoding: .utf8), let m = parse(text, file: f.lastPathComponent) { return m }
        }
        return nil
    }

    /// `id length x y z [rot_z rot_y rot_x]` per line; `# sheet_size_m: W H` (centred on the origin) if present.
    static func parse(_ text: String, file: String) -> ArenaMap? {
        var markers: [ArenaMarker] = []
        var sheetSize: (Double, Double)?
        for raw in text.split(whereSeparator: \.isNewline) {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.hasPrefix("#") {
                if let r = line.range(of: "sheet_size_m:") {
                    let v = line[r.upperBound...].split(separator: " ").compactMap { Double($0) }
                    if v.count >= 2 { sheetSize = (v[0], v[1]) }
                }
                continue
            }
            let p = line.split(whereSeparator: { $0 == " " || $0 == "\t" }).compactMap { Double($0) }
            guard p.count >= 5, abs(p[4]) < 0.3 else { continue }          // floor markers only (z ~ 0)
            markers.append(ArenaMarker(id: Int(p[0]), x: p[2], y: p[3], size: p[1], yaw: p.count >= 6 ? p[5] : 0))
        }
        guard markers.count >= 2 else { return nil }
        let xs = markers.map(\.x), ys = markers.map(\.y)
        let half = (markers.map(\.size).max() ?? 0.25) / 2
        var sheet = [xs.min()! - half - 0.25, ys.min()! - half - 0.25, xs.max()! + half + 0.25, ys.max()! + half + 0.25]
        if let (w, h) = sheetSize, w >= sheet[2] - sheet[0], h >= sheet[3] - sheet[1] {
            let cx = (xs.min()! + xs.max()!) / 2, cy = (ys.min()! + ys.max()!) / 2
            sheet = [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]
        }
        return ArenaMap(markers: markers, sheet: sheet, file: file)
    }

    /// The marker closest to a point, and its distance (m).
    func nearest(_ x: Double, _ y: Double) -> (marker: ArenaMarker, distance: Double)? {
        markers.map { ($0, hypot($0.x - x, $0.y - y)) }.min { $0.1 < $1.1 }
    }

    /// "near marker #122 (0.31 m)" / "on marker #122"
    func describe(_ x: Double, _ y: Double) -> String? {
        guard let n = nearest(x, y) else { return nil }
        return n.distance <= n.marker.size / 2 ? "on marker #\(n.marker.id)"
                                                : String(format: "near marker #%d (%.2f m)", n.marker.id, n.distance)
    }
}
