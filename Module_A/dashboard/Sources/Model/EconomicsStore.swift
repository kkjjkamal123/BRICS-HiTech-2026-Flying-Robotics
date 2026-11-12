import Foundation
import Observation

struct EconLine: Identifiable, Hashable, Sendable {
    let id: String
    let item: String
    let amount: Double
    let comment: String?
}

struct EconAlternative: Identifiable, Hashable, Sendable {
    var id: String { name }
    let name: String
    let annualCost: Double
    let notes: String
}

struct EconKPI: Identifiable, Hashable, Sendable {
    var id: String { label }
    let label: String
    let value: String
    let note: String
}

struct CashFlowYear: Identifiable, Hashable, Sendable {
    var id: Int { year }
    let year: Int
    let net: Double
    let cumulative: Double
}

/// Case 1 economics: inputs from economics/case1_fire.yaml, results from economics/out/case1_fire.{md,csv}
/// (both produced by economics/econ.py, the same model the Excel sheet uses).
@MainActor
@Observable
final class EconomicsStore {
    private(set) var title = ""
    private(set) var customer = ""
    private(set) var currency = "RUB"
    private(set) var years = 5
    private(set) var discountRate = 0.0
    private(set) var capex: [EconLine] = []
    private(set) var opex: [EconLine] = []
    private(set) var benefits: [EconLine] = []
    private(set) var alternatives: [EconAlternative] = []
    private(set) var kpis: [EconKPI] = []
    private(set) var cashFlow: [CashFlowYear] = []
    private(set) var verdict = ""
    private(set) var loaded = false
    private(set) var attempted = false
    let root: URL

    init(root: URL) { self.root = root }

    var totalCapex: Double { capex.reduce(0) { $0 + $1.amount } }
    var totalOpex: Double { opex.reduce(0) { $0 + $1.amount } }
    var totalBenefits: Double { benefits.reduce(0) { $0 + $1.amount } }

    func reload() {
        let root = root
        Task.detached(priority: .utility) {
            let yaml = EconomicsStore.loadYAML(root: root)
            let md = (try? String(contentsOf: root.appending(path: "economics/out/case1_fire.md"), encoding: .utf8)) ?? ""
            let csv = (try? String(contentsOf: root.appending(path: "economics/out/case1_fire.csv"), encoding: .utf8)) ?? ""
            await MainActor.run { self.apply(yaml: yaml, md: md, csv: csv) }
        }
    }

    /// PyYAML is in the toolkit .venv - one subprocess turns the YAML into JSON.
    nonisolated static func loadYAML(root: URL) -> [String: Any] {
        let p = Process()
        p.executableURL = root.appending(path: ".venv/bin/python")
        p.arguments = ["-c", "import yaml,json,sys; print(json.dumps(yaml.safe_load(open(sys.argv[1]))))",
                       root.appending(path: "economics/case1_fire.yaml").path(percentEncoded: false)]
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = FileHandle.nullDevice
        do { try p.run() } catch { return [:] }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    private func lines(_ any: Any?, prefix: String) -> [EconLine] {
        (any as? [[String: Any]] ?? []).enumerated().map { i, d in
            EconLine(id: "\(prefix)\(i)", item: d["item"] as? String ?? "?",
                     amount: (d["amount"] as? NSNumber)?.doubleValue ?? 0, comment: d["comment"] as? String)
        }
    }

    private func apply(yaml: [String: Any], md: String, csv: String) {
        title = yaml["title"] as? String ?? "Case 1 economics"
        customer = yaml["customer"] as? String ?? ""
        currency = yaml["currency"] as? String ?? "RUB"
        years = (yaml["years"] as? NSNumber)?.intValue ?? 5
        discountRate = (yaml["discount_rate"] as? NSNumber)?.doubleValue ?? 0
        capex = lines(yaml["capex"], prefix: "c")
        opex = lines(yaml["opex"], prefix: "o")
        benefits = lines(yaml["benefits"], prefix: "b")
        alternatives = (yaml["alternatives"] as? [[String: Any]] ?? []).map {
            EconAlternative(name: $0["name"] as? String ?? "?", annualCost: ($0["annual_cost"] as? NSNumber)?.doubleValue ?? 0,
                            notes: $0["notes"] as? String ?? "")
        }
        // KPI table rows: | Label | **value** | note |
        var k: [EconKPI] = []
        for raw in md.split(whereSeparator: \.isNewline) {
            let cells = raw.split(separator: "|").map { $0.trimmingCharacters(in: .whitespaces) }
            guard cells.count == 3 else { continue }
            let label = cells[0]
            let wanted = ["Payback period (simple)", "Discounted payback", "ROI (5 yr)", "IRR", "Break-even benefits"]
            if wanted.contains(label) || label.hasPrefix("NPV @") {
                k.append(EconKPI(label: label, value: cells[1].replacingOccurrences(of: "**", with: ""), note: cells[2]))
            }
        }
        kpis = k
        if let v = md.split(whereSeparator: \.isNewline).first(where: { $0.contains("ECONOMICALLY") }) {
            verdict = v.replacingOccurrences(of: "**", with: "").replacingOccurrences(of: "The project is ", with: "")
        }
        var cum = 0.0
        cashFlow = csv.split(whereSeparator: \.isNewline).dropFirst().compactMap { row in
            let c = row.split(separator: ",")
            guard c.count == 2, let y = Int(c[0]), let n = Double(c[1]) else { return nil }
            cum += n
            return CashFlowYear(year: y, net: n, cumulative: cum)
        }
        loaded = !capex.isEmpty
        attempted = true
    }
}
