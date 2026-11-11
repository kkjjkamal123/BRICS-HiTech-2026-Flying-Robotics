import SwiftUI

// Judging Spec: the approved technical specification as a readable instrument table.
// C1–C7 table with expandable method/evidence, M1–M3 columns, pre-test checklist.

struct SpecView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        Page(section: .spec, trailing: evaluateButton.eraseToAnyView()) {
            SummaryRow()
            CharacteristicsTable()
            ModulesPanel()
            ChecklistPanel()
        }
        // Runs load asynchronously at launch; evaluate as soon as the latest Case 1 run is known.
        .task(id: latestRun?.id) {
            guard let latest = latestRun, model.spec.evaluatedRun != latest.id else { return }
            model.spec.evaluate(latest: latest)
        }
    }

    /// The spec scores Case 1 (forest fire); other mission folders (e.g. Case 3 swarm) are skipped.
    private var latestRun: RunSummary? {
        let runs = model.runs.missionRuns
        return runs.first { $0.id.hasPrefix("case1") } ?? runs.first
    }

    private var evaluateButton: some View {
        Button("Re-evaluate latest run", systemImage: "arrow.triangle.2.circlepath") {
            model.runs.reload()
            model.spec.evaluate(latest: latestRun)
        }
        .buttonStyle(.secondary)
        .fixedSize()
        .help("Re-read the newest mission run folder and score C1–C7 against it")
    }
}

// MARK: - Summary

private struct SummaryRow: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let spec = model.spec
        let modulesDone = spec.modules.filter(\.done).count
        HStack(spacing: Theme.spacing) {
            StatTile(title: "Characteristics passed", value: "\(spec.passCount)", unit: "/ \(spec.items.count)",
                     symbol: "checkmark.seal", tint: spec.passCount == spec.items.count ? Theme.ok : Theme.textPrimary,
                     footnote: spec.evaluatedRun ?? "No run evaluated yet",
                     emphasis: spec.passCount == spec.items.count)
            StatTile(title: "Modules demonstrated", value: "\(modulesDone)", unit: "/ \(spec.modules.count)",
                     symbol: "square.stack.3d.up",
                     footnote: spec.modules.filter { !$0.done }.map { "\($0.id) open" }.joined(separator: " · ").nonEmpty ?? "All modules shown")
            StatTile(title: "Pre-test checklist", value: "\(spec.checked.count)", unit: "/ \(spec.checklist.count)",
                     symbol: "checklist", tint: spec.checked.count == spec.checklist.count ? Theme.ok : Theme.textPrimary,
                     footnote: spec.checked.count == spec.checklist.count ? "Ready for the attempt" : "\(spec.checklist.count - spec.checked.count) items open",
                     emphasis: spec.checked.count == spec.checklist.count)
        }
        .fixedSize(horizontal: false, vertical: true)
    }
}

// MARK: - C1–C7 table

private enum SpecColumns {
    static let id: CGFloat = 34
    static let unit: CGFloat = 150
    static func threshold(_ wide: Bool) -> CGFloat { wide ? 212 : 192 }
    static func measured(_ wide: Bool) -> CGFloat { wide ? 236 : 206 }
    static let verdict: CGFloat = 112
    static let chevron: CGFloat = 12
    static let gap: CGFloat = 14
    static let inset: CGFloat = 18
    /// Leading offset of the title column (used to indent the disclosure).
    static let titleLead: CGFloat = inset + id + gap
}

private struct CharacteristicsTable: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var expanded: Set<String> = []
    @State private var wide = true


    var body: some View {
        let spec = model.spec
        GlassCard(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader(title: "Mandatory characteristics", symbol: "list.bullet.rectangle",
                           trailing: Text("Module B2 · 28 pts").font(Theme.mono(11)).foregroundStyle(Theme.textTertiary).eraseToAnyView())
                    .padding(.horizontal, SpecColumns.inset)
                    .padding(.top, 14)
                    .padding(.bottom, 10)
                ColumnHeader(wide: wide)
                ForEach(spec.items) { item in
                    Rectangle().fill(Theme.hairline).frame(height: 1)
                    SpecRow(item: item, wide: wide, expanded: expanded.contains(item.id)) {
                        withAnimation(reduceMotion ? nil : .snappy(duration: 0.24)) {
                            if expanded.contains(item.id) { expanded.remove(item.id) } else { expanded.insert(item.id) }
                        }
                    }
                }
            }
            .padding(.bottom, 4)
        }
        .onGeometryChange(for: Bool.self) { $0.size.width > 1000 } action: { wide = $0 }
    }
}

private struct ColumnHeader: View {
    let wide: Bool

    var body: some View {
        HStack(spacing: SpecColumns.gap) {
            label("ID").frame(width: SpecColumns.id, alignment: .leading)
            label("Characteristic").frame(maxWidth: .infinity, alignment: .leading)
            if wide { label("Unit").frame(width: SpecColumns.unit, alignment: .leading) }
            label("Threshold").frame(width: SpecColumns.threshold(wide), alignment: .leading)
            label("Measured").frame(width: SpecColumns.measured(wide), alignment: .leading)
            label("Verdict").frame(width: SpecColumns.verdict, alignment: .leading)
            Color.clear.frame(width: SpecColumns.chevron, height: 1)
        }
        .padding(.horizontal, SpecColumns.inset)
        .padding(.vertical, 7)
        .background(Theme.well.opacity(0.6))
        .overlay(alignment: .top) { Rectangle().fill(Theme.hairline).frame(height: 1) }
    }

    private func label(_ s: String) -> some View {
        Text(s.uppercased())
            .font(.system(size: 10, weight: .semibold))
            .tracking(0.7)
            .foregroundStyle(Theme.textTertiary)
            .lineLimit(1)
    }
}

private struct SpecRow: View {
    let item: SpecItem
    let wide: Bool
    let expanded: Bool
    let toggle: () -> Void
    @State private var hover = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button(action: toggle) { summary }
                .buttonStyle(.plain)
                .accessibilityHint(expanded ? "Hide measurement method" : "Show measurement method")
            if expanded {
                SpecDetail(item: item)
                    .padding(.leading, SpecColumns.titleLead)
                    .padding(.trailing, SpecColumns.inset)
                    .padding(.bottom, 16)
                    .transition(.asymmetric(insertion: .opacity.combined(with: .offset(y: -6)), removal: .opacity))
            }
        }
        .background(Color.white.opacity(expanded ? 0.02 : hover ? 0.025 : 0))
        .clipped()
        .onHover { hover = $0 }
        .animation(.easeOut(duration: 0.12), value: hover)
    }

    private var summary: some View {
        let color = Theme.color(for: item.verdict)
        return HStack(alignment: .firstTextBaseline, spacing: SpecColumns.gap) {
            Text(item.id)
                .font(Theme.mono(12.5, .semibold))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: SpecColumns.id, alignment: .leading)
            VStack(alignment: .leading, spacing: 2) {
                Text(item.title)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(Theme.textPrimary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                if !wide {
                    Text(item.unit).font(Theme.mono(11)).foregroundStyle(Theme.textTertiary).lineLimit(1)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if wide {
                Text(item.unit)
                    .font(Theme.mono(11.5))
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(width: SpecColumns.unit, alignment: .leading)
            }
            Text(item.threshold)
                .font(Theme.mono(12))
                .foregroundStyle(Theme.textPrimary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
                .frame(width: SpecColumns.threshold(wide), alignment: .leading)
            Text(item.measured)
                .font(Theme.mono(12))
                .foregroundStyle(item.verdict == .pending ? Theme.textTertiary : Theme.textPrimary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
                .contentTransition(.opacity)
                .frame(width: SpecColumns.measured(wide), alignment: .leading)
            StatusPill(text: item.verdict.title, color: color)
                .fixedSize()
                .frame(width: SpecColumns.verdict, alignment: .leading)
                .alignmentGuide(.firstTextBaseline) { $0[VerticalAlignment.center] + 4 }
            Image(systemName: "chevron.right")
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(hover || expanded ? Theme.textSecondary : Theme.textTertiary)
                .rotationEffect(.degrees(expanded ? 90 : 0))
                .frame(width: SpecColumns.chevron)
        }
        .padding(.horizontal, SpecColumns.inset)
        .padding(.vertical, 12)
        .contentShape(.rect)
    }
}

private struct SpecDetail: View {
    let item: SpecItem

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 24) {
                VStack(alignment: .leading, spacing: 5) {
                    Eyebrow(text: "Measurement method")
                    Text(item.method)
                        .font(.system(size: 12.5))
                        .foregroundStyle(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                VStack(alignment: .leading, spacing: 6) {
                    Eyebrow(text: "Evidence")
                    EvidenceTags(files: item.evidence.components(separatedBy: " · "))
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            if item.id == "C5" {
                TruePositionEditor()
            }
        }
        .padding(.top, 2)
    }
}

private struct EvidenceTags: View {
    let files: [String]

    var body: some View {
        FlowRow(spacing: 6) {
            ForEach(files, id: \.self) { f in
                HStack(spacing: 5) {
                    Image(systemName: Self.symbol(for: f))
                        .font(.system(size: 9.5, weight: .medium))
                        .foregroundStyle(Theme.textTertiary)
                    Text(f).font(Theme.mono(11)).foregroundStyle(Theme.textSecondary).lineLimit(1)
                }
                .padding(.horizontal, 7)
                .frame(height: 22)
                .background(Theme.well, in: .rect(cornerRadius: 5))
                .overlay(RoundedRectangle(cornerRadius: 5).strokeBorder(Theme.hairline))
            }
        }
    }
}

extension EvidenceTags {
    static func symbol(for file: String) -> String {
        if file.hasSuffix("/") { return "folder" }
        if file.contains("video") || file.contains("recording") { return "film" }
        if file.contains("photo") || file.contains("snapshot") { return "photo" }
        return "doc.text"
    }
}

/// Minimal wrapping row for small tags.
private struct FlowRow: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxW = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, rowH: CGFloat = 0, widest: CGFloat = 0
        for s in subviews {
            let size = s.sizeThatFits(.unspecified)
            if x > 0, x + size.width > maxW { x = 0; y += rowH + spacing; rowH = 0 }
            x += size.width + spacing
            widest = max(widest, x - spacing)
            rowH = max(rowH, size.height)
        }
        return CGSize(width: min(widest, maxW), height: y + rowH)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, rowH: CGFloat = 0
        for s in subviews {
            let size = s.sizeThatFits(.unspecified)
            if x > bounds.minX, x + size.width > bounds.maxX { x = bounds.minX; y += rowH + spacing; rowH = 0 }
            s.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowH = max(rowH, size.height)
        }
    }
}

// MARK: - C5 tape-measured true positions

private struct TruePositionEditor: View {
    @Environment(AppModel.self) private var model
    @State private var objects: [RunObject] = []
    @State private var loaded = false
    @State private var trueX: [Int: String] = [:]
    @State private var trueY: [Int: String] = [:]

    private var run: RunSummary? {
        model.runs.missionRuns.first { $0.id == model.spec.evaluatedRun }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Eyebrow(text: "Expert tape measurement · true positions (m)")
                Spacer(minLength: 8)
                if !objects.isEmpty {
                    Button("Clear") { clear() }
                        .buttonStyle(.quiet)
                        .disabled(trueX.values.allSatisfy(\.isEmpty) && trueY.values.allSatisfy(\.isEmpty))
                    Button("Apply & re-evaluate", systemImage: "checkmark") { apply() }
                        .buttonStyle(.secondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            content
        }
        .padding(12)
        .background(Theme.well, in: .rect(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Theme.hairline))
        .task(id: model.spec.evaluatedRun) { await load() }
    }

    @ViewBuilder private var content: some View {
        if !loaded {
            Text("Loading objects…").font(.system(size: 12)).foregroundStyle(Theme.textTertiary)
        } else if objects.isEmpty {
            Text(run == nil ? "Evaluate a mission run first - its reported objects appear here."
                            : "The evaluated run reported no objects.")
                .font(.system(size: 12)).foregroundStyle(Theme.textTertiary)
        } else {
            Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 6) {
                GridRow {
                    head("Obj"); head("Class"); head("Reported X, Y"); head("True X"); head("True Y"); head("Error")
                }
                ForEach(objects) { o in
                    GridRow {
                        Text("#\(o.id)").font(Theme.mono(12)).foregroundStyle(Theme.textSecondary)
                        HStack(spacing: 5) {
                            Image(systemName: Theme.symbol(forObject: o.name))
                                .font(.system(size: 10))
                                .foregroundStyle(Theme.color(forObject: o.name))
                            Text(o.name).font(.system(size: 12.5)).foregroundStyle(Theme.textPrimary)
                        }
                        Text(String(format: "%.2f, %.2f", o.x, o.y)).font(Theme.mono(12)).foregroundStyle(Theme.textSecondary)
                        CoordField(text: bindX(o.id))
                        CoordField(text: bindY(o.id))
                        errorText(o)
                    }
                }
            }
        }
    }

    private func head(_ s: String) -> some View {
        Text(s.uppercased()).font(.system(size: 9.5, weight: .semibold)).tracking(0.6).foregroundStyle(Theme.textTertiary)
    }

    @ViewBuilder private func errorText(_ o: RunObject) -> some View {
        if let x = Self.parse(trueX[o.id]), let y = Self.parse(trueY[o.id]) {
            let e = hypot(o.x - x, o.y - y)
            Text(String(format: "%.2f m", e))
                .font(Theme.mono(12, .medium))
                .foregroundStyle(e <= 0.5 ? Theme.ok : Theme.critical)
                .contentTransition(.numericText())
        } else {
            Text("—").font(Theme.mono(12)).foregroundStyle(Theme.textTertiary)
        }
    }

    private func bindX(_ id: Int) -> Binding<String> {
        Binding(get: { trueX[id] ?? "" }, set: { trueX[id] = $0 })
    }

    private func bindY(_ id: Int) -> Binding<String> {
        Binding(get: { trueY[id] ?? "" }, set: { trueY[id] = $0 })
    }

    private static func parse(_ s: String?) -> Double? {
        guard let s, !s.isEmpty else { return nil }
        return Double(s.replacingOccurrences(of: ",", with: ".").trimmingCharacters(in: .whitespaces))
    }

    private func load() async {
        guard let run else { objects = []; loaded = true; return }
        let detail = await Task.detached(priority: .userInitiated) { RunsStore.loadDetail(run) }.value
        objects = detail.objects
        for (id, p) in model.spec.truePositions {
            trueX[id] = String(format: "%.2f", p.x)
            trueY[id] = String(format: "%.2f", p.y)
        }
        loaded = true
    }

    private func apply() {
        var positions: [Int: (x: Double, y: Double)] = [:]
        for o in objects {
            if let x = Self.parse(trueX[o.id]), let y = Self.parse(trueY[o.id]) { positions[o.id] = (x, y) }
        }
        model.spec.truePositions = positions
        model.spec.evaluate(latest: run)
    }

    private func clear() {
        trueX.removeAll()
        trueY.removeAll()
        model.spec.truePositions = [:]
        model.spec.evaluate(latest: run)
    }
}

private struct CoordField: View {
    @Binding var text: String
    @FocusState private var focused: Bool

    var body: some View {
        TextField("", text: $text, prompt: Text("—").foregroundStyle(Theme.textTertiary))
            .textFieldStyle(.plain)
            .font(Theme.mono(12))
            .focused($focused)
            .padding(.horizontal, 7)
            .frame(width: 72, height: 24)
            .background(Theme.panel, in: .rect(cornerRadius: 6))
            .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(focused ? Theme.hairlineStrong : Theme.hairline))
            .animation(.easeOut(duration: 0.12), value: focused)
    }
}

// MARK: - M1–M3

/// Three equal columns whose CONTENTS / FUNCTION / CRITERION / STATUS rows line up across modules.
private struct ModulesPanel: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let modules = model.spec.modules
        GlassCard(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader(title: "Functional modules", symbol: "square.stack.3d.up",
                           trailing: Text("\(modules.filter(\.done).count) / \(modules.count) demonstrated")
                    .font(Theme.mono(11)).foregroundStyle(Theme.textTertiary).eraseToAnyView())
                    .padding(.horizontal, 18)
                    .padding(.top, 14)
                    .padding(.bottom, 10)
                Rectangle().fill(Theme.hairline).frame(height: 1)
                EqualColumns(columns: modules.count) {
                    row(modules) { ModuleTitle(module: $0) }
                    row(modules) { field("Contents", $0.contents, mono: false, primary: false) }
                    row(modules) { field("Verifiable function", $0.function, mono: false, primary: true) }
                    row(modules) { field("Pass criterion", $0.criterion, mono: true, primary: true) }
                    row(modules, last: true) { ModuleStatus(module: $0) }
                }
                .overlay { separators(modules.count) }
            }
        }
    }

    private func row<Cell: View>(_ modules: [SpecModule], last: Bool = false,
                                 @ViewBuilder cell: @escaping (SpecModule) -> Cell) -> some View {
        ForEach(modules) { m in
            cell(m)
                .padding(.horizontal, 18)
                .padding(.top, last ? 0 : 14)
                .frame(maxWidth: .infinity, alignment: .topLeading)
        }
    }

    private func separators(_ count: Int) -> some View {
        HStack(spacing: 0) {
            ForEach(0..<max(count, 1), id: \.self) { i in
                if i > 0 { Rectangle().fill(Theme.hairline).frame(width: 1) }
                Color.clear
            }
        }
        .allowsHitTesting(false)
    }

    private func field(_ title: String, _ text: String, mono: Bool, primary: Bool) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Eyebrow(text: title)
            Text(text)
                .font(mono ? Theme.mono(11.5) : .system(size: 12.5))
                .foregroundStyle(primary ? Theme.textPrimary : Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

/// Row-major grid with exactly equal column widths; each row is as tall as its tallest cell.
private struct EqualColumns: Layout {
    let columns: Int

    private func rowHeights(_ subviews: Subviews, columnWidth: CGFloat) -> [CGFloat] {
        let n = max(columns, 1)
        return stride(from: 0, to: subviews.count, by: n).map { start in
            subviews[start..<min(start + n, subviews.count)]
                .map { $0.sizeThatFits(ProposedViewSize(width: columnWidth, height: nil)).height }
                .max() ?? 0
        }
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 900
        let cw = width / CGFloat(max(columns, 1))
        return CGSize(width: width, height: rowHeights(subviews, columnWidth: cw).reduce(0, +))
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let n = max(columns, 1)
        let cw = bounds.width / CGFloat(n)
        let heights = rowHeights(subviews, columnWidth: cw)
        var y = bounds.minY
        for (r, h) in heights.enumerated() {
            for c in 0..<n where r * n + c < subviews.count {
                subviews[r * n + c].place(at: CGPoint(x: bounds.minX + CGFloat(c) * cw, y: y), anchor: .topLeading,
                                          proposal: ProposedViewSize(width: cw, height: h))
            }
            y += h
        }
    }
}

private struct ModuleTitle: View {
    let module: SpecModule

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(module.id).font(Theme.mono(12.5, .semibold)).foregroundStyle(Theme.textSecondary)
            Text(module.title)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(Theme.textPrimary)
                .lineLimit(1)
                .minimumScaleFactor(0.85)
        }
        .padding(.top, 2)
    }
}

private struct ModuleStatus: View {
    let module: SpecModule

    var body: some View {
        let color = module.done ? Theme.ok : Theme.caution
        VStack(spacing: 0) {
            Rectangle().fill(Theme.hairline).frame(height: 1).padding(.top, 16)
            HStack(spacing: 7) {
                Circle().fill(color).frame(width: 6, height: 6)
                Text(module.status).font(.system(size: 12, weight: .medium)).foregroundStyle(color).lineLimit(1)
                Spacer(minLength: 0)
            }
            .padding(.vertical, 14)
        }
    }
}

// MARK: - Checklist

private struct ChecklistPanel: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        let spec = model.spec
        let complete = spec.checked.count == spec.checklist.count
        GlassCard(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                VStack(alignment: .leading, spacing: 12) {
                    CardHeader(title: "Pre-test start-up checklist", symbol: "checklist", trailing: trailing.eraseToAnyView())
                    ProgressTrack(value: spec.checklistProgress, color: complete ? Theme.ok : Theme.textSecondary)
                }
                .padding(.horizontal, 18)
                .padding(.top, 14)
                .padding(.bottom, 12)
                ForEach(Array(spec.checklist.enumerated()), id: \.element.id) { i, item in
                    Rectangle().fill(Theme.hairline).frame(height: 1)
                    ChecklistRow(index: i + 1, text: item.text, on: spec.checked.contains(item.id)) {
                        withAnimation(reduceMotion ? nil : .spring(duration: 0.28, bounce: 0.2)) { spec.toggle(item.id) }
                    }
                }
            }
            .padding(.bottom, 4)
        }
    }

    private var trailing: some View {
        let spec = model.spec
        return HStack(spacing: 10) {
            Text("\(spec.checked.count) / \(spec.checklist.count)")
                .font(Theme.mono(11.5, .medium))
                .foregroundStyle(Theme.textSecondary)
                .contentTransition(.numericText())
            Button("Reset", systemImage: "arrow.counterclockwise") {
                withAnimation(reduceMotion ? nil : .snappy(duration: 0.25)) { spec.resetChecklist() }
            }
            .buttonStyle(.quiet)
            .disabled(spec.checked.isEmpty)
        }
        .fixedSize()
    }
}

private struct ProgressTrack: View {
    let value: Double
    let color: Color

    var body: some View {
        Capsule()
            .fill(Color.white.opacity(0.06))
            .frame(height: 4)
            .overlay(alignment: .leading) {
                GeometryReader { g in
                    Capsule().fill(color).frame(width: max(0, g.size.width * value))
                }
            }
            .accessibilityElement()
            .accessibilityLabel("Checklist progress")
            .accessibilityValue("\(Int(value * 100)) percent")
    }
}

private struct ChecklistRow: View {
    let index: Int
    let text: String
    let on: Bool
    let toggle: () -> Void
    @State private var hover = false

    var body: some View {
        Button(action: toggle) {
            HStack(spacing: 14) {
                Text(String(format: "%02d", index))
                    .font(Theme.mono(11))
                    .foregroundStyle(Theme.textTertiary)
                    .frame(width: 20, alignment: .leading)
                CheckBox(on: on, hover: hover)
                Text(text)
                    .font(.system(size: 13))
                    .foregroundStyle(on ? Theme.textSecondary : Theme.textPrimary)
                    .lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 10)
            .background(Color.white.opacity(hover ? 0.025 : 0))
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
        .animation(.easeOut(duration: 0.12), value: hover)
        .accessibilityAddTraits(on ? [.isSelected] : [])
    }
}

private struct CheckBox: View {
    let on: Bool
    let hover: Bool

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 4.5)
                .fill(on ? Theme.ok : Color.white.opacity(hover ? 0.06 : 0.02))
            RoundedRectangle(cornerRadius: 4.5)
                .strokeBorder(on ? Theme.ok : hover ? Theme.textTertiary : Theme.hairlineStrong, lineWidth: 1)
            if on {
                Image(systemName: "checkmark")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(Theme.canvas)
                    .transition(.scale(scale: 0.4).combined(with: .opacity))
            }
        }
        .frame(width: 16, height: 16)
        .scaleEffect(on ? 1 : 0.96)
    }
}

private extension String {
    var nonEmpty: String? { isEmpty ? nil : self }
}
