import Charts
import SwiftUI

// Module C - economic efficiency. Everything is read from `EconomicsStore` (economics/case1_fire.yaml +
// economics/out/case1_fire.{md,csv}); this file only formats and draws it.

struct EconomicsView: View {
    @Environment(AppModel.self) private var model
    @State private var width: CGFloat = 1200

    var body: some View {
        let e = model.economics
        Page(section: .economics) {
            if !e.loaded && e.attempted {
                GlassCard {
                    ContentUnavailableView {
                        Label("Economics model not found", systemImage: "chart.pie")
                    } description: {
                        Text("Needs economics/case1_fire.yaml and the toolkit .venv with PyYAML.")
                    } actions: {
                        Button("Try again", systemImage: "arrow.clockwise") { e.reload() }
                            .fixedSize()
                    }
                    .frame(maxWidth: .infinity, minHeight: 220)
                }
            } else if !e.loaded {
                GlassCard {
                    ProgressView("Loading economics model…")
                        .controlSize(.small)
                        .frame(maxWidth: .infinity, minHeight: 180)
                }
            } else {
                content(e)
            }
        }
    }

    private func content(_ e: EconomicsStore) -> some View {
        let k = EconFigures(e)
        let wide = width >= 1020
        return VStack(alignment: .leading, spacing: Theme.spacing) {
            VerdictLine(figures: k)
            ReadoutStrip(readouts: k.readouts, columns: wide ? 6 : 3)
            HStack(alignment: .top, spacing: Theme.spacing) {
                CashFlowCard(flows: e.cashFlow, payback: k.payback, years: e.years)
                BenefitsCard(benefits: e.benefits)
                    .frame(width: wide ? 400 : 360)
            }
            .fixedSize(horizontal: false, vertical: true)
            AlternativesCard(rows: k.alternatives, years: e.years, capex: e.totalCapex, opex: e.totalOpex)
            InputsCard(capex: e.capex, opex: e.opex, benefits: e.benefits,
                       footer: k.footer, excel: model.settings.toolkitRoot.appending(path: "deliverables/case1_forest_fire/06_Economics.xlsx"))
        }
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { width = $0 }
    }
}

// MARK: - Figures (parsing + fixed formatting)

private struct Readout: Identifiable {
    var id: String { title }
    let title: String
    let value: String
    let unit: String
    let note: String
}

private struct AltRow: Identifiable {
    var id: String { name }
    let name: String
    let cost: Double
    let notes: String
    let ours: Bool
}

@MainActor
private struct EconFigures {
    let npv: Double?
    let irr: Double?
    let payback: Double?
    let discountedPayback: Double?
    let roi: Double?
    let breakEven: Double?
    let rate: Double
    let years: Int
    let feasible: Bool
    let customer: String
    let alternatives: [AltRow]

    init(_ e: EconomicsStore) {
        func kpi(_ prefix: String) -> Double? {
            e.kpis.first { $0.label.hasPrefix(prefix) }.flatMap { Fmt.number($0.value) }
        }
        npv = kpi("NPV")
        irr = kpi("IRR")
        payback = kpi("Payback")
        discountedPayback = kpi("Discounted payback")
        roi = kpi("ROI")
        breakEven = kpi("Break-even")
        rate = e.discountRate
        years = e.years
        customer = e.customer
        let v = e.verdict.uppercased()
        feasible = v.contains("FEASIBLE") && !v.contains("NOT ") && !v.contains("INFEASIBLE")
        let ours = AltRow(name: "Our UAV system", cost: e.totalOpex + e.totalCapex / Double(max(1, e.years)),
                          notes: "small ignition sources in real time, with coordinates", ours: true)
        alternatives = (e.alternatives.map { AltRow(name: $0.name, cost: $0.annualCost, notes: $0.notes, ours: false) } + [ours])
            .sorted { $0.cost > $1.cost }
    }

    var ratePct: String { Fmt.pct(rate * 100, digits: rate * 100 == (rate * 100).rounded() ? 0 : 1) }

    var readouts: [Readout] {
        [
            Readout(title: "NPV", value: Fmt.millions(npv), unit: "M ₽",
                    note: npv.map { "\(Fmt.rub($0)) ₽ @ \(ratePct) %" } ?? "–"),
            Readout(title: "IRR", value: Fmt.fixed(irr, 1), unit: "%", note: "vs \(ratePct) % discount rate"),
            Readout(title: "Payback", value: Fmt.fixed(payback, 2), unit: "yr", note: "simple, undiscounted"),
            Readout(title: "Discounted payback", value: Fmt.fixed(discountedPayback, 2), unit: "yr", note: "at \(ratePct) % discount"),
            Readout(title: "ROI · \(years) yr", value: Fmt.fixed(roi, 1), unit: "%", note: "net benefit / investment"),
            Readout(title: "Break-even", value: Fmt.fixed(breakEven, 1), unit: "%", note: "of planned benefits"),
        ]
    }

    var footer: String {
        "\(customer) · horizon \(years) yr · discount rate \(ratePct) %"
    }
}

private enum Fmt {
    /// "6 205 125 RUB" -> 6205125, "57.2% of plan" -> 57.2
    static func number(_ s: String) -> Double? {
        let cleaned = s.replacingOccurrences(of: "\u{2212}", with: "-").filter { $0.isNumber || $0 == "." || $0 == "-" }
        return Double(cleaned)
    }

    static func fixed(_ v: Double?, _ digits: Int) -> String {
        guard let v else { return "–" }
        return String(format: "%.\(digits)f", v)
    }

    static func pct(_ v: Double, digits: Int) -> String { String(format: "%.\(digits)f", v) }

    static func millions(_ v: Double?) -> String {
        guard let v else { return "–" }
        return String(format: "%.2f", v / 1e6)
    }

    static func signedMillions(_ v: Double) -> String {
        let s = String(format: "%.2f", abs(v) / 1e6)
        return v < 0 ? "\u{2212}" + s : "+" + s
    }

    /// Full rouble amount with non-breaking thin grouping: 1 800 000
    static func rub(_ v: Double) -> String {
        let f = NumberFormatter()
        f.numberStyle = .decimal
        f.groupingSeparator = "\u{00A0}"
        f.maximumFractionDigits = 0
        return f.string(from: NSNumber(value: v)) ?? "\(Int(v))"
    }

    /// Splits "Fewer manned patrol flights (60 h x 60 000 RUB/h x 50%)" into title + detail.
    static func split(_ item: String) -> (title: String, detail: String?) {
        // only a trailing "(…)" is a detail; "Operator (0.5 FTE) incl. taxes" stays whole
        guard item.hasSuffix(")"), let r = item.range(of: " (", options: .backwards) else { return (item, nil) }
        var detail = String(item[r.upperBound...])
        detail.removeLast()
        detail = detail.replacingOccurrences(of: " x ", with: " × ")
        // keep "150 000" together when the line wraps
        detail = detail.replacingOccurrences(of: #"(\d) (\d{3})"#, with: "$1\u{00A0}$2", options: .regularExpression)
        return (String(item[..<r.lowerBound]), detail)
    }
}

// MARK: - Verdict

private struct VerdictLine: View {
    let figures: EconFigures

    var body: some View {
        let f = figures
        HStack(spacing: 12) {
            StatusPill(text: f.feasible ? "Feasible" : "Not feasible", color: f.feasible ? Theme.ok : Theme.critical,
                       symbol: f.feasible ? "checkmark" : "xmark")
                .fixedSize()
            Text("NPV \(num(Fmt.millions(f.npv) + " M ₽")) at \(num(f.ratePct + " %")), IRR \(num(Fmt.fixed(f.irr, 1) + " %")), pays back in \(num(Fmt.fixed(f.payback, 2) + " years")).")
                .font(.system(size: 13))
                .foregroundStyle(Theme.textSecondary)
                .lineLimit(1)
                .minimumScaleFactor(0.85)
            Spacer(minLength: 12)
            Text(f.customer)
                .font(.system(size: 12))
                .foregroundStyle(Theme.textTertiary)
                .lineLimit(1)
                .truncationMode(.tail)
                .layoutPriority(-1)
        }
        .padding(.horizontal, 14)
        .frame(height: 44)
        .background(Theme.panel, in: .rect(cornerRadius: Theme.radius))
        .overlay(RoundedRectangle(cornerRadius: Theme.radius).strokeBorder(Theme.hairline))
    }

    private func num(_ s: String) -> Text {
        Text(s).font(Theme.mono(12.5, .medium)).foregroundStyle(Theme.textPrimary)
    }
}

// MARK: - KPI readouts

private struct ReadoutStrip: View {
    let readouts: [Readout]
    let columns: Int

    var body: some View {
        let rows = stride(from: 0, to: readouts.count, by: columns).map { Array(readouts[$0..<min($0 + columns, readouts.count)]) }
        VStack(spacing: 0) {
            ForEach(rows.indices, id: \.self) { r in
                if r > 0 { Rectangle().fill(Theme.hairline).frame(height: 1) }
                HStack(spacing: 0) {
                    ForEach(rows[r]) { item in
                        if item.id != rows[r].first?.id {
                            Rectangle().fill(Theme.hairline).frame(width: 1)
                        }
                        ReadoutCell(readout: item)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
            }
        }
        .background(Theme.panel, in: .rect(cornerRadius: Theme.radius))
        .overlay(RoundedRectangle(cornerRadius: Theme.radius).strokeBorder(Theme.hairline))
        .animation(.snappy(duration: 0.2), value: columns)
    }
}

private struct ReadoutCell: View {
    let readout: Readout

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Eyebrow(text: readout.title).lineLimit(1)
            HStack(alignment: .firstTextBaseline, spacing: 5) {
                Text(readout.value)
                    .font(Theme.mono(24, .medium))
                    .foregroundStyle(Theme.textPrimary)
                Text(readout.unit)
                    .font(Theme.mono(12, .medium))
                    .foregroundStyle(Theme.textSecondary)
            }
            .lineLimit(1)
            .minimumScaleFactor(0.6)
            Text(readout.note)
                .font(.system(size: 11))
                .foregroundStyle(Theme.textTertiary)
                .lineLimit(1)
                .truncationMode(.tail)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Cash flow

private struct CashFlowCard: View {
    let flows: [CashFlowYear]
    let payback: Double?
    let years: Int

    var body: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: 14) {
                CardHeader(title: "Cash flow · \(years) years", symbol: "chart.bar.xaxis", trailing: legend.eraseToAnyView())
                CashFlowChart(flows: flows, payback: payback)
                    .frame(minHeight: 300)
            }
            .frame(maxHeight: .infinity, alignment: .top)
        }
    }

    private var legend: some View {
        HStack(spacing: 14) {
            swatch(Theme.ok.opacity(0.75), "Net")
            swatch(Theme.critical.opacity(0.7), "Investment")
            HStack(spacing: 5) {
                Capsule().fill(Theme.accent).frame(width: 12, height: 2)
                Text("Cumulative").font(.system(size: 11)).foregroundStyle(Theme.textSecondary)
            }
            Text("M ₽").font(Theme.mono(10.5)).foregroundStyle(Theme.textTertiary)
        }
        .fixedSize()
    }

    private func swatch(_ c: Color, _ t: String) -> some View {
        HStack(spacing: 5) {
            RoundedRectangle(cornerRadius: 2).fill(c).frame(width: 8, height: 8)
            Text(t).font(.system(size: 11)).foregroundStyle(Theme.textSecondary)
        }
    }
}

private struct CashFlowChart: View {
    let flows: [CashFlowYear]
    let payback: Double?

    private var lastYear: Double { Double(flows.last?.year ?? 5) }

    private var domain: ClosedRange<Double> {
        let values: [Double] = flows.map { $0.net / 1e6 } + flows.map { $0.cumulative / 1e6 } + [0]
        let lo = values.min() ?? 0, hi = values.max() ?? 1
        let span = max(1, hi - lo)
        return (lo - span * 0.08)...(hi + span * 0.14)
    }

    var body: some View {
        Chart {
            bars
            RuleMark(y: .value("Zero", 0))
                .foregroundStyle(Theme.hairlineStrong)
                .lineStyle(StrokeStyle(lineWidth: 1))
                .annotation(position: .top, alignment: .leading, spacing: 3) {
                    Text("Break-even").font(.system(size: 10, weight: .medium)).foregroundStyle(Theme.textTertiary)
                }
            cumulative
            paybackRule
        }
        .chartXScale(domain: -0.7...(lastYear + 0.7))
        .chartYScale(domain: domain)
        .chartXAxis {
            AxisMarks(values: flows.map { Double($0.year) }) { v in
                AxisValueLabel(anchor: .top, collisionResolution: .disabled) {
                    if let x = v.as(Double.self), let f = flows.first(where: { Double($0.year) == x }) {
                        AxisColumn(flow: f)
                    }
                }
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading, values: .automatic(desiredCount: 5)) { v in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 1, dash: [2, 3])).foregroundStyle(.white.opacity(0.06))
                AxisValueLabel {
                    if let y = v.as(Double.self) {
                        Text(String(format: "%.0f", y)).font(Theme.mono(10)).foregroundStyle(Theme.textTertiary)
                    }
                }
            }
        }
        .accessibilityLabel("Cash flow by year")
    }

    @ChartContentBuilder private var bars: some ChartContent {
        ForEach(flows) { f in
            barMark(f)
        }
    }

    private func barMark(_ f: CashFlowYear) -> some ChartContent {
        let x: Double = Double(f.year)
        let net: Double = f.net / 1e6
        let fill: Color = f.net < 0 ? Theme.critical.opacity(0.7) : Theme.ok.opacity(0.75)
        let x0: PlottableValue<Double> = .value("Year", x - 0.3)
        let x1: PlottableValue<Double> = .value("Year", x + 0.3)
        let y0: PlottableValue<Double> = .value("Base", 0.0)
        let y1: PlottableValue<Double> = .value("Net", net)
        return RectangleMark(xStart: x0, xEnd: x1, yStart: y0, yEnd: y1)
            .foregroundStyle(fill)
            .cornerRadius(2)
    }

    @ChartContentBuilder private var cumulative: some ChartContent {
        ForEach(flows) { f in
            LineMark(x: .value("Year", Double(f.year)), y: .value("Cumulative", f.cumulative / 1e6))
                .foregroundStyle(Theme.accent)
                .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
                .interpolationMethod(.linear)
        }
        ForEach(flows) { f in
            PointMark(x: .value("Year", Double(f.year)), y: .value("Cumulative", f.cumulative / 1e6))
                .symbol { Circle().fill(Theme.accent).stroke(Theme.panel, lineWidth: 1.5).frame(width: 8, height: 8) }
        }
        if let last = flows.last {
            PointMark(x: .value("Year", Double(last.year)), y: .value("Cumulative", last.cumulative / 1e6))
                .opacity(0)
                .annotation(position: .top, alignment: .trailing, spacing: 6) {
                    Text(Fmt.signedMillions(last.cumulative))
                        .font(Theme.mono(10.5, .semibold))
                        .foregroundStyle(Theme.accent)
                }
        }
    }

    @ChartContentBuilder private var paybackRule: some ChartContent {
        if let payback {
            RuleMark(x: .value("Payback", payback))
                .foregroundStyle(Theme.textSecondary.opacity(0.55))
                .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                .annotation(position: .top, alignment: .leading, spacing: 2,
                            overflowResolution: .init(x: .fit(to: .chart), y: .fit(to: .chart))) {
                    Text("Payback \(Fmt.fixed(payback, 2)) yr")
                        .font(Theme.mono(10, .medium))
                        .foregroundStyle(Theme.textSecondary)
                        .padding(.leading, 4)
                }
        }
    }
}

/// X-axis label column: year, net cash flow and cumulative - a data table aligned under each bar.
private struct AxisColumn: View {
    let flow: CashFlowYear

    var body: some View {
        VStack(spacing: 3) {
            Text("Y\(flow.year)").font(Theme.mono(10, .semibold)).foregroundStyle(Theme.textSecondary)
            Text(Fmt.signedMillions(flow.net))
                .font(Theme.mono(10))
                .foregroundStyle(flow.net < 0 ? Theme.critical.opacity(0.9) : Theme.ok.opacity(0.85))
            Text(Fmt.signedMillions(flow.cumulative))
                .font(Theme.mono(10))
                .foregroundStyle(Theme.accent.opacity(0.85))
        }
        .padding(.top, 4)
        // numeric axis labels start at the tick: fixed width + half-width shift centres them under the bar
        .frame(width: 48)
        .offset(x: -24)
    }
}

// MARK: - Benefits breakdown

private struct BenefitsCard: View {
    let benefits: [EconLine]

    private var total: Double { benefits.reduce(0) { $0 + $1.amount } }
    private var largestID: String? { benefits.max { $0.amount < $1.amount }?.id }

    /// One accent for the largest item, shades of the neutral signal colour for the rest.
    private func color(_ b: EconLine) -> Color {
        if b.id == largestID { return Theme.accent }
        let others = benefits.filter { $0.id != largestID }.sorted { $0.amount > $1.amount }
        let rank = others.firstIndex { $0.id == b.id } ?? 0
        return Theme.signal.opacity(max(0.25, 0.8 - Double(rank) * 0.3))
    }

    var body: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: 14) {
                CardHeader(title: "Annual benefits", symbol: "chart.pie",
                           trailing: Text("year-1 basis").font(.system(size: 11)).foregroundStyle(Theme.textTertiary).eraseToAnyView())
                donut
                    .frame(height: 176)
                    .frame(maxWidth: .infinity)
                legend
            }
            .frame(maxHeight: .infinity, alignment: .top)
        }
    }

    private var donut: some View {
        Chart(benefits) { b in
            SectorMark(angle: .value("Amount", b.amount), innerRadius: .ratio(0.7), angularInset: 1.5)
                .foregroundStyle(color(b))
                .cornerRadius(2)
        }
        .chartLegend(.hidden)
        .chartBackground { proxy in
            GeometryReader { geo in
                if let frame = proxy.plotFrame {
                    let r = geo[frame]
                    VStack(spacing: 2) {
                        Text(Fmt.millions(total)).font(Theme.mono(22, .medium)).foregroundStyle(Theme.textPrimary)
                        Text("M ₽ / yr").font(Theme.mono(10.5)).foregroundStyle(Theme.textTertiary)
                    }
                    .position(x: r.midX, y: r.midY)
                }
            }
        }
        .accessibilityLabel("Annual benefits \(Fmt.millions(total)) million roubles")
    }

    private var legend: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Text("Item").frame(maxWidth: .infinity, alignment: .leading)
                Text("M ₽").frame(width: 52, alignment: .trailing)
                Text("Share").frame(width: 50, alignment: .trailing)
            }
            .font(.system(size: 11, weight: .medium))
            .foregroundStyle(Theme.textTertiary)
            .padding(.bottom, 6)
            ForEach(benefits.sorted { $0.amount > $1.amount }) { b in
                Rectangle().fill(Theme.hairline).frame(height: 1)
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        RoundedRectangle(cornerRadius: 2).fill(color(b)).frame(width: 8, height: 8)
                            .alignmentGuide(.firstTextBaseline) { $0[.bottom] - 1 }
                        Text(Fmt.split(b.item).title)
                            .font(.system(size: 12.5))
                            .foregroundStyle(Theme.textPrimary)
                            .lineLimit(2)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    Text(Fmt.millions(b.amount)).font(Theme.mono(12)).foregroundStyle(Theme.textPrimary)
                        .frame(width: 52, alignment: .trailing)
                    Text(String(format: "%.1f %%", total > 0 ? b.amount / total * 100 : 0))
                        .font(Theme.mono(12)).foregroundStyle(Theme.textSecondary)
                        .frame(width: 50, alignment: .trailing)
                }
                .padding(.vertical, 8)
            }
        }
    }
}

// MARK: - Alternatives

private struct AlternativesCard: View {
    let rows: [AltRow]
    let years: Int
    let capex: Double
    let opex: Double

    var body: some View {
        let maxCost = rows.map(\.cost).max() ?? 1
        GlassCard {
            VStack(alignment: .leading, spacing: 12) {
                CardHeader(title: "Annual cost vs alternatives · same district", symbol: "chart.bar.doc.horizontal",
                           trailing: Text("M ₽ / yr").font(Theme.mono(10.5)).foregroundStyle(Theme.textTertiary).eraseToAnyView())
                VStack(spacing: 0) {
                    ForEach(rows) { r in
                        if r.id != rows.first?.id { Rectangle().fill(Theme.hairline).frame(height: 1) }
                        AltRowView(row: r, fraction: r.cost / maxCost, opexFraction: r.ours ? opex / maxCost : nil)
                    }
                }
                Text("Our annual cost = OPEX \(Fmt.millions(opex)) M ₽ + CAPEX \(Fmt.millions(capex)) M ₽ spread over \(years) years.")
                    .font(.system(size: 11.5))
                    .foregroundStyle(Theme.textTertiary)
            }
        }
    }
}

private struct AltRowView: View {
    let row: AltRow
    let fraction: Double
    let opexFraction: Double?

    var body: some View {
        HStack(spacing: 14) {
            HStack(spacing: 6) {
                Text(row.name)
                    .font(.system(size: 12.5, weight: row.ours ? .semibold : .regular))
                    .foregroundStyle(row.ours ? Theme.textPrimary : Theme.textSecondary)
                    .lineLimit(1)
                    .truncationMode(.tail)
            }
            .frame(width: 190, alignment: .leading)
            bar
                .frame(height: 10)
                .frame(minWidth: 120)
            Text(Fmt.millions(row.cost))
                .font(Theme.mono(12, row.ours ? .semibold : .regular))
                .foregroundStyle(row.ours ? Theme.accent : Theme.textPrimary)
                .frame(width: 48, alignment: .trailing)
            Text(row.notes)
                .font(.system(size: 12))
                .foregroundStyle(Theme.textTertiary)
                .lineLimit(1)
                .truncationMode(.tail)
                .frame(width: 320, alignment: .leading)
                .help(row.notes)
        }
        .frame(height: 38)
    }

    private var bar: some View {
        GeometryReader { geo in
            let w = geo.size.width
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 2).fill(Color.white.opacity(0.035))
                if row.ours, let opexFraction {
                    RoundedRectangle(cornerRadius: 2).fill(Theme.accent.opacity(0.4)).frame(width: w * fraction)
                    RoundedRectangle(cornerRadius: 2).fill(Theme.accent).frame(width: w * opexFraction)
                } else {
                    RoundedRectangle(cornerRadius: 2).fill(Color.white.opacity(0.24)).frame(width: w * fraction)
                }
            }
        }
    }
}

// MARK: - Model inputs

private struct InputsCard: View {
    let capex: [EconLine]
    let opex: [EconLine]
    let benefits: [EconLine]
    let footer: String
    let excel: URL

    var body: some View {
        GlassCard(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader(title: "Model inputs", symbol: "slider.horizontal.3", trailing: trailing.eraseToAnyView())
                    .padding(.horizontal, 18)
                    .padding(.vertical, 12)
                Rectangle().fill(Theme.hairline).frame(height: 1)
                HStack(alignment: .top, spacing: 0) {
                    InputTable(title: "Investment · one-time", lines: capex, totalLabel: "Total CAPEX")
                    Rectangle().fill(Theme.hairline).frame(width: 1)
                    InputTable(title: "Operating cost · per year", lines: opex, totalLabel: "Total OPEX / yr")
                    Rectangle().fill(Theme.hairline).frame(width: 1)
                    InputTable(title: "Benefits · per year", lines: benefits, totalLabel: "Total benefits / yr")
                }
                .fixedSize(horizontal: false, vertical: true)
                Rectangle().fill(Theme.hairline).frame(height: 1)
                Text(footer)
                    .font(.system(size: 11.5))
                    .foregroundStyle(Theme.textTertiary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .padding(.horizontal, 18)
                    .padding(.vertical, 11)
            }
        }
    }

    private var trailing: some View {
        HStack(spacing: 10) {
            Text("economics/case1_fire.yaml").font(Theme.mono(10.5)).foregroundStyle(Theme.textTertiary)
                .lineLimit(1)
            Button("Open Excel model", systemImage: "tablecells") { NSWorkspace.shared.open(excel) }
                .buttonStyle(.quiet)
                .help("Open 06_Economics.xlsx - the same model with live formulas")
        }
        .fixedSize()
    }
}

private struct InputTable: View {
    let title: String
    let lines: [EconLine]
    let totalLabel: String

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Eyebrow(text: title).lineLimit(1)
                Spacer(minLength: 8)
                Text("₽").font(Theme.mono(10.5)).foregroundStyle(Theme.textTertiary)
            }
            .padding(.bottom, 8)
            ForEach(lines) { l in
                Rectangle().fill(Theme.hairline).frame(height: 1)
                row(l)
            }
            Spacer(minLength: 0)
            Rectangle().fill(Theme.hairlineStrong).frame(height: 1)
            HStack(alignment: .firstTextBaseline) {
                Text(totalLabel).font(.system(size: 12, weight: .semibold)).foregroundStyle(Theme.textSecondary)
                Spacer(minLength: 8)
                Text(Fmt.rub(lines.reduce(0) { $0 + $1.amount }))
                    .font(Theme.mono(12.5, .semibold)).foregroundStyle(Theme.textPrimary)
            }
            .padding(.top, 9)
        }
        .padding(.horizontal, 18)
        .padding(.top, 14)
        .padding(.bottom, 14)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private func row(_ l: EconLine) -> some View {
        let parts = Fmt.split(l.item)
        return HStack(alignment: .firstTextBaseline, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(parts.title)
                    .font(.system(size: 12.5))
                    .foregroundStyle(Theme.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                if let d = parts.detail ?? l.comment {
                    Text(d)
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.textTertiary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Text(Fmt.rub(l.amount))
                .font(Theme.mono(12))
                .foregroundStyle(Theme.textPrimary)
                .fixedSize()
        }
        .padding(.vertical, 8)
    }
}
