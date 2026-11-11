import Charts
import ImageIO
import SwiftUI

// Evidence browser: a compact, filterable run list on the left and the selected run's proof on the right
// (path map, C4 processing rate, objects table, detection timeline, snapshots). All file parsing and
// image decoding happens off the main actor.

struct ResultsView: View {
    @Environment(AppModel.self) private var model
    @State private var selectedID: String?
    @State private var filter: RunFilter = .all
    @State private var showEmpty = false
    @State private var loaded: LoadedRun?
    @State private var slowLoad = false
    @State private var detailWidth: CGFloat = 800
    @State private var detailScrolled = false

    var body: some View {
        let visible = visibleRuns
        let current = currentRun(in: visible)
        VStack(alignment: .leading, spacing: Theme.spacing) {
            PageHeader(section: .results, trailing: headerTrailing.eraseToAnyView())
            HStack(alignment: .top, spacing: Theme.spacing) {
                RunBrowser(allCount: model.runs.runs.count, visible: visible, filter: $filter,
                           showEmpty: $showEmpty, hiddenEmpty: hiddenEmptyCount, selection: $selectedID,
                           currentID: current?.id)
                    .frame(width: 280)
                    .padding(.bottom, 24)
                detailColumn(current)
            }
            .frame(maxHeight: .infinity, alignment: .top)
        }
        .padding(.horizontal, 28)
        .padding(.top, 18)
        .frame(maxWidth: 1640)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(Theme.canvas)
        .task(id: current?.id) { await load(current) }
    }

    // MARK: Data

    private var visibleRuns: [RunSummary] {
        model.runs.runs.filter { filter.matches($0) && (showEmpty || !$0.isEmptyRun) }
    }

    private var hiddenEmptyCount: Int {
        showEmpty ? 0 : model.runs.runs.filter { filter.matches($0) && $0.isEmptyRun }.count
    }

    private func currentRun(in visible: [RunSummary]) -> RunSummary? {
        // No explicit choice yet: open on the newest Case 1 run (the case this drone flies), else the newest run.
        visible.first { $0.id == selectedID } ?? visible.first { $0.caseKey.hasPrefix("case1") } ?? visible.first
    }

    private func load(_ run: RunSummary?) async {
        guard let run, loaded?.id != run.id else { return }
        // Only show the loading treatment when a load is actually slow, so fast switches never flicker.
        let timer = Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(140))
            if !Task.isCancelled { withAnimation(.easeOut(duration: 0.15)) { slowLoad = true } }
        }
        let result = await Task.detached(priority: .userInitiated) { LoadedRun.make(run) }.value
        timer.cancel()
        guard !Task.isCancelled else { return }
        withAnimation(.snappy(duration: 0.2)) {
            loaded = result
            slowLoad = false
        }
    }

    // MARK: Views

    private var headerTrailing: some View {
        HStack(spacing: 10) {
            if model.runs.isLoading { ProgressView().controlSize(.small) }
            Button("Reload", systemImage: "arrow.clockwise") { model.runs.reload() }
                .buttonStyle(.secondary)
                .help("Rescan the runs folder")
        }
        .fixedSize()
    }

    @ViewBuilder private func detailColumn(_ run: RunSummary?) -> some View {
        if let run {
            ScrollView {
                RunDetailPane(run: run, loaded: loaded, loading: loaded?.id != run.id, slow: slowLoad, width: detailWidth)
                    .padding(.bottom, 28)
            }
            .scrollIndicators(.automatic)
            .scrollEdgeEffectStyle(.soft, for: .top)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { detailWidth = $0 }
            .onScrollGeometryChange(for: Bool.self) { $0.contentOffset.y > 2 } action: { _, now in detailScrolled = now }
            .overlay(alignment: .top) {
                LinearGradient(colors: [Theme.canvas, Theme.canvas.opacity(0)], startPoint: .top, endPoint: .bottom)
                    .frame(height: 14)
                    .opacity(detailScrolled ? 1 : 0)
                    .animation(.easeOut(duration: 0.15), value: detailScrolled)
                    .allowsHitTesting(false)
            }
        } else {
            GlassCard {
                ContentUnavailableView {
                    Label(model.runs.runs.isEmpty ? "No runs yet" : "No runs match", systemImage: "tray")
                } description: {
                    Text(model.runs.runs.isEmpty
                         ? "Run the simulation or copy flight logs back from the drone."
                         : "Nothing in “\(filter.title)”. Try another filter or show empty runs.")
                } actions: {
                    if !model.runs.runs.isEmpty {
                        Button("Show all runs") { filter = .all; showEmpty = true }.buttonStyle(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, minHeight: 320)
            }
            .frame(maxWidth: .infinity, alignment: .top)
        }
    }
}

// MARK: - Filtering & presentation

private enum RunFilter: String, CaseIterable, Identifiable {
    case missions, simulations, flightTests, all
    var id: String { rawValue }

    var title: String {
        switch self {
        case .missions: "Missions"
        case .simulations: "Simulations"
        case .flightTests: "Flight tests"
        case .all: "All"
        }
    }

    func matches(_ r: RunSummary) -> Bool {
        switch self {
        case .missions: r.kind == .mission && !r.isMock
        case .simulations: r.kind == .mission && r.isMock
        case .flightTests: r.kind != .mission
        case .all: true
        }
    }
}

private enum Fmt {
    static let gb = Locale(identifier: "en_GB")
    static let time = Date.FormatStyle(locale: gb).hour(.twoDigits(amPM: .omitted)).minute(.twoDigits).second(.twoDigits)
    static let day = Date.FormatStyle(locale: gb).weekday(.abbreviated).day(.twoDigits).month(.abbreviated)
    static let full = Date.FormatStyle(locale: gb).day(.twoDigits).month(.abbreviated).year().hour(.twoDigits(amPM: .omitted)).minute(.twoDigits).second(.twoDigits)

    static func duration(_ s: Double) -> String {
        guard s >= 1 else { return "—" }
        let t = Int(s.rounded())
        return t < 60 ? "\(t) s" : String(format: "%d:%02d", t / 60, t % 60)
    }
}

private extension RunSummary {
    /// Folder prefix before the timestamp, e.g. "case1_fire".
    var caseKey: String {
        guard kind == .mission, let r = id.range(of: #"_\d{8}_\d{6}"#, options: .regularExpression) else { return "" }
        return String(id[..<r.lowerBound])
    }

    var displayTitle: String {
        switch kind {
        case .hover: return "Hover test"
        case .roam: return "ArUco roam test"
        case .mission: break
        }
        let key = caseKey
        if key.hasPrefix("case1") { return "Case 1 · Fire survey" }
        return key.isEmpty ? "Mission" : key
    }

    var kindTag: String? {
        switch kind {
        case .mission: isMock ? "SIM" : "FLIGHT"
        case .hover, .roam: "TEST"
        }
    }

    /// summary.json duration, falling back to the fps_summary span (mock runs log 0 s).
    var listDuration: Double {
        if duration >= 1 { return duration }
        let spans = fps?.cameras.values.compactMap { $0["run"]?.seconds } ?? []
        return Double(spans.max() ?? 0)
    }

    /// Flight-test logs are never "empty": their duration comes from a CSV scan that can read 0.
    var isEmptyRun: Bool { kind == .mission && listDuration < 1 }

    var resultText: String { result == "?" ? "unknown" : result }

    var statusColor: Color {
        let r = result.lowercased()
        if r.contains("abort") || r.contains("fail") || r.contains("error") || r.contains("crash") { return Theme.critical }
        if succeeded { return Theme.ok }
        if r == "?" || r.contains("see log") { return Theme.textTertiary }
        return Theme.caution
    }
}

// MARK: - Run list

private struct DaySection: Identifiable {
    let id: String
    let date: Date?
    let runs: [RunSummary]
}

private struct RunBrowser: View {
    let allCount: Int
    let visible: [RunSummary]
    @Binding var filter: RunFilter
    @Binding var showEmpty: Bool
    let hiddenEmpty: Int
    @Binding var selection: String?
    let currentID: String?
    @FocusState private var focused: Bool

    var body: some View {
        GlassCard(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                VStack(alignment: .leading, spacing: 10) {
                    CardHeader(title: "Runs", symbol: "tray.full", trailing: countLabel.eraseToAnyView())
                    FilterBar(selection: $filter)
                    emptyToggle
                }
                .padding(.horizontal, 12)
                .padding(.top, 12)
                .padding(.bottom, 10)
                Rectangle().fill(Theme.hairline).frame(height: 1)
                list
            }
            .frame(maxHeight: .infinity, alignment: .top)
        }
        .overlay {
            RoundedRectangle(cornerRadius: Theme.radius)
                .strokeBorder(Theme.hairlineStrong, lineWidth: 1)
                .opacity(focused ? 1 : 0)
        }
        .focusable()
        .focused($focused)
        .focusEffectDisabled()
        .onKeyPress(.upArrow) { move(-1) }
        .onKeyPress(.downArrow) { move(1) }
        .onAppear { focused = true }
    }

    private var countLabel: some View {
        Text(visible.count == allCount ? "\(allCount)" : "\(visible.count) of \(allCount)")
            .font(Theme.mono(10.5))
            .foregroundStyle(Theme.textTertiary)
            .contentTransition(.numericText())
    }

    private var emptyToggle: some View {
        HStack(spacing: 8) {
            Text("Show empty runs")
                .font(.system(size: 12))
                .foregroundStyle(Theme.textSecondary)
            if hiddenEmpty > 0 {
                Text("\(hiddenEmpty) hidden")
                    .font(Theme.mono(10.5))
                    .foregroundStyle(Theme.textTertiary)
            }
            Spacer(minLength: 4)
            Toggle("Show empty runs", isOn: $showEmpty.animation(.snappy(duration: 0.2)))
                .labelsHidden()
                .toggleStyle(.switch)
                .controlSize(.mini)
                .help("Include runs shorter than 1 s (self-tests, aborted mocks)")
        }
        .frame(height: 20)
    }

    private var sections: [DaySection] {
        let cal = Calendar.current
        var out: [DaySection] = []
        var bucket: [RunSummary] = []
        var bucketDay: Date?
        for run in visible {
            let day: Date? = run.date == .distantPast ? nil : cal.startOfDay(for: run.date)
            if !bucket.isEmpty && day != bucketDay {
                out.append(DaySection(id: bucketDay.map { "\($0.timeIntervalSince1970)" } ?? "undated", date: bucketDay, runs: bucket))
                bucket = []
            }
            bucketDay = day
            bucket.append(run)
        }
        if !bucket.isEmpty {
            out.append(DaySection(id: bucketDay.map { "\($0.timeIntervalSince1970)" } ?? "undated", date: bucketDay, runs: bucket))
        }
        return out
    }

    @ViewBuilder private var list: some View {
        if visible.isEmpty {
            VStack(spacing: 8) {
                Text("No \(filter == .all ? "runs" : filter.title.lowercased()) recorded")
                    .font(.system(size: 12.5))
                    .foregroundStyle(Theme.textSecondary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .padding(.vertical, 40)
        } else {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 0, pinnedViews: [.sectionHeaders]) {
                        ForEach(sections) { section in
                            Section {
                                ForEach(section.runs) { run in
                                    RunRow(run: run, selected: run.id == currentID)
                                        .id(run.id)
                                        .onTapGesture {
                                            selection = run.id
                                            focused = true
                                        }
                                }
                            } header: {
                                DayHeader(date: section.date, count: section.runs.count)
                            }
                        }
                    }
                    .padding(.horizontal, 6)
                    .padding(.bottom, 8)
                }
                .scrollIndicators(.automatic)
                .onAppear { if let currentID { proxy.scrollTo(currentID, anchor: .center) } }
                .onChange(of: currentID) { _, id in
                    guard let id else { return }
                    withAnimation(.snappy(duration: 0.2)) { proxy.scrollTo(id) }
                }
            }
        }
    }

    private func move(_ step: Int) -> KeyPress.Result {
        guard !visible.isEmpty else { return .ignored }
        let index = visible.firstIndex { $0.id == currentID } ?? 0
        let next = min(max(index + step, 0), visible.count - 1)
        selection = visible[next].id
        return .handled
    }
}

private struct FilterBar: View {
    @Binding var selection: RunFilter
    @Namespace private var ns

    var body: some View {
        SpreadLayout(spacing: 2) {
            ForEach(RunFilter.allCases) { f in
                FilterSegment(title: f.title, selected: f == selection, ns: ns) {
                    withAnimation(.snappy(duration: 0.22)) { selection = f }
                }
            }
        }
        .padding(2)
        .background(Theme.well, in: .rect(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Theme.hairline))
    }
}

/// Lays children out at their ideal widths, then shares the leftover width equally (a segmented control
/// whose segments never truncate but still fill the bar).
private struct SpreadLayout: Layout {
    var spacing: CGFloat = 0

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let ideal = subviews.map { $0.sizeThatFits(.unspecified) }
        let natural = ideal.reduce(0) { $0 + $1.width } + spacing * CGFloat(max(0, subviews.count - 1))
        return CGSize(width: max(natural, proposal.width ?? natural), height: ideal.map(\.height).max() ?? 0)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let ideal = subviews.map { $0.sizeThatFits(.unspecified) }
        let natural = ideal.reduce(0) { $0 + $1.width } + spacing * CGFloat(max(0, subviews.count - 1))
        let extra = subviews.isEmpty ? 0 : max(0, bounds.width - natural) / CGFloat(subviews.count)
        var x = bounds.minX
        for (view, size) in zip(subviews, ideal) {
            let w = size.width + extra
            view.place(at: CGPoint(x: x, y: bounds.minY), proposal: ProposedViewSize(width: w, height: bounds.height))
            x += w + spacing
        }
    }
}

private struct FilterSegment: View {
    let title: String
    let selected: Bool
    let ns: Namespace.ID
    let action: () -> Void
    @State private var hover = false

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(selected ? Theme.textPrimary : hover ? Theme.textSecondary : Theme.textTertiary)
                .lineLimit(1)
                .fixedSize()
                .padding(.horizontal, 7)
                .frame(maxWidth: .infinity)
                .frame(height: 22)
                .background {
                    if selected {
                        RoundedRectangle(cornerRadius: 6)
                            .fill(Theme.panelRaised)
                            .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Theme.hairlineStrong, lineWidth: 0.75))
                            .matchedGeometryEffect(id: "segment", in: ns)
                    }
                }
                .contentShape(.rect)
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
        .animation(.easeOut(duration: 0.12), value: hover)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

private struct DayHeader: View {
    let date: Date?
    let count: Int

    var body: some View {
        HStack {
            Text(date.map { $0.formatted(Fmt.day) } ?? "Undated")
                .textCase(.uppercase)
            Spacer()
            Text("\(count)")
        }
        .font(Theme.mono(10, .medium))
        .tracking(0.5)
        .foregroundStyle(Theme.textTertiary)
        .padding(.horizontal, 10)
        .padding(.top, 10)
        .padding(.bottom, 4)
        .background(Theme.panel)
    }
}

private struct RunRow: View {
    let run: RunSummary
    let selected: Bool
    @State private var hover = false

    var body: some View {
        HStack(spacing: 10) {
            Circle().fill(run.statusColor).frame(width: 6, height: 6)
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(run.displayTitle)
                        .font(.system(size: 12.5, weight: selected ? .semibold : .medium))
                        .foregroundStyle(selected ? Theme.textPrimary : Theme.textPrimary.opacity(0.88))
                        .lineLimit(1)
                        .truncationMode(.tail)
                    if let tag = run.kindTag, tag != "SIM" {
                        Text(tag)
                            .font(Theme.mono(8.5, .semibold))
                            .tracking(0.4)
                            .foregroundStyle(Theme.textTertiary)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .overlay(RoundedRectangle(cornerRadius: 3).strokeBorder(Theme.hairlineStrong, lineWidth: 0.75))
                            .fixedSize()
                    }
                }
                Text(subtitle)
                    .font(Theme.mono(10.5))
                    .foregroundStyle(Theme.textTertiary)
                    .lineLimit(1)
            }
            Spacer(minLength: 6)
            if run.kind == .mission {
                HStack(spacing: 4) {
                    Image(systemName: "scope").font(.system(size: 9, weight: .semibold))
                    Text("\(run.objects)").font(Theme.mono(11, .medium))
                }
                .foregroundStyle(run.objects > 0 ? Theme.textSecondary : Theme.textTertiary)
                .fixedSize()
                .help("\(run.objects) confirmed objects")
            }
        }
        .padding(.horizontal, 10)
        .frame(height: 44)
        .background {
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.white.opacity(selected ? 0.075 : hover ? 0.035 : 0))
                .overlay {
                    if selected { RoundedRectangle(cornerRadius: 8).strokeBorder(Theme.hairline) }
                }
        }
        .contentShape(.rect)
        .onHover { hover = $0 }
        .animation(.easeOut(duration: 0.12), value: hover)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(selected ? [.isButton, .isSelected] : .isButton)
    }

    private var subtitle: String {
        var parts = [run.date == .distantPast ? "--:--:--" : run.date.formatted(Fmt.time)]
        parts.append(Fmt.duration(run.listDuration))
        if run.distance > 0 { parts.append(String(format: "%.1f m", run.distance)) }
        return parts.joined(separator: " · ")
    }
}

// MARK: - Loaded detail (built off the main actor)

private struct SeriesPoint: Identifiable, Sendable {
    let id: Int
    let series: String
    let x: Double
    let y: Double
}

private struct EventPoint: Identifiable, Sendable {
    let id: Int
    let t: Double
    let conf: Double
    let name: String
}

private struct Confirmation: Identifiable, Sendable {
    let id: Int
    let t: Double
    let conf: Double
    let label: String
    let name: String
}

private struct LoadedRun: Sendable {
    let id: String
    let detail: RunDetail
    let flightTime: Double
    let flightTimeSource: String
    let distance: Double
    let maxAltitude: Double?
    let altitude: [SeriesPoint]
    let fps: [SeriesPoint]
    let fpsSeriesNames: [String]
    let fpsMax: Double
    let events: [EventPoint]
    let confirmations: [Confirmation]
    let eventSpan: Double

    static func make(_ run: RunSummary) -> LoadedRun {
        var d = RunsStore.loadDetail(run)
        backfill(&d, run: run)

        // flight time: summary -> log.txt span -> perf span -> CSV last t
        var time = run.duration, source = "summary.json"
        if time < 1, let span = logSpan(d.log) { time = span; source = "log.txt" }
        if time < 1, let perf = d.fpsSeries.map(\.second).max(), perf > 0 { time = Double(perf + 1); source = "perf.csv" }

        // distance: summary, else integrate the path
        var dist = run.distance
        if dist <= 0, d.path.count > 1 {
            dist = zip(d.path, d.path.dropFirst()).reduce(0) { acc, p in
                let step = ((p.1.x - p.0.x) * (p.1.x - p.0.x) + (p.1.y - p.0.y) * (p.1.y - p.0.y)).squareRoot()
                return step < 1.5 ? acc + step : acc   // ignore pose jumps
            }
        }

        // altitude (flight-test CSVs are NED-ish: negative z is up)
        var alt: [SeriesPoint] = []
        var maxAlt: Double?
        if run.kind != .mission, !d.altitude.isEmpty {
            let negatives = d.altitude.filter { $0.z < -0.05 }.count
            let flip = negatives > d.altitude.count / 3
            let stride = max(1, d.altitude.count / 600)
            for (i, a) in d.altitude.enumerated() where i % stride == 0 {
                alt.append(SeriesPoint(id: i, series: "alt", x: a.t, y: flip ? -a.z : a.z))
            }
            maxAlt = alt.map(\.y).max()
        } else if !d.altitude.isEmpty {
            maxAlt = d.altitude.map(\.z).max()
        }

        // FPS: merge identical camera series into one labelled line
        var byCam: [String: [FPSPoint]] = [:]
        for p in d.fpsSeries { byCam[p.camera, default: []].append(p) }
        var fps: [SeriesPoint] = []
        var names: [String] = []
        let thermal = byCam["thermal"] ?? []
        let rgb = byCam["rgb"] ?? []
        if !thermal.isEmpty, thermal.map(\.fps) == rgb.map(\.fps) {
            names = ["thermal + rgb"]
            fps = thermal.map { SeriesPoint(id: $0.id, series: "thermal + rgb", x: Double($0.second), y: $0.fps) }
        } else {
            for cam in byCam.keys.sorted(by: { a, b in a == "thermal" ? true : b == "thermal" ? false : a < b }) {
                names.append(cam)
                fps += (byCam[cam] ?? []).map { SeriesPoint(id: $0.id, series: cam, x: Double($0.second), y: $0.fps) }
            }
        }

        // detection events relative to the first event
        let t0 = d.events.first?.time
        var events: [EventPoint] = []
        var confs: [Confirmation] = []
        let objectsByTime = d.objects.sorted { ($0.confirmed ?? .distantFuture) < ($1.confirmed ?? .distantFuture) }
        let evStride = max(1, d.events.count / 1500)
        for (i, e) in d.events.enumerated() {
            let t = t0.map { e.time.timeIntervalSince($0) } ?? 0
            if e.confirmedNow {
                let k = confs.count
                let label = k < objectsByTime.count ? "#\(objectsByTime[k].id)" : "#\(k + 1)"
                confs.append(Confirmation(id: i, t: t, conf: e.conf, label: label, name: e.name))
            } else if i % evStride == 0 {
                events.append(EventPoint(id: i, t: t, conf: e.conf, name: e.name))
            }
        }
        let span = max(events.map(\.t).max() ?? 0, confs.map(\.t).max() ?? 0)

        return LoadedRun(id: run.id, detail: d, flightTime: time, flightTimeSource: source, distance: dist,
                         maxAltitude: maxAlt, altitude: alt, fps: fps, fpsSeriesNames: names,
                         fpsMax: fps.map(\.y).max() ?? 0, events: events, confirmations: confs, eventSpan: span)
    }

    /// RunsStore splits CSVs on "\n", which never matches the CRLF line endings Python's csv module writes
    /// (Swift treats "\r\n" as one Character), so those files come back empty. Re-read them here.
    private static func backfill(_ d: inout RunDetail, run: RunSummary) {
        func rows(_ url: URL) -> [[String]] {
            guard let text = try? String(contentsOf: url, encoding: .utf8) else { return [] }
            return text.split(whereSeparator: \.isNewline).dropFirst().map {
                $0.split(separator: ",", omittingEmptySubsequences: false).map(String.init)
            }
        }
        if run.kind != .mission {
            guard d.path.isEmpty, d.altitude.isEmpty,
                  let text = try? String(contentsOf: run.folder, encoding: .utf8),
                  let head = text.split(whereSeparator: \.isNewline).first?.split(separator: ",").map(String.init) else { return }
            let ix = head.firstIndex(of: "x"), iy = head.firstIndex(of: "y"), iz = head.firstIndex(of: "z"), it = head.firstIndex(of: "t")
            for r in rows(run.folder) {
                if let ix, let iy, max(ix, iy) < r.count, let x = Double(r[ix]), let y = Double(r[iy]), x.isFinite, y.isFinite {
                    d.path.append(SIMD2(x, y))
                }
                if let iz, let it, max(iz, it) < r.count, let z = Double(r[iz]), let t = Double(r[it]), z.isFinite {
                    d.altitude.append((t, z))
                }
            }
            return
        }
        let dir = run.folder
        if d.path.isEmpty {
            for r in rows(dir.appending(path: "path.csv")) {
                let c = r.compactMap { Double($0) }
                if c.count >= 2 { d.path.append(SIMD2(c[0], c[1])) }
                if c.count >= 3 { d.altitude.append((Double(d.altitude.count), c[2])) }
            }
        }
        if d.events.isEmpty {
            for (i, c) in rows(dir.appending(path: "events.csv")).enumerated() {
                guard c.count >= 10, let t = Double(c[1]) else { continue }
                d.events.append(RunEvent(id: i, time: Date(timeIntervalSince1970: t), camera: c[2], name: c[3],
                                         conf: Double(c[4]) ?? 0, x: Double(c[5]) ?? 0, y: Double(c[6]) ?? 0, confirmedNow: c[9] == "1"))
            }
        }
        if d.fpsSeries.isEmpty {
            var bins: [String: [Int: Int]] = [:]
            var t0: Double?
            for c in rows(dir.appending(path: "perf.csv")) {
                guard c.count >= 2, let t = Double(c[0]) else { continue }
                if t0 == nil { t0 = t }
                let sec = Int(t - (t0 ?? t))
                for cam in c[1].split(separator: "+") { bins[String(cam), default: [:]][sec, default: 0] += 1 }
            }
            var i = 0
            for (cam, b) in bins.sorted(by: { $0.key < $1.key }) {
                // drop the final partial second: it under-counts and would look like a dip below target
                let lastSec = b.keys.max() ?? 0
                for (sec, n) in b.sorted(by: { $0.key < $1.key }) where sec < lastSec || b.count == 1 {
                    d.fpsSeries.append(FPSPoint(id: i, second: sec, camera: cam, fps: Double(n)))
                    i += 1
                }
            }
        }
    }

    /// Seconds between the first and last "HH:MM:SS" stamped lines of log.txt.
    private static func logSpan(_ lines: [String]) -> Double? {
        func secs(_ s: String) -> Int? {
            let p = s.prefix(8).split(separator: ":")
            guard p.count == 3, let h = Int(p[0]), let m = Int(p[1]), let x = Int(p[2]) else { return nil }
            return h * 3600 + m * 60 + x
        }
        guard let a = lines.lazy.compactMap(secs).first, let b = lines.reversed().lazy.compactMap(secs).first else { return nil }
        let span = b >= a ? b - a : b + 86_400 - a
        return span > 0 ? Double(span) : nil
    }
}

// MARK: - Detail pane

private struct RunDetailPane: View {
    let run: RunSummary
    let loaded: LoadedRun?
    let loading: Bool
    let slow: Bool
    let width: CGFloat

    private var wide: Bool { width >= 860 }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.spacing) {
            DetailHeader(run: run, report: loaded?.id == run.id ? loaded?.detail.report : nil, busy: loading && slow)
            if let loaded {
                content(loaded)
                    .opacity(loading && slow ? 0.4 : 1)
                    .allowsHitTesting(!loading)
            } else {
                placeholder
            }
        }
    }

    @ViewBuilder private func content(_ l: LoadedRun) -> some View {
        let isMission = run.kind == .mission
        ReadoutStrip(cells: isMission ? missionReadouts(l) : testReadouts(l))
        if isMission {
            mapAndChart(map: map(l), chart: FPSChartCard(loaded: l, summary: run.fps?.best(camera: "thermal"), height: wide ? 300 : 190))
            if !l.detail.objects.isEmpty { ObjectsTable(objects: l.detail.objects, available: width) }
            if !l.events.isEmpty || !l.confirmations.isEmpty { EventTimeline(loaded: l) }
            if !l.detail.snapshots.isEmpty { SnapshotStrip(urls: l.detail.snapshots) }
        } else {
            mapAndChart(map: map(l), chart: AltitudeChartCard(loaded: l, height: wide ? 300 : 190))
        }
    }

    @ViewBuilder private func mapAndChart(map: some View, chart: some View) -> some View {
        if wide {
            HStack(alignment: .top, spacing: Theme.spacing) {
                map.frame(maxWidth: .infinity)
                chart.frame(width: max(320, min(440, width * 0.4)))
            }
        } else {
            VStack(spacing: Theme.spacing) { map; chart }
        }
    }

    private func map(_ l: LoadedRun) -> some View {
        let d = l.detail
        let objects = d.objects.map {
            MapObject(id: "\($0.id)", label: "#\($0.id) \($0.name)", name: $0.name, x: $0.x, y: $0.y,
                      time: $0.confirmed?.formatted(Fmt.time))
        }
        return GlassCard(padding: 14) {
            VStack(alignment: .leading, spacing: 10) {
                CardHeader(title: "Flight path", symbol: "point.topleft.down.to.point.bottomright.curvepath",
                           trailing: mapLegend(l).eraseToAnyView())
                if d.path.isEmpty && objects.isEmpty {
                    QuietEmpty(text: "No path recorded in this run").frame(height: wide ? 300 : 260)
                } else {
                    FieldMap(area: d.area, home: d.path.first.map { [$0.x, $0.y] }, drone: nil, track: d.path, objects: objects)
                        .frame(height: wide ? 300 : 260)
                        .clipShape(.rect(cornerRadius: 8))
                }
            }
        }
    }

    private func mapLegend(_ l: LoadedRun) -> some View {
        Text("\(l.detail.path.count) pts · \(String(format: "%.1f", l.distance)) m")
            .font(Theme.mono(10.5))
            .foregroundStyle(Theme.textTertiary)
            .lineLimit(1)
    }

    private func missionReadouts(_ l: LoadedRun) -> [Readout] {
        let counts = Dictionary(grouping: l.detail.objects, by: \.name).map { "\($0.value.count) \($0.key)" }.sorted().joined(separator: " · ")
        let fps = run.fps?.best(camera: "thermal")
        return [
            Readout(title: "Result", value: run.resultText.capitalized, color: run.statusColor, footnote: run.isMock ? "simulation" : "flight"),
            Readout(title: "Objects", value: "\(l.detail.objects.count)", footnote: counts.isEmpty ? "none confirmed" : counts),
            Readout(title: "Flight time", value: Fmt.duration(l.flightTime), footnote: "from \(l.flightTimeSource)"),
            Readout(title: "Distance", value: String(format: "%.1f", l.distance), unit: "m", footnote: "\(l.detail.path.count) samples"),
            Readout(title: "Thermal ≥10 FPS", value: fps.map { String(format: "%.0f", $0.pctAtLeast10) } ?? "—", unit: fps == nil ? nil : "%",
                    color: fps.map { $0.pctAtLeast10 >= 90 ? Theme.ok : Theme.caution },
                    footnote: fps.map { String(format: "mean %.1f FPS", $0.meanFPS) } ?? "no fps_summary.json"),
        ]
    }

    private func testReadouts(_ l: LoadedRun) -> [Readout] {
        [
            Readout(title: "Result", value: run.resultText.capitalized, color: run.statusColor, footnote: run.kind == .hover ? "hover test" : "roam test"),
            Readout(title: "Duration", value: Fmt.duration(max(run.duration, l.detail.altitude.last?.t ?? 0)), footnote: "\(l.detail.altitude.count) samples"),
            Readout(title: "Distance", value: String(format: "%.1f", l.distance), unit: "m", footnote: "integrated from x/y"),
            Readout(title: "Max altitude", value: l.maxAltitude.map { String(format: "%.2f", $0) } ?? "—", unit: "m", footnote: "from z column"),
        ]
    }

    private var placeholder: some View {
        GlassCard {
            HStack(spacing: 10) {
                ProgressView().controlSize(.small)
                Text("Loading run…").font(.system(size: 12.5)).foregroundStyle(Theme.textSecondary)
            }
            .frame(maxWidth: .infinity, minHeight: 240)
        }
    }
}

private struct DetailHeader: View {
    let run: RunSummary
    let report: URL?
    let busy: Bool

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 8) {
                    Text(run.displayTitle)
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(Theme.textPrimary)
                        .lineLimit(1)
                    StatusPill(text: run.resultText, color: run.statusColor).fixedSize()
                    if let tag = run.kindTag { StatusPill(text: tag, color: Theme.textSecondary).fixedSize() }
                }
                Text(subtitle)
                    .font(Theme.mono(11))
                    .foregroundStyle(Theme.textTertiary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .textSelection(.enabled)
            }
            .layoutPriority(1)
            Spacer(minLength: 8)
            if busy { ProgressView().controlSize(.small).transition(.opacity) }
            HStack(spacing: 4) {
                Button("Report", systemImage: "doc.text") { if let report { NSWorkspace.shared.open(report) } }
                    .disabled(report == nil)
                    .opacity(report == nil ? 0.45 : 1)
                    .help(report == nil ? "No report.html in this run" : "Open report.html")
                Button(run.kind == .mission ? "Folder" : "Log", systemImage: "folder") {
                    NSWorkspace.shared.activateFileViewerSelecting([run.folder])
                }
                .help("Reveal in Finder")
            }
            .buttonStyle(.quiet)
            .fixedSize()
        }
        .padding(.top, 2)
    }

    private var subtitle: String {
        let name = run.kind == .mission ? run.id : run.folder.lastPathComponent
        guard run.date != .distantPast else { return name }
        return "\(run.date.formatted(Fmt.full)) · \(name)"
    }
}

// MARK: - Readouts

private struct Readout: Identifiable {
    var id: String { title }
    let title: String
    let value: String
    var unit: String?
    var color: Color?
    var footnote: String?
}

private struct ReadoutStrip: View {
    let cells: [Readout]

    var body: some View {
        GlassCard(padding: 0) {
            HStack(spacing: 0) {
                ForEach(Array(cells.enumerated()), id: \.element.id) { i, cell in
                    if i > 0 { Rectangle().fill(Theme.hairline).frame(width: 1).padding(.vertical, 12) }
                    ReadoutCell(cell: cell)
                }
            }
        }
    }
}

private struct ReadoutCell: View {
    let cell: Readout

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(cell.title.uppercased())
                .font(.system(size: 10, weight: .semibold))
                .tracking(0.7)
                .foregroundStyle(Theme.textTertiary)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                if let color = cell.color {
                    Circle().fill(color).frame(width: 6, height: 6)
                        .alignmentGuide(.firstTextBaseline) { $0[.bottom] + 1 }
                        .padding(.trailing, 3)
                }
                Text(cell.value)
                    .font(Theme.mono(18, .medium))
                    .foregroundStyle(Theme.textPrimary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                    .contentTransition(.numericText())
                if let unit = cell.unit {
                    Text(unit).font(Theme.mono(11)).foregroundStyle(Theme.textSecondary).fixedSize()
                }
            }
            Text(cell.footnote ?? " ")
                .font(.system(size: 10.5))
                .foregroundStyle(Theme.textTertiary)
                .lineLimit(1)
                .truncationMode(.tail)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Charts

private struct ChartStyle: ViewModifier {
    func body(content: Content) -> some View {
        content
            .chartYAxis {
                AxisMarks(position: .leading, values: .automatic(desiredCount: 4)) { _ in
                    AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5, dash: [2, 3])).foregroundStyle(Color.white.opacity(0.06))
                    AxisValueLabel().font(.system(size: 10)).foregroundStyle(Theme.textTertiary)
                }
            }
            .chartXAxis {
                AxisMarks(values: .automatic(desiredCount: 5)) { value in
                    AxisValueLabel {
                        if let v = value.as(Double.self) { Text("\(Int(v)) s") }
                    }
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.textTertiary)
                }
            }
    }
}

private extension View {
    func instrumentChart() -> some View { modifier(ChartStyle()) }
}

private let areaFill = LinearGradient(colors: [Theme.signal.opacity(0.25), Theme.signal.opacity(0)], startPoint: .top, endPoint: .bottom)

private struct FPSChartCard: View {
    let loaded: LoadedRun
    let summary: FPSSummary.Span?
    var height: CGFloat = 300

    var body: some View {
        GlassCard(padding: 14) {
            VStack(alignment: .leading, spacing: 10) {
                CardHeader(title: "Processing rate · C4", symbol: "speedometer", trailing: trailing.eraseToAnyView())
                if loaded.fps.isEmpty {
                    QuietEmpty(text: "No perf.csv in this run").frame(height: height)
                } else {
                    chart.frame(height: height)
                }
            }
        }
    }

    private var trailing: some View {
        Group {
            if let s = summary {
                Text(String(format: "mean %.1f FPS", s.meanFPS))
            }
        }
        .font(Theme.mono(10.5))
        .foregroundStyle(Theme.textTertiary)
    }

    private var chart: some View {
        let primary = loaded.fpsSeriesNames.first ?? ""
        let top = max(15, loaded.fpsMax * 1.18)
        return Chart {
            ForEach(loaded.fps.filter { $0.series == primary }) { p in
                AreaMark(x: .value("s", p.x), y: .value("FPS", p.y))
                    .foregroundStyle(areaFill)
                    .interpolationMethod(.monotone)
            }
            ForEach(loaded.fps) { p in
                LineMark(x: .value("s", p.x), y: .value("FPS", p.y), series: .value("Camera", p.series))
                    .foregroundStyle(p.series == primary ? Theme.signal : Theme.textSecondary)
                    .lineStyle(StrokeStyle(lineWidth: p.series == primary ? 2 : 1.25))
                    .interpolationMethod(.monotone)
            }
            RuleMark(y: .value("Target", 10))
                .foregroundStyle(Theme.caution.opacity(0.7))
                .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))
                .annotation(position: .top, alignment: .trailing, spacing: 2) {
                    Text("10 FPS TARGET").font(Theme.mono(9, .semibold)).foregroundStyle(Theme.caution.opacity(0.85))
                }
            ForEach(lastPoints) { p in
                PointMark(x: .value("s", p.x), y: .value("FPS", p.y))
                    .symbolSize(18)
                    .foregroundStyle(p.series == primary ? Theme.signal : Theme.textSecondary)
                    .annotation(position: .top, alignment: .trailing, spacing: 4) {
                        Text(p.series).font(Theme.mono(9.5)).foregroundStyle(Theme.textSecondary)
                    }
            }
        }
        .chartYScale(domain: 0...top)
        .chartXScale(domain: 0...max(1, loaded.fps.map(\.x).max() ?? 1))
        .instrumentChart()
    }

    private var lastPoints: [SeriesPoint] {
        loaded.fpsSeriesNames.compactMap { name in loaded.fps.last { $0.series == name } }
    }
}

private struct AltitudeChartCard: View {
    let loaded: LoadedRun
    var height: CGFloat = 300

    var body: some View {
        GlassCard(padding: 14) {
            VStack(alignment: .leading, spacing: 10) {
                CardHeader(title: "Altitude", symbol: "arrow.up.and.down",
                           trailing: Text(loaded.maxAltitude.map { String(format: "max %.2f m", $0) } ?? "")
                               .font(Theme.mono(10.5)).foregroundStyle(Theme.textTertiary).eraseToAnyView())
                if loaded.altitude.isEmpty {
                    QuietEmpty(text: "No z column in this log").frame(height: height)
                } else {
                    Chart(loaded.altitude) { p in
                        AreaMark(x: .value("t", p.x), y: .value("m", p.y))
                            .foregroundStyle(areaFill)
                            .interpolationMethod(.monotone)
                        LineMark(x: .value("t", p.x), y: .value("m", p.y))
                            .foregroundStyle(Theme.signal)
                            .lineStyle(StrokeStyle(lineWidth: 2))
                            .interpolationMethod(.monotone)
                    }
                    .chartYScale(domain: 0...max(1.5, (loaded.maxAltitude ?? 1) * 1.2))
                    .instrumentChart()
                    .frame(height: height)
                }
            }
        }
    }
}

private struct EventTimeline: View {
    let loaded: LoadedRun

    var body: some View {
        GlassCard(padding: 14) {
            VStack(alignment: .leading, spacing: 10) {
                CardHeader(title: "Detection events · events.csv", symbol: "waveform.path.ecg", trailing: legend.eraseToAnyView())
                chart.frame(height: 170)
            }
        }
    }

    private var legend: some View {
        HStack(spacing: 12) {
            HStack(spacing: 5) {
                Circle().fill(Theme.accent.opacity(0.5)).frame(width: 5, height: 5)
                Text("\(loaded.events.count + loaded.confirmations.count) detections")
            }
            HStack(spacing: 5) {
                Image(systemName: "diamond.fill").font(.system(size: 7)).foregroundStyle(Theme.accent)
                Text("confirmed")
            }
        }
        .font(Theme.mono(10.5))
        .foregroundStyle(Theme.textTertiary)
        .fixedSize()
    }

    private var chart: some View {
        Chart {
            ForEach(loaded.confirmations) { c in
                RuleMark(x: .value("t", c.t))
                    .foregroundStyle(Theme.accent.opacity(0.35))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [2, 3]))
            }
            ForEach(loaded.events) { e in
                PointMark(x: .value("t", e.t), y: .value("conf", e.conf))
                    .symbolSize(12)
                    .foregroundStyle(Theme.color(forObject: e.name).opacity(0.45))
            }
            ForEach(loaded.confirmations) { c in
                PointMark(x: .value("t", c.t), y: .value("conf", c.conf))
                    .symbol(.diamond)
                    .symbolSize(70)
                    .foregroundStyle(Theme.color(forObject: c.name))
                    .annotation(position: .top, spacing: 4) {
                        Text(c.label).font(Theme.mono(10, .semibold)).foregroundStyle(Theme.textPrimary)
                    }
            }
        }
        .chartYScale(domain: 0...1.15)
        .chartXScale(domain: 0...max(1, loaded.eventSpan * 1.02))
        .chartYAxis {
            AxisMarks(position: .leading, values: [0, 0.5, 1]) { _ in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5, dash: [2, 3])).foregroundStyle(Color.white.opacity(0.06))
                AxisValueLabel().font(.system(size: 10)).foregroundStyle(Theme.textTertiary)
            }
        }
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 6)) { value in
                AxisValueLabel {
                    if let v = value.as(Double.self) { Text(String(format: "+%.0f s", v)) }
                }
                .font(.system(size: 10))
                .foregroundStyle(Theme.textTertiary)
            }
        }
    }
}

// MARK: - Objects table

/// Fixed column widths for the objects table.
private enum W {
    static let id: CGFloat = 26, cls: CGFloat = 92, num: CGFloat = 58, conf: CGFloat = 46, hits: CGFloat = 42, time: CGFloat = 66, thumb: CGFloat = 40
}

private struct ObjectsTable: View {
    let objects: [RunObject]
    let available: CGFloat

    /// Columns keep fixed proportions; on wide panes they grow together (up to 2x) so the table fills the card.
    private var scale: CGFloat {
        let base = W.id + W.cls + W.num * 2 + W.conf + W.hits + W.time + W.thumb
        let room = available - 28 - 12 * 8 - W.thumb - W.id
        return min(2, max(1, room / (base - W.thumb - W.id)))
    }

    var body: some View {
        GlassCard(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader(title: "Confirmed objects · report.csv", symbol: "tablecells",
                           trailing: Text("\(objects.count)").font(Theme.mono(10.5)).foregroundStyle(Theme.textTertiary).eraseToAnyView())
                    .padding(.horizontal, 14)
                    .padding(.top, 12)
                    .padding(.bottom, 8)
                Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 0) {
                    headerRow
                    ForEach(objects) { o in
                        Rectangle().fill(Theme.hairline).frame(height: 1).gridCellUnsizedAxes(.horizontal)
                        ObjectRow(object: o, scale: scale)
                    }
                }
                .padding(.horizontal, 14)
                .padding(.bottom, 6)
            }
        }
    }

    private var headerRow: some View {
        GridRow {
            head("#", W.id, .leading)
            head("Class", W.cls * scale, .leading)
            head("X m", W.num * scale, .trailing)
            head("Y m", W.num * scale, .trailing)
            head("Conf", W.conf * scale, .trailing)
            head("Hits", W.hits * scale, .trailing)
            head("Time", W.time * scale, .trailing)
            head("Img", W.thumb, .trailing)
            Color.clear.frame(maxWidth: .infinity, maxHeight: 1)
        }
        .frame(height: 24)
    }

    private func head(_ t: String, _ w: CGFloat, _ a: Alignment) -> some View {
        Text(t.uppercased())
            .font(.system(size: 10, weight: .semibold))
            .tracking(0.6)
            .foregroundStyle(Theme.textTertiary)
            .frame(width: w, alignment: a)
    }
}

private struct ObjectRow: View {
    let object: RunObject
    let scale: CGFloat

    var body: some View {
        let w = (id: W.id, cls: W.cls * scale, num: W.num * scale, conf: W.conf * scale, hits: W.hits * scale, time: W.time * scale, thumb: W.thumb)
        GridRow {
            Text("\(object.id)").font(Theme.mono(12)).foregroundStyle(Theme.textSecondary).frame(width: w.id, alignment: .leading)
            HStack(spacing: 6) {
                Image(systemName: Theme.symbol(forObject: object.name)).font(.system(size: 10))
                    .foregroundStyle(Theme.color(forObject: object.name))
                Text(object.name.capitalized).font(.system(size: 12.5)).foregroundStyle(Theme.textPrimary).lineLimit(1)
            }
            .frame(width: w.cls, alignment: .leading)
            mono(String(format: "%.2f", object.x), w.num)
            mono(String(format: "%.2f", object.y), w.num)
            mono(String(format: "%.0f%%", object.conf * 100), w.conf)
            mono("\(object.hits)", w.hits)
            mono(object.confirmed?.formatted(Fmt.time) ?? "—", w.time)
            thumb.frame(width: w.thumb, alignment: .trailing)
            Color.clear.frame(maxWidth: .infinity, maxHeight: 1)
        }
        .frame(height: 36)
    }

    private func mono(_ s: String, _ w: CGFloat) -> some View {
        Text(s).font(Theme.mono(12)).foregroundStyle(Theme.textPrimary).lineLimit(1).frame(width: w, alignment: .trailing)
    }

    @ViewBuilder private var thumb: some View {
        if let url = object.snapshot {
            Button { NSWorkspace.shared.open(url) } label: {
                Thumbnail(url: url, maxPixel: 96)
                    .frame(width: 36, height: 24)
                    .clipShape(.rect(cornerRadius: 4))
                    .overlay(RoundedRectangle(cornerRadius: 4).strokeBorder(Theme.hairline))
            }
            .buttonStyle(.plain)
            .help("Open snapshot")
        } else {
            Text("—").font(Theme.mono(12)).foregroundStyle(Theme.textTertiary)
        }
    }
}

// MARK: - Snapshots

private struct SnapshotStrip: View {
    let urls: [URL]

    var body: some View {
        GlassCard(padding: 0) {
            VStack(alignment: .leading, spacing: 10) {
                CardHeader(title: "Snapshots at confirmation", symbol: "photo.on.rectangle",
                           trailing: Text("\(urls.count)").font(Theme.mono(10.5)).foregroundStyle(Theme.textTertiary).eraseToAnyView())
                    .padding(.horizontal, 14)
                    .padding(.top, 12)
                ScrollView(.horizontal) {
                    LazyHStack(spacing: 12) {
                        ForEach(urls, id: \.self) { SnapshotTile(url: $0) }
                    }
                    .padding(.horizontal, 14)
                    .padding(.bottom, 14)
                }
                .scrollIndicators(.automatic)
            }
        }
        .clipShape(.rect(cornerRadius: Theme.radius))
    }
}

private struct SnapshotTile: View {
    let url: URL
    @State private var hover = false

    var body: some View {
        Button { NSWorkspace.shared.open(url) } label: {
            VStack(alignment: .leading, spacing: 6) {
                Thumbnail(url: url, maxPixel: 360)
                    .frame(width: 176, height: 118)
                    .clipShape(.rect(cornerRadius: 10))
                    .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(hover ? Theme.hairlineStrong : Theme.hairline))
                Text(url.deletingPathExtension().lastPathComponent)
                    .font(Theme.mono(10.5))
                    .foregroundStyle(hover ? Theme.textSecondary : Theme.textTertiary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .frame(width: 176, alignment: .leading)
            }
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
        .animation(.easeOut(duration: 0.12), value: hover)
        .help("Open \(url.lastPathComponent)")
    }
}

/// Downsampled image loaded off the main thread via ImageIO and cached.
private struct Thumbnail: View {
    let url: URL
    let maxPixel: Int
    @State private var image: CGImage?

    var body: some View {
        ZStack {
            Theme.well
            if let image {
                Image(decorative: image, scale: 1)
                    .resizable()
                    .aspectRatio(contentMode: .fill)
                    .transition(.opacity)
            }
        }
        .task(id: url) {
            let loaded = await ThumbnailLoader.load(url, maxPixel: maxPixel)
            withAnimation(.easeOut(duration: 0.15)) { image = loaded?.image }
        }
    }
}

private struct SendableImage: @unchecked Sendable { let image: CGImage }

private enum ThumbnailLoader {
    private final class Cache: @unchecked Sendable {
        let store = NSCache<NSString, CGImage>()
        init() { store.countLimit = 200 }
    }
    private static let cache = Cache()

    static func load(_ url: URL, maxPixel: Int) async -> SendableImage? {
        let key = "\(url.path(percentEncoded: false))@\(maxPixel)" as NSString
        if let hit = cache.store.object(forKey: key) { return SendableImage(image: hit) }
        let result = await Task.detached(priority: .utility) { () -> SendableImage? in
            guard let src = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
            let opts: [CFString: Any] = [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceShouldCacheImmediately: true,
                kCGImageSourceThumbnailMaxPixelSize: maxPixel,
            ]
            return CGImageSourceCreateThumbnailAtIndex(src, 0, opts as CFDictionary).map { SendableImage(image: $0) }
        }.value
        if let result { cache.store.setObject(result.image, forKey: key) }
        return result
    }
}

// MARK: - Small pieces

private struct QuietEmpty: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.system(size: 12.5))
            .foregroundStyle(Theme.textTertiary)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Theme.well, in: .rect(cornerRadius: 8))
    }
}
