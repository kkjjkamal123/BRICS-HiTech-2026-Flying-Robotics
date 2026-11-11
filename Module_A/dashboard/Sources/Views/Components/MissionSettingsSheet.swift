import SwiftUI

/// Mission settings: scan area, boundary (geofence), home, altitude, line spacing, speed and the fire temperature.
/// Saved on this Mac and sent to the mission as `--set` arguments every time it starts (drone and simulator).
struct MissionSettingsSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        let ms = model.missionSettings
        let field = markerField
        let problems = ms.problems(markerField: field)
        VStack(spacing: 0) {
            header
            Rectangle().fill(Theme.hairline).frame(height: 1)
            HStack(alignment: .top, spacing: 0) {
                VStack(alignment: .leading, spacing: 10) {
                    SurveyPreview(settings: ms, markers: markerPoints, markerField: field)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    PreviewLegend()
                    SurveyFacts(settings: ms)
                }
                .padding(18)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                Rectangle().fill(Theme.hairline).frame(width: 1)
                ScrollView {
                    SettingsForm(markerField: field)
                        .padding(18)
                }
                .frame(width: 430)
            }
            Rectangle().fill(Theme.hairline).frame(height: 1)
            footer(problems: problems)
        }
        .frame(minWidth: 1060, idealWidth: 1140, minHeight: 700, idealHeight: 760)
        .onAppear { ms.markerField = field }
        .onChange(of: field) { _, f in ms.markerField = f }
        .background(Theme.canvas)
        .preferredColorScheme(.dark)
        .tint(Theme.accent)
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Mission settings")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Text("Used by the next Run mission and Run simulation. Saved on this Mac; the config file on the drone is not changed.")
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.textSecondary)
            }
            Spacer()
            if model.mission.connected {
                StatusPill(text: "A mission is running: changes apply to the next run", color: Theme.caution, pulsing: false)
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 14)
    }

    private func footer(problems: [String]) -> some View {
        let ms = model.missionSettings
        return VStack(alignment: .leading, spacing: 10) {
            if !problems.isEmpty || !ms.warnings.isEmpty || ms.adjustment != nil {
                VStack(alignment: .leading, spacing: 5) {
                    if let a = ms.adjustment {
                        MessageRow(text: "Blocked: \(a). Values outside the safe range are not accepted.", color: Theme.signal, symbol: "hand.raised.fill")
                    }
                    ForEach(problems, id: \.self) { MessageRow(text: $0, color: Theme.critical, symbol: "xmark.octagon.fill") }
                    ForEach(ms.warnings, id: \.self) { MessageRow(text: $0, color: Theme.caution, symbol: "exclamationmark.triangle.fill") }
                }
            }
            HStack(spacing: 10) {
                Text(ms.setArguments.joined(separator: " "))
                    .font(Theme.mono(10.5))
                    .foregroundStyle(Theme.textTertiary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .textSelection(.enabled)
                    .help(ms.setArguments.joined(separator: " "))
                Spacer(minLength: 8)
                Button("Reset to venue defaults") { withAnimation(.snappy) { ms.resetToVenue() } }
                    .buttonStyle(.secondary)
                    .disabled(ms.isVenueDefault)
                Button(problems.isEmpty ? "Done" : "Close (mission blocked)") { dismiss() }
                    .buttonStyle(.primary)
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 12)
    }

    /// Marker centres of the arena: from the running mission (the map loaded on the drone), else the official map.
    private var markerPoints: [[Double]] {
        let live = (model.mission.status?.markers ?? []).filter { $0.count >= 2 }
        if live.count >= 2 { return live }
        let f = MissionSettings.Venue.markerField
        return stride(from: f[1], through: f[3] + 1e-9, by: 0.75).flatMap { y in
            stride(from: f[0], through: f[2] + 1e-9, by: 0.75).map { [$0, y] }
        }
    }

    private var markerField: [Double] {
        let pts = markerPoints
        let xs = pts.map { $0[0] }, ys = pts.map { $0[1] }
        guard let x0 = xs.min(), let x1 = xs.max(), let y0 = ys.min(), let y1 = ys.max() else { return MissionSettings.Venue.markerField }
        return [x0, y0, x1, y1]
    }
}

// MARK: - Form

private struct SettingsForm: View {
    @Environment(AppModel.self) private var model
    let markerField: [Double]

    var body: some View {
        @Bindable var ms = model.missionSettings
        VStack(alignment: .leading, spacing: 18) {
            FormSection(title: "Arena", symbol: "square.grid.3x3") {
                InfoLine(text: String(format: "Floor markers  x %.2f … %.2f   y %.2f … %.2f m", markerField[0], markerField[2], markerField[1], markerField[3]))
                Explain("The drone only knows where it is above the markers, so the boundary cannot be set past the outer markers, the scan area cannot leave the boundary, and home stays inside it. Out-of-range values are pulled back as you type. Origin (0, 0) = centre of the field.")
            }

            FormSection(title: "Boundary (geofence)", symbol: "square.dashed", tint: Theme.critical) {
                BoxEditor(box: $ms.fence)
                Explain("If the drone crosses the boundary it lands immediately. Waypoints outside it are skipped.")
                HStack(spacing: 8) {
                    Button("Fit to marker field") { withAnimation(.snappy) { ms.fenceToMarkerField(markerField) } }
                        .buttonStyle(.secondary)
                }
            }

            FormSection(title: "Scan area", symbol: "rectangle.dashed") {
                BoxEditor(box: $ms.area)
                Explain("The rectangle the drone sweeps line by line. Keep it inside the boundary.")
                HStack(spacing: 8) {
                    Button("Boundary − 0.5 m") { withAnimation(.snappy) { ms.areaInsideFence(margin: 0.5) } }
                        .buttonStyle(.secondary)
                    Button("Boundary − 0.25 m") { withAnimation(.snappy) { ms.areaInsideFence(margin: 0.25) } }
                        .buttonStyle(.secondary)
                }
            }

            FormSection(title: "Home", symbol: "house") {
                HStack(spacing: 14) {
                    MetreField(label: "x", value: Binding(get: { ms.home[0] }, set: { ms.home[0] = $0 }))
                    MetreField(label: "y", value: Binding(get: { ms.home[1] }, set: { ms.home[1] = $0 }))
                    Spacer(minLength: 0)
                }
                Explain("Where the drone flies back to before landing. Take off from here.")
            }

            FormSection(title: "Flight", symbol: "airplane") {
                ParamSlider(label: "Altitude", value: $ms.altitude, range: MissionSettings.Limit.altitude, step: 0.1, format: "%.1f", unit: "m")
                ParamSlider(label: "Speed", value: $ms.speed, range: MissionSettings.Limit.speed, step: 0.05, format: "%.2f", unit: "")
                Explain("Altitude = survey height. Higher sees a wider strip (fewer lines) but makes objects smaller. Speed in m/s: slower gives sharper pictures and more detections.")
            }

            FormSection(title: "Line spacing", symbol: "line.3.horizontal") {
                Picker("Line spacing", selection: $ms.spacingAuto) {
                    Text("Auto (from camera view)").tag(true)
                    Text("Manual").tag(false)
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                if ms.spacingAuto {
                    ParamSlider(label: "Overlap", value: Binding(get: { ms.overlap * 100 }, set: { ms.overlap = $0 / 100 }),
                                range: 0...(MissionSettings.Limit.overlap.upperBound * 100), step: 5, format: "%.0f", unit: "%")
                    InfoLine(text: String(format: "Auto spacing at %.1f m:  %.2f m", ms.altitude, ms.autoSpacing))
                } else {
                    ParamSlider(label: "Spacing", value: $ms.spacing, range: MissionSettings.Limit.spacing, step: 0.05, format: "%.2f", unit: "m")
                }
                Explain(String(format: "Line spacing is the distance between two neighbouring passes of the lawn-mower sweep (the blue lines on the map). At %.1f m the thermal camera sees a strip %.2f m wide, so spacing below that means the strips overlap and nothing is missed. Smaller spacing = more lines, longer flight. Larger = faster, but gaps if it is wider than the strip.",
                               ms.altitude, min(ms.footprint.width, ms.footprint.height)))
            }

            FormSection(title: "Fire temperature", symbol: "thermometer.high", tint: Theme.accent) {
                ParamSlider(label: "Fire at ≥", value: $ms.fireC, range: MissionSettings.Limit.fireC, step: 5, format: "%.0f", unit: "°C")
                Explain("Anything the thermal camera reads at or above this temperature is mapped as fire. Venue rule: 100 °C. The thermal pane draws its FIRE boxes at the same temperature while the mission runs.")
            }
        }
    }
}

private struct FormSection<Content: View>: View {
    let title: String
    let symbol: String
    var tint: Color = Theme.textTertiary
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 7) {
                Image(systemName: symbol)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(tint)
                    .frame(width: 14)
                Text(title.uppercased())
                    .font(Theme.mono(10.5, .semibold))
                    .tracking(0.8)
                    .foregroundStyle(Theme.textSecondary)
            }
            content
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.panel, in: .rect(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Theme.hairline))
    }
}

/// x from / to and y from / to of a rectangle, 0.25 m steps.
private struct BoxEditor: View {
    @Binding var box: [Double]

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 14) {
                MetreField(label: "x from", value: Binding(get: { box[0] }, set: { box[0] = $0 }))
                MetreField(label: "to", value: Binding(get: { box[2] }, set: { box[2] = $0 }))
                Spacer(minLength: 0)
                Text(String(format: "%.2f m wide", box[2] - box[0]))
                    .font(Theme.mono(10.5)).foregroundStyle(Theme.textTertiary).fixedSize()
            }
            HStack(spacing: 14) {
                MetreField(label: "y from", value: Binding(get: { box[1] }, set: { box[1] = $0 }))
                MetreField(label: "to", value: Binding(get: { box[3] }, set: { box[3] = $0 }))
                Spacer(minLength: 0)
                Text(String(format: "%.2f m deep", box[3] - box[1]))
                    .font(Theme.mono(10.5)).foregroundStyle(Theme.textTertiary).fixedSize()
            }
        }
    }
}

private struct MetreField: View {
    let label: String
    @Binding var value: Double

    var body: some View {
        HStack(spacing: 6) {
            Text(label)
                .font(.system(size: 12))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: label.count > 2 ? 44 : 14, alignment: .leading)
            TextField(label, value: $value, format: .number.precision(.fractionLength(0...2)))
                .labelsHidden()
                .textFieldStyle(.roundedBorder)
                .font(Theme.mono(12))
                .multilineTextAlignment(.trailing)
                .frame(width: 62)
            Stepper(label, value: $value, step: 0.25)
                .labelsHidden()
        }
        .fixedSize()
    }
}

private struct Explain: View {
    let text: String
    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text)
            .font(.system(size: 11.5))
            .foregroundStyle(Theme.textTertiary)
            .fixedSize(horizontal: false, vertical: true)
    }
}

private struct InfoLine: View {
    let text: String

    var body: some View {
        Text(text)
            .font(Theme.mono(11.5, .medium))
            .foregroundStyle(Theme.textPrimary)
            .textSelection(.enabled)
    }
}

private struct MessageRow: View {
    let text: String
    let color: Color
    let symbol: String

    var body: some View {
        Label {
            Text(text).foregroundStyle(Theme.textPrimary).fixedSize(horizontal: false, vertical: true)
        } icon: {
            Image(systemName: symbol).foregroundStyle(color)
        }
        .font(.system(size: 12))
    }
}

// MARK: - Preview

private struct SurveyFacts: View {
    let settings: MissionSettings

    var body: some View {
        let ms = settings
        let lines = ms.surveyLines
        HStack(spacing: 18) {
            fact("LINES", "\(lines.count)")
            fact("SPACING", String(format: "%.2f m", ms.actualSpacing))
            fact("CAMERA STRIP", String(format: "%.2f m", min(ms.footprint.width, ms.footprint.height)))
            fact("PATH", String(format: "%.1f m", ms.surveyLength))
            fact("SURVEY TIME", String(format: "%d:%02d", Int(ms.surveySeconds) / 60, Int(ms.surveySeconds) % 60))
            Spacer(minLength: 0)
        }
    }

    private func fact(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(Theme.mono(9.5, .semibold)).tracking(0.6).foregroundStyle(Theme.textTertiary)
            Text(value).font(Theme.mono(14, .medium)).foregroundStyle(Theme.textPrimary).monospacedDigit()
                .contentTransition(.numericText())
        }
    }
}

private struct PreviewLegend: View {
    var body: some View {
        HStack(spacing: 16) {
            item(Rectangle().stroke(Theme.critical, style: StrokeStyle(lineWidth: 1.5, dash: [4, 3])), "Boundary")
            item(Rectangle().stroke(Color.white.opacity(0.6), style: StrokeStyle(lineWidth: 1, dash: [4, 3])), "Scan area")
            item(Rectangle().fill(Theme.signal), "Survey path", height: 2)
            item(Rectangle().fill(Theme.signal.opacity(0.18)), "What the thermal camera sees")
            item(Rectangle().fill(Color.white.opacity(0.25)), "Floor marker")
            Spacer(minLength: 0)
        }
        .font(.system(size: 11))
        .foregroundStyle(Theme.textSecondary)
    }

    private func item<S: View>(_ swatch: S, _ text: String, height: CGFloat = 9) -> some View {
        HStack(spacing: 6) {
            swatch.frame(width: 14, height: height)
            Text(text)
        }
    }
}

/// Top-down drawing of the plan: marker field, boundary, scan area, survey lines with the camera strip.
private struct SurveyPreview: View {
    let settings: MissionSettings
    let markers: [[Double]]
    let markerField: [Double]

    var body: some View {
        let ms = settings
        GeometryReader { geo in
            let frame = WorldFrame(bounds: bounds, size: geo.size, insets: EdgeInsets(top: 8, leading: 26, bottom: 20, trailing: 8))
            Canvas { ctx, _ in
                drawGrid(ctx, frame)
                drawMarkers(ctx, frame)
                drawCoverage(ctx, frame, ms)
                drawRect(ctx, frame, ms.area, color: .white.opacity(0.6), width: 1, label: String(format: "SCAN AREA %.1f × %.1f m", ms.area[2] - ms.area[0], ms.area[3] - ms.area[1]), below: false)
                drawRect(ctx, frame, ms.fence, color: Theme.critical, width: 1.5, label: "BOUNDARY", below: true)
                drawPath(ctx, frame, ms)
                drawSpacing(ctx, frame, ms)
                drawHome(ctx, frame, ms.home)
            }
        }
        .background(Theme.well, in: .rect(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Theme.hairline))
        .accessibilityLabel("Preview of the survey plan")
    }

    private var bounds: CGRect {
        let boxes = [markerField, settings.fence, settings.area]
        var xs = boxes.flatMap { [$0[0], $0[2]] } + [settings.home[0]]
        var ys = boxes.flatMap { [$0[1], $0[3]] } + [settings.home[1]]
        xs = xs.filter(\.isFinite); ys = ys.filter(\.isFinite)
        let x0 = (xs.min() ?? -3) - 0.7, x1 = (xs.max() ?? 3) + 0.7
        let y0 = (ys.min() ?? -2) - 0.7, y1 = (ys.max() ?? 2) + 0.7
        return CGRect(x: x0, y: y0, width: max(1, x1 - x0), height: max(1, y1 - y0))
    }

    private func rect(_ f: WorldFrame, _ b: [Double]) -> CGRect {
        let a = f.point(min(b[0], b[2]), max(b[1], b[3])), c = f.point(max(b[0], b[2]), min(b[1], b[3]))
        return CGRect(x: a.x, y: a.y, width: c.x - a.x, height: c.y - a.y)
    }

    private func drawGrid(_ ctx: GraphicsContext, _ f: WorldFrame) {
        let b = f.bounds, r = f.worldRect
        var major = Path()
        var x = b.minX.rounded(.up)
        while x <= b.maxX {
            let px = f.point(x, 0).x
            major.addLines([CGPoint(x: px, y: r.minY), CGPoint(x: px, y: r.maxY)])
            ctx.draw(Text(x == 0 ? "0" : String(format: "%.0f", x)).font(Theme.mono(9)).foregroundStyle(Theme.textTertiary),
                     at: CGPoint(x: px, y: r.maxY + 4), anchor: .top)
            x += 1
        }
        var y = b.minY.rounded(.up)
        while y <= b.maxY {
            let py = f.point(0, y).y
            major.addLines([CGPoint(x: r.minX, y: py), CGPoint(x: r.maxX, y: py)])
            ctx.draw(Text(String(format: "%.0f", y)).font(Theme.mono(9)).foregroundStyle(Theme.textTertiary),
                     at: CGPoint(x: r.minX - 6, y: py), anchor: .trailing)
            y += 1
        }
        ctx.stroke(major, with: .color(.white.opacity(0.06)), lineWidth: 0.75)
        // axes through the origin (field centre)
        var axes = Path()
        let o = f.point(0, 0)
        axes.addLines([CGPoint(x: o.x, y: r.minY), CGPoint(x: o.x, y: r.maxY)])
        axes.move(to: CGPoint(x: r.minX, y: o.y)); axes.addLine(to: CGPoint(x: r.maxX, y: o.y))
        ctx.stroke(axes, with: .color(.white.opacity(0.12)), lineWidth: 0.75)
    }

    private func drawMarkers(_ ctx: GraphicsContext, _ f: WorldFrame) {
        let sheet = rect(f, [markerField[0] - 0.375, markerField[1] - 0.375, markerField[2] + 0.375, markerField[3] + 0.375])
        ctx.fill(Path(roundedRect: sheet, cornerRadius: 4), with: .color(.white.opacity(0.03)))
        let side = max(3, min(12, f.pointsPerMetre * 0.25))
        var squares = Path()
        for m in markers {
            let p = f.point(m[0], m[1])
            squares.addRect(CGRect(x: p.x - side / 2, y: p.y - side / 2, width: side, height: side))
        }
        ctx.fill(squares, with: .color(.white.opacity(0.16)))
    }

    /// The strip the thermal camera sees along every line: overlap and gaps are visible at a glance.
    private func drawCoverage(_ ctx: GraphicsContext, _ f: WorldFrame, _ ms: MissionSettings) {
        let half = min(ms.footprint.width, ms.footprint.height) / 2
        let a = ms.area
        for y in ms.surveyLines {
            let r = rect(f, [a[0] - half, y - half, a[2] + half, y + half])
            ctx.fill(Path(roundedRect: r, cornerRadius: 3), with: .color(Theme.signal.opacity(0.09)))
        }
    }

    private func drawRect(_ ctx: GraphicsContext, _ f: WorldFrame, _ b: [Double], color: Color, width: CGFloat, label: String, below: Bool) {
        guard b[0] < b[2], b[1] < b[3] else { return }
        let r = rect(f, b)
        ctx.stroke(Path(r), with: .color(color), style: StrokeStyle(lineWidth: width, dash: [5, 4]))
        let text = Text(label).font(Theme.mono(9, .semibold)).tracking(0.5).foregroundStyle(color)
        if below {
            ctx.draw(text, at: CGPoint(x: r.maxX, y: r.maxY + 3), anchor: .topTrailing)
        } else {
            ctx.draw(text, at: CGPoint(x: r.minX + 4, y: r.minY - 3), anchor: .bottomLeading)
        }
    }

    private func drawPath(_ ctx: GraphicsContext, _ f: WorldFrame, _ ms: MissionSettings) {
        let a = ms.area
        guard a[0] < a[2] else { return }
        var pts: [CGPoint] = [f.point(ms.home[0], ms.home[1])]
        for (i, y) in ms.surveyLines.enumerated() {
            let row = [f.point(a[0], y), f.point(a[2], y)]
            pts += i % 2 == 0 ? row : row.reversed()
        }
        pts.append(f.point(ms.home[0], ms.home[1]))
        var transit = Path()
        transit.addLines([pts[0], pts[1]])
        transit.move(to: pts[pts.count - 2]); transit.addLine(to: pts[pts.count - 1])
        ctx.stroke(transit, with: .color(Theme.signal.opacity(0.45)), style: StrokeStyle(lineWidth: 1, dash: [2, 3]))
        var survey = Path()
        survey.addLines(Array(pts[1..<(pts.count - 1)]))
        ctx.stroke(survey, with: .color(Theme.signal), style: StrokeStyle(lineWidth: 1.8, lineCap: .round, lineJoin: .round))
        // direction arrow in the middle of every line
        for i in stride(from: 1, to: pts.count - 2, by: 2) {
            let p = pts[i], q = pts[i + 1]
            guard abs(q.x - p.x) > 30 else { continue }
            let mid = CGPoint(x: (p.x + q.x) / 2, y: p.y), dir: CGFloat = q.x > p.x ? 1 : -1
            var arrow = Path()
            arrow.move(to: CGPoint(x: mid.x - 5 * dir, y: mid.y - 4))
            arrow.addLine(to: CGPoint(x: mid.x + 3 * dir, y: mid.y))
            arrow.addLine(to: CGPoint(x: mid.x - 5 * dir, y: mid.y + 4))
            ctx.stroke(arrow, with: .color(Theme.signal), style: StrokeStyle(lineWidth: 1.6, lineCap: .round, lineJoin: .round))
        }
    }

    /// Dimension line between the first two survey lines: this is the "line spacing".
    private func drawSpacing(_ ctx: GraphicsContext, _ f: WorldFrame, _ ms: MissionSettings) {
        let lines = ms.surveyLines
        guard lines.count > 1 else { return }
        let x = ms.area[2] + 0.22
        let p = f.point(x, lines[0]), q = f.point(x, lines[1])
        var dim = Path()
        dim.move(to: p); dim.addLine(to: q)
        for e in [p, q] { dim.move(to: CGPoint(x: e.x - 4, y: e.y)); dim.addLine(to: CGPoint(x: e.x + 4, y: e.y)) }
        ctx.stroke(dim, with: .color(Theme.textPrimary), lineWidth: 1)
        ctx.draw(Text(String(format: "line spacing\n%.2f m", ms.actualSpacing)).font(Theme.mono(9.5, .semibold)).foregroundStyle(Theme.textPrimary),
                 at: CGPoint(x: p.x + 7, y: (p.y + q.y) / 2), anchor: .leading)
    }

    private func drawHome(_ ctx: GraphicsContext, _ f: WorldFrame, _ h: [Double]) {
        let p = f.point(h[0], h[1])
        let r = CGRect(x: p.x - 8, y: p.y - 8, width: 16, height: 16)
        ctx.fill(Path(roundedRect: r, cornerRadius: 3), with: .color(Theme.canvas))
        ctx.stroke(Path(roundedRect: r, cornerRadius: 3), with: .color(Theme.textSecondary), lineWidth: 1)
        ctx.draw(Text("H").font(Theme.mono(9.5, .bold)).foregroundStyle(Theme.textPrimary), at: p)
    }
}
