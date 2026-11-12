import SwiftUI

struct MapObject: Identifiable, Hashable {
    let id: String
    let label: String
    let name: String
    let x: Double
    let y: Double
    var time: String?
}

/// Top-down instrument view of the flight area in aruco_map metres (x right, y up): faint grid, dashed survey
/// area, home pad, breadcrumb trail, drone with heading and detected objects with collision-free labels.
///
/// Rendering is split so that only what changes is redrawn: the static layers live in one `Canvas`,
/// pins/labels/drone are light views, and the cursor readout owns its own hover state.
struct FieldMap: View {
    var area: [Double]?
    var home: [Double]?
    /// Floor marker centres [[x, y], ...]: the real arena.
    var markers: [[Double]] = []
    var drone: SIMD2<Double>?
    var heading: Double?
    var track: [SIMD2<Double>] = []
    var objects: [MapObject] = []
    var showLabels = true
    /// The real arena floor (marker map). Drawn as the printed sheet with every ArUco marker, so detections sit on
    /// the floor as it is; labels and tooltips name the nearest marker.
    var arena: ArenaMap?

    @State private var hovered: String?

    var body: some View {
        GeometryReader { geo in
            let frame = WorldFrame(bounds: bounds, size: geo.size, insets: Self.insets)
            let layout = LabelLayout(objects: showLabels ? objects : [], frame: frame, area: area, home: home, arena: arena)
            ZStack(alignment: .topLeading) {
                MapCanvas(layer: .floor, area: area, home: home, markers: markers, track: [], fadeTrail: false, frame: frame, arena: arena)
                    .equatable()
                MapCanvas(layer: .track, area: nil, home: home, track: track, fadeTrail: drone != nil, frame: frame, arena: arena)
                CursorReadout(frame: frame, arena: arena)
                ForEach(layout.placements) { p in
                    PinLabel(placement: p, highlighted: hovered == p.id)
                        .zIndex(hovered == p.id ? 2 : 1)
                }
                ForEach(objects) { o in
                    ObjectPin(name: o.name, highlighted: hovered == o.id)
                        .position(frame.point(o.x, o.y))
                        .onHover { inside in
                            withAnimation(.snappy(duration: 0.18)) { hovered = inside ? o.id : (hovered == o.id ? nil : hovered) }
                        }
                        .help(pinHelp(o))
                        .transition(.scale(scale: 0.3).combined(with: .opacity))
                        .zIndex(3)
                }
                if let drone {
                    DroneGlyph(heading: heading ?? Self.heading(from: track), onFloor: arena != nil)
                        .position(frame.point(drone.x, drone.y))
                        .animation(.smooth(duration: 0.45), value: drone)
                        .zIndex(4)
                }
            }
            .animation(.snappy(duration: 0.3), value: layout.placements)
            .animation(.spring(duration: 0.45, bounce: 0.15), value: objects)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Flight area map with \(objects.count) detected objects")
    }

    /// Room around the plotted world for the axis labels.
    static let insets = EdgeInsets(top: 6, leading: 20, bottom: 16, trailing: 6)

    private func pinHelp(_ o: MapObject) -> String {
        var s = String(format: "%@  x %.2f  y %.2f m", o.label, o.x, o.y)
        if let near = arena?.describe(o.x, o.y) { s += "  ·  " + near }
        if let t = o.time { s += "  ·  \(t)" }
        return s
    }

    /// Everything that should be visible, with a 0.6 m margin.
    private var bounds: CGRect {
        var xs: [Double] = [0, 1], ys: [Double] = [0, 1]
        if let s = arena?.sheet { xs += [s[0], s[2]]; ys += [s[1], s[3]] }
        if let a = area, a.count == 4 { xs += [a[0], a[2]]; ys += [a[1], a[3]] }
        if let h = home, h.count >= 2 { xs.append(h[0]); ys.append(h[1]) }
        for m in markers where m.count >= 2 { xs.append(m[0]); ys.append(m[1]) }
        if let d = drone { xs.append(d.x); ys.append(d.y) }
        for p in track { xs.append(p.x); ys.append(p.y) }
        for o in objects { xs.append(o.x); ys.append(o.y) }
        let m = arena == nil ? 0.6 : 0.12                  // the floor sheet already has its own margin
        let x0 = (xs.min() ?? 0) - m, x1 = (xs.max() ?? 1) + m
        let y0 = (ys.min() ?? 0) - m, y1 = (ys.max() ?? 1) + m
        return CGRect(x: x0, y: y0, width: x1 - x0, height: y1 - y0)
    }

    /// Direction of the last real movement (math convention: radians from +x, counter-clockwise).
    static func heading(from track: [SIMD2<Double>]) -> Double? {
        guard let last = track.last else { return nil }
        for p in track.reversed().dropFirst() {
            let d = last - p
            if d.x * d.x + d.y * d.y > 0.0025 { return atan2(d.y, d.x) }
        }
        return nil
    }
}

/// aruco_map metres <-> view points, preserving aspect ratio, centred inside `insets`.
struct WorldFrame: Equatable {
    let bounds: CGRect
    let size: CGSize
    var insets = EdgeInsets()

    private var plot: CGRect {
        CGRect(x: insets.leading, y: insets.top,
               width: max(1, size.width - insets.leading - insets.trailing),
               height: max(1, size.height - insets.top - insets.bottom))
    }
    private var scale: CGFloat { min(plot.width / bounds.width, plot.height / bounds.height) }
    private var offset: CGPoint {
        CGPoint(x: plot.minX + (plot.width - bounds.width * scale) / 2,
                y: plot.minY + (plot.height - bounds.height * scale) / 2)
    }

    /// The world bounds as a rect in view points.
    var worldRect: CGRect {
        CGRect(x: offset.x, y: offset.y, width: bounds.width * scale, height: bounds.height * scale)
    }
    var pointsPerMetre: CGFloat { scale }

    func point(_ x: Double, _ y: Double) -> CGPoint {
        CGPoint(x: offset.x + (x - bounds.minX) * scale, y: offset.y + (bounds.maxY - y) * scale)
    }

    func world(_ p: CGPoint) -> SIMD2<Double> {
        SIMD2((p.x - offset.x) / scale + bounds.minX, bounds.maxY - (p.y - offset.y) / scale)
    }
}

// MARK: - Static layers

/// Two instances: the floor (redrawn only when the frame or arena changes) and the trail + home pad on top.
private struct MapCanvas: View, Equatable {
    enum Layer { case floor, track }
    let layer: Layer
    let area: [Double]?
    let home: [Double]?
    var markers: [[Double]] = []
    let track: [SIMD2<Double>]
    let fadeTrail: Bool
    let frame: WorldFrame
    var arena: ArenaMap?

    /// Printed floor sheet and marker ink (slightly dimmed so the light floor does not glare in the dark UI).
    static let floor = Color(hex: 0xD8D5CE)
    static let ink = Color(hex: 0x16181B)
    static let trackOnFloor = Color(hex: 0x1F5FBF)
    private var onFloor: Bool { arena != nil }

    var body: some View {
        Canvas { ctx, _ in
            switch layer {
            case .floor:
                drawGrid(ctx)
                if let arena { drawFloor(ctx, arena) } else { drawMarkers(ctx) }
                drawArea(ctx)
            case .track:
                drawTrack(ctx)
                drawHome(ctx)
            }
        }
    }

    /// The real floor: the printed sheet, every ArUco marker with its true pattern / size / position, metre lines and
    /// the marker IDs (when big enough to read).
    private func drawFloor(_ ctx: GraphicsContext, _ arena: ArenaMap) {
        let f = frame, k = f.pointsPerMetre, s = arena.sheet
        let a = f.point(s[0], s[3]), b = f.point(s[2], s[1])
        let sheet = CGRect(x: a.x, y: a.y, width: b.x - a.x, height: b.y - a.y)
        ctx.fill(Path(roundedRect: sheet, cornerRadius: 3), with: .color(Self.floor))
        // metre lines and the axes through the origin, faint, under the markers
        var lines = Path(), axes = Path()
        var x = s[0].rounded(.up)
        while x <= s[2] + 1e-9 {
            let px = f.point(x, 0).x
            if abs(x) < 1e-9 { axes.addLines([CGPoint(x: px, y: sheet.minY), CGPoint(x: px, y: sheet.maxY)]) }
            else { lines.addLines([CGPoint(x: px, y: sheet.minY), CGPoint(x: px, y: sheet.maxY)]) }
            x += 1
        }
        var y = s[1].rounded(.up)
        while y <= s[3] + 1e-9 {
            let py = f.point(0, y).y
            if abs(y) < 1e-9 { axes.move(to: CGPoint(x: sheet.minX, y: py)); axes.addLine(to: CGPoint(x: sheet.maxX, y: py)) }
            else { lines.move(to: CGPoint(x: sheet.minX, y: py)); lines.addLine(to: CGPoint(x: sheet.maxX, y: py)) }
            y += 1
        }
        ctx.stroke(lines, with: .color(.black.opacity(0.07)), lineWidth: 0.75)
        ctx.stroke(axes, with: .color(.black.opacity(0.16)), style: StrokeStyle(lineWidth: 0.75, dash: [3, 3]))
        // markers: black square, then the white cells of its 4 x 4 code (row 0 = top edge, facing +y at yaw 0)
        var ink = Path(), paper = Path()
        for m in arena.markers {
            let c = f.point(m.x, m.y), side = m.size * k, cell = side / 6
            let t = CGAffineTransform(translationX: c.x, y: c.y).rotated(by: -m.yaw)     // view y points down
            ink.addRect(CGRect(x: -side / 2, y: -side / 2, width: side, height: side), transform: t)
            guard cell >= 0.8 else { continue }                                         // too small: plain square
            for r in 0..<4 {
                for col in 0..<4 where ArucoDictionary.isWhite(m.id, row: r, col: col) {
                    paper.addRect(CGRect(x: -side / 2 + CGFloat(col + 1) * cell, y: -side / 2 + CGFloat(r + 1) * cell,
                                         width: cell, height: cell), transform: t)
                }
            }
        }
        ctx.fill(ink, with: .color(Self.ink))
        ctx.fill(paper, with: .color(Self.floor))
        if k * 0.25 >= 15 {                                 // marker IDs once a marker is ~15 pt wide
            for m in arena.markers {
                let p = f.point(m.x, m.y - m.size / 2)
                ctx.draw(Text("\(m.id)").font(Theme.code(max(7, min(10, k * 0.07)), .medium)).foregroundStyle(Color.black.opacity(0.45)),
                         at: CGPoint(x: p.x, y: p.y + 1.5), anchor: .top)
            }
        }
        ctx.stroke(Path(roundedRect: sheet, cornerRadius: 3), with: .color(.white.opacity(0.18)), lineWidth: 0.75)
    }

    private func drawGrid(_ ctx: GraphicsContext) {
        let f = frame, b = f.bounds, r = f.worldRect
        var minor = Path(), major = Path()
        var x = (b.minX * 2).rounded(.up) / 2
        while x <= b.maxX + 1e-9 {
            let px = f.point(x, 0).x
            let line = [CGPoint(x: px, y: r.minY), CGPoint(x: px, y: r.maxY)]
            if abs(x.rounded() - x) < 1e-6 { major.addLines(line) } else { minor.addLines(line) }
            x += 0.5
        }
        var y = (b.minY * 2).rounded(.up) / 2
        while y <= b.maxY + 1e-9 {
            let py = f.point(0, y).y
            let line = [CGPoint(x: r.minX, y: py), CGPoint(x: r.maxX, y: py)]
            if abs(y.rounded() - y) < 1e-6 { major.addLines(line) } else { minor.addLines(line) }
            y += 0.5
        }
        ctx.stroke(minor, with: .color(.white.opacity(0.03)), lineWidth: 0.5)
        ctx.stroke(major, with: .color(.white.opacity(0.065)), lineWidth: 0.75)
        ctx.stroke(Path(r), with: .color(.white.opacity(0.07)), lineWidth: 0.75)

        // axis labels sit outside the plotted rect, so they never collide with content
        let xs = Array(Int(b.minX.rounded(.up))...Int(b.maxX.rounded(.down)))
        let step = labelStep(count: xs.count, span: r.width)
        for gx in xs where gx % step == 0 {
            let label = gx == xs.last(where: { $0 % step == 0 }) ? "\(gx) m" : "\(gx)"
            ctx.draw(axisText(label), at: CGPoint(x: f.point(Double(gx), 0).x, y: r.maxY + 3), anchor: .top)
        }
        let ys = Array(Int(b.minY.rounded(.up))...Int(b.maxY.rounded(.down)))
        let ystep = labelStep(count: ys.count, span: r.height)
        for gy in ys where gy % ystep == 0 {
            ctx.draw(axisText("\(gy)"), at: CGPoint(x: r.minX - 5, y: f.point(0, Double(gy)).y), anchor: .trailing)
        }
    }

    /// The arena floor: a soft sheet under the marker field and one small square per marker.
    private func drawMarkers(_ ctx: GraphicsContext) {
        let pts = markers.filter { $0.count >= 2 }
        guard pts.count >= 2 else { return }
        let xs = pts.map { $0[0] }, ys = pts.map { $0[1] }
        let a = frame.point(xs.min()! - 0.375, ys.max()! + 0.375), b = frame.point(xs.max()! + 0.375, ys.min()! - 0.375)
        let sheet = Path(roundedRect: CGRect(x: a.x, y: a.y, width: b.x - a.x, height: b.y - a.y), cornerRadius: 4)
        ctx.fill(sheet, with: .color(.white.opacity(0.028)))
        ctx.stroke(sheet, with: .color(.white.opacity(0.10)), lineWidth: 0.75)
        let side = max(3, min(9, frame.pointsPerMetre * 0.25))
        var squares = Path()
        for m in pts {
            let p = frame.point(m[0], m[1])
            squares.addRect(CGRect(x: p.x - side / 2, y: p.y - side / 2, width: side, height: side))
        }
        ctx.fill(squares, with: .color(.white.opacity(0.11)))
    }

    private func labelStep(count: Int, span: CGFloat) -> Int {
        let perLabel = span / CGFloat(max(count, 1))
        return perLabel < 22 ? (perLabel < 11 ? 4 : 2) : 1
    }

    private func axisText(_ s: String) -> Text {
        Text(s).font(Theme.code(9)).foregroundStyle(Theme.textTertiary)
    }

    private func drawArea(_ ctx: GraphicsContext) {
        guard let rect = LabelLayout.areaRect(area, frame) else { return }
        ctx.fill(Path(rect), with: .color(onFloor ? .black.opacity(0.035) : .white.opacity(0.018)))
        ctx.stroke(Path(rect), with: .color(onFloor ? .black.opacity(0.55) : .white.opacity(0.34)), style: StrokeStyle(lineWidth: 1, dash: [4, 3]))
        if let a = area, let lr = LabelLayout.areaLabelRect(area, frame) {
            let text = String(format: "Survey %.1f × %.1f m", abs(a[2] - a[0]), abs(a[3] - a[1]))
            ctx.draw(Text(text).font(Theme.code(8.5, .medium)).foregroundStyle(onFloor ? Color.black.opacity(0.6) : Theme.textTertiary),
                     at: CGPoint(x: lr.minX, y: lr.midY), anchor: .leading)
        }
    }

    private func drawTrack(_ ctx: GraphicsContext) {
        guard track.count > 1 else { return }
        let pts = track.map { frame.point($0.x, $0.y) }
        let style = StrokeStyle(lineWidth: 1.6, lineCap: .round, lineJoin: .round)
        guard fadeTrail else {
            var path = Path()
            path.addLines(pts)
            ctx.stroke(path, with: .color((onFloor ? Self.trackOnFloor : Theme.signal).opacity(0.75)), style: style)
            return
        }
        // fading breadcrumb: older segments fade towards the background (drawn in a few chunks, not per point)
        let chunks = min(24, pts.count - 1)
        let per = Double(pts.count - 1) / Double(chunks)
        for i in 0..<chunks {
            let a = Int((Double(i) * per).rounded(.down))
            let b = min(pts.count - 1, Int((Double(i + 1) * per).rounded(.up)))
            guard b > a else { continue }
            var path = Path()
            path.addLines(Array(pts[a...b]))
            let t = Double(i + 1) / Double(chunks)
            ctx.stroke(path, with: .color((onFloor ? Self.trackOnFloor : Theme.signal).opacity(0.08 + 0.82 * t * t)), style: style)
        }
    }

    private func drawHome(_ ctx: GraphicsContext) {
        guard let r = LabelLayout.homeRect(home, frame) else { return }
        let shape = Path(roundedRect: r, cornerRadius: 3)
        ctx.fill(shape, with: .color(Theme.canvas))
        ctx.stroke(shape, with: .color(Theme.textSecondary), lineWidth: 1)
        ctx.draw(Text("H").font(Theme.code(9.5, .bold)).foregroundStyle(Theme.textPrimary),
                 at: CGPoint(x: r.midX, y: r.midY))
    }
}

// MARK: - Labels (collision-free placement)

private struct LabelPlacement: Identifiable, Equatable {
    let id: String
    let title: String
    let detail: String
    let rect: CGRect
    let anchor: CGPoint
}

/// Places one label per object around its pin, trying 8 positions in order and avoiding other labels,
/// pins, the home pad, the survey caption and the map edges. Mono fonts make text widths predictable.
private struct LabelLayout {
    var placements: [LabelPlacement] = []

    static let titleSize: CGFloat = 9.5
    static let detailSize: CGFloat = 9
    static let charWidth: CGFloat = 0.62   // SF Mono advance ≈ 0.6 em
    static let pinRadius: CGFloat = 12

    init(objects: [MapObject], frame: WorldFrame, area: [Double]?, home: [Double]?, arena: ArenaMap? = nil) {
        guard !objects.isEmpty else { return }
        let canvas = CGRect(origin: .zero, size: frame.size).insetBy(dx: 2, dy: 2)
        var obstacles: [CGRect] = objects.map {
            let p = frame.point($0.x, $0.y)
            return CGRect(x: p.x - Self.pinRadius, y: p.y - Self.pinRadius, width: Self.pinRadius * 2, height: Self.pinRadius * 2)
        }
        if let h = Self.homeRect(home, frame) { obstacles.append(h.insetBy(dx: -2, dy: -2)) }
        if let s = Self.areaLabelRect(area, frame) { obstacles.append(s) }

        for o in objects.sorted(by: { $0.id.localizedStandardCompare($1.id) == .orderedAscending }) {
            let title = o.label
            var detail = String(format: "%.2f, %.2f", o.x, o.y)
            if let n = arena?.nearest(o.x, o.y) { detail += " · M\(n.marker.id)" }      // nearest floor marker
            let w = CGFloat(max(title.count, detail.count)) * Self.titleSize * Self.charWidth + 12
            let h: CGFloat = 30
            let p = frame.point(o.x, o.y)
            let g: CGFloat = 9
            let candidates = [
                CGRect(x: p.x + g, y: p.y - g - h + 6, width: w, height: h),          // NE
                CGRect(x: p.x + g, y: p.y + g - 6, width: w, height: h),              // SE
                CGRect(x: p.x - g - w, y: p.y - g - h + 6, width: w, height: h),      // NW
                CGRect(x: p.x - g - w, y: p.y + g - 6, width: w, height: h),          // SW
                CGRect(x: p.x + g + 3, y: p.y - h / 2, width: w, height: h),          // E
                CGRect(x: p.x - g - 3 - w, y: p.y - h / 2, width: w, height: h),      // W
                CGRect(x: p.x - w / 2, y: p.y - g - 4 - h, width: w, height: h),      // N
                CGRect(x: p.x - w / 2, y: p.y + g + 4, width: w, height: h),          // S
            ]
            let own = CGRect(x: p.x - Self.pinRadius, y: p.y - Self.pinRadius, width: Self.pinRadius * 2, height: Self.pinRadius * 2)
            let others = obstacles.filter { $0 != own }
            func cost(_ r: CGRect) -> CGFloat {
                var c: CGFloat = 0
                let inside = r.intersection(canvas)
                c += (r.width * r.height - (inside.isNull ? 0 : inside.width * inside.height)) * 4
                for ob in others + placements.map(\.rect) {
                    let i = r.intersection(ob.insetBy(dx: -2, dy: -2))
                    if !i.isNull { c += i.width * i.height }
                }
                return c
            }
            var best = candidates[0], bestCost = CGFloat.infinity
            for r in candidates {
                let c = cost(r)
                if c < bestCost { best = r; bestCost = c }
                if c == 0 { break }
            }
            // never let a label leave the map, even if every slot was crowded
            best.origin.x = min(max(best.minX, canvas.minX), canvas.maxX - best.width)
            best.origin.y = min(max(best.minY, canvas.minY), canvas.maxY - best.height)
            placements.append(LabelPlacement(id: o.id, title: title, detail: detail, rect: best, anchor: p))
        }
    }

    static func areaRect(_ area: [Double]?, _ f: WorldFrame) -> CGRect? {
        guard let a = area, a.count == 4 else { return nil }
        let p0 = f.point(min(a[0], a[2]), max(a[1], a[3])), p1 = f.point(max(a[0], a[2]), min(a[1], a[3]))
        return CGRect(x: p0.x, y: p0.y, width: p1.x - p0.x, height: p1.y - p0.y)
    }

    /// The "SURVEY w × h m" caption sits just above the area's top-left corner.
    static func areaLabelRect(_ area: [Double]?, _ f: WorldFrame) -> CGRect? {
        guard let r = areaRect(area, f) else { return nil }
        let w: CGFloat = 19 * 8.5 * charWidth
        let y = r.minY - 13 >= f.worldRect.minY ? r.minY - 13 : r.minY + 3
        return CGRect(x: r.minX + 1, y: y, width: w, height: 11)
    }

    static func homeRect(_ home: [Double]?, _ f: WorldFrame) -> CGRect? {
        guard let h = home, h.count >= 2 else { return nil }
        let c = f.point(h[0], h[1])
        return CGRect(x: c.x - 8, y: c.y - 8, width: 16, height: 16)
    }
}

private struct PinLabel: View {
    let placement: LabelPlacement
    let highlighted: Bool

    var body: some View {
        let r = placement.rect
        ZStack(alignment: .topLeading) {
            Leader(from: placement.anchor, to: nearestEdgePoint(of: r, to: placement.anchor))
                .stroke(Theme.accent.opacity(highlighted ? 0.8 : 0.4), lineWidth: 0.75)
            VStack(alignment: .leading, spacing: 1) {
                Text(placement.title)
                    .font(Theme.code(LabelLayout.titleSize, .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Text(placement.detail)
                    .font(Theme.code(LabelLayout.detailSize))
                    .foregroundStyle(Theme.textSecondary)
            }
            .lineLimit(1)
            .fixedSize()
            .padding(.horizontal, 6)
            .frame(width: r.width, height: r.height, alignment: .leading)
            .background(Theme.panelRaised.opacity(0.94), in: .rect(cornerRadius: 5))
            .overlay(RoundedRectangle(cornerRadius: 5).strokeBorder(highlighted ? Theme.accent.opacity(0.7) : Theme.hairlineStrong, lineWidth: 0.75))
            .offset(x: r.minX, y: r.minY)
        }
        .allowsHitTesting(false)
    }

    private func nearestEdgePoint(of r: CGRect, to p: CGPoint) -> CGPoint {
        CGPoint(x: min(max(p.x, r.minX), r.maxX), y: min(max(p.y, r.minY), r.maxY))
    }
}

private struct Leader: Shape {
    var from: CGPoint
    var to: CGPoint
    func path(in rect: CGRect) -> Path {
        var p = Path()
        let d = hypot(to.x - from.x, to.y - from.y)
        guard d > LabelLayout.pinRadius + 1 else { return p }
        let k = LabelLayout.pinRadius / d
        p.move(to: CGPoint(x: from.x + (to.x - from.x) * k, y: from.y + (to.y - from.y) * k))
        p.addLine(to: to)
        return p
    }
}

// MARK: - Pins, drone, cursor

private struct ObjectPin: View {
    var name = "fire"
    let highlighted: Bool
    private var tint: Color { Theme.color(forObject: name) }
    @State private var ripple = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        ZStack {
            // one-shot ripple when the object first appears: no continuous redraw
            Circle()
                .stroke(tint, lineWidth: 1)
                .frame(width: 12, height: 12)
                .scaleEffect(ripple ? 3.2 : 1)
                .opacity(ripple ? 0 : 0.8)
            Circle()
                .fill(tint.opacity(0.18))
                .frame(width: 24, height: 24)
            Circle()
                .fill(tint)
                .frame(width: 17, height: 17)
                .overlay(Circle().strokeBorder(Theme.canvas, lineWidth: 1.5))
            Image(systemName: Theme.symbol(forObject: name))
                .font(.system(size: 8.5, weight: .bold))
                .foregroundStyle(Theme.canvas)
        }
        .frame(width: 26, height: 26)
        .scaleEffect(highlighted ? 1.25 : 1)
        .contentShape(.circle)
        .onAppear {
            guard !reduceMotion else { ripple = true; return }
            withAnimation(.easeOut(duration: 1.5).repeatCount(3, autoreverses: false)) { ripple = true }
        }
    }
}

private struct DroneGlyph: View {
    var heading: Double?
    /// Drawn on the light floor: dark arrow, deeper blue ring.
    var onFloor = false
    /// Unwrapped rotation so 359° → 1° turns 2°, not -358°.
    @State private var angle: Double = 0

    var body: some View {
        ZStack {
            let ring = onFloor ? MapCanvas.trackOnFloor : Theme.signal
            Circle()
                .fill(ring.opacity(onFloor ? 0.18 : 0.14))
                .frame(width: 30, height: 30)
            Circle()
                .strokeBorder(ring.opacity(onFloor ? 0.8 : 0.45), lineWidth: onFloor ? 1 : 0.75)
                .frame(width: 30, height: 30)
            if heading != nil {
                Arrowhead()
                    .fill(onFloor ? MapCanvas.ink : Theme.textPrimary)
                    .overlay(Arrowhead().stroke(onFloor ? Color.white : Theme.canvas, lineWidth: 1))
                    .frame(width: 13, height: 15)
                    .rotationEffect(.radians(angle))
            } else {
                Circle().fill(onFloor ? MapCanvas.ink : Theme.textPrimary).frame(width: 9, height: 9)
            }
        }
        .onAppear { angle = target(heading) }
        .onChange(of: heading) { _, h in
            guard h != nil else { return }
            var delta = (target(h) - angle).truncatingRemainder(dividingBy: 2 * .pi)
            if delta > .pi { delta -= 2 * .pi } else if delta < -.pi { delta += 2 * .pi }
            withAnimation(.smooth(duration: 0.35)) { angle += delta }
        }
        .allowsHitTesting(false)
        .accessibilityLabel("Drone")
    }

    /// Map heading (radians from +x, counter-clockwise) → SwiftUI rotation of an up-pointing arrow.
    private func target(_ h: Double?) -> Double { .pi / 2 - (h ?? .pi / 2) }
}

private struct Arrowhead: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.midX, y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX, y: r.maxY))
        p.addLine(to: CGPoint(x: r.midX, y: r.maxY - r.height * 0.28))
        p.addLine(to: CGPoint(x: r.minX, y: r.maxY))
        p.closeSubpath()
        return p
    }
}

/// Cursor position in map metres, shown only while hovering. Owns its own state so mouse movement redraws
/// nothing else.
private struct CursorReadout: View {
    let frame: WorldFrame
    var arena: ArenaMap?
    @State private var cursor: CGPoint?

    var body: some View {
        Color.clear
            .contentShape(.rect)
            .onContinuousHover { phase in
                switch phase {
                case .active(let p): cursor = frame.worldRect.contains(p) ? p : nil
                case .ended: cursor = nil
                }
            }
            .overlay(alignment: .topTrailing) {
                if let cursor {
                    let w = frame.world(cursor)
                    Text(String(format: "x %5.2f  y %5.2f m", w.x, w.y)
                         + (arena?.nearest(w.x, w.y).map { "  ·  M\($0.marker.id)" } ?? ""))
                        .font(Theme.code(10, .medium))
                        .foregroundStyle(Theme.textSecondary)
                        .monospacedDigit()
                        .padding(.horizontal, 7)
                        .frame(height: 20)
                        .glassEffect(.regular, in: .rect(cornerRadius: 6))
                        .padding(.top, FieldMap.insets.top + 4)
                        .padding(.trailing, FieldMap.insets.trailing + 4)
                        .allowsHitTesting(false)
                        .transition(.opacity)
                }
            }
            .overlay {
                if let cursor {
                    CrossHair(point: cursor, rect: frame.worldRect)
                        .stroke(arena == nil ? Color.white.opacity(0.14) : Color.black.opacity(0.3), style: StrokeStyle(lineWidth: 0.5, dash: [2, 3]))
                        .allowsHitTesting(false)
                }
            }
    }
}

private struct CrossHair: Shape {
    let point: CGPoint
    let rect: CGRect
    func path(in _: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: rect.minX, y: point.y)); p.addLine(to: CGPoint(x: rect.maxX, y: point.y))
        p.move(to: CGPoint(x: point.x, y: rect.minY)); p.addLine(to: CGPoint(x: point.x, y: rect.maxY))
        return p
    }
}
