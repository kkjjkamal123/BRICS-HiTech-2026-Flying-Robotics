import Foundation
import Observation

struct ModelInfo: Identifiable, Hashable, Sendable {
    var id: String { name }
    let name: String
    let folder: URL
    let formats: [String]
    let map50: Double?
    let map5095: Double?
}

@MainActor
@Observable
final class AIModelStore {
    private(set) var models: [ModelInfo] = []
    private(set) var weights: [String] = []
    private(set) var datasets: [String] = []
    let root: URL

    init(root: URL) { self.root = root }

    var fireModel: ModelInfo? { models.first { $0.name == "fire" } }

    func reload() {
        let root = root
        Task.detached(priority: .utility) {
            let fm = FileManager.default
            let modelsDir = root.appending(path: "models")
            var ms: [ModelInfo] = []
            for d in (try? fm.contentsOfDirectory(at: modelsDir, includingPropertiesForKeys: nil)) ?? [] where d.hasDirectoryPath {
                let files = (try? fm.contentsOfDirectory(atPath: d.path(percentEncoded: false))) ?? []
                let formats = ["pt", "onnx", "rknn"].filter { ext in files.contains { $0.hasSuffix("." + ext) || $0.hasSuffix("_\(ext)_model") } }
                let (m50, m95) = AIModelStore.readMetrics(d.appending(path: "metrics.md"))
                ms.append(ModelInfo(name: d.lastPathComponent, folder: d, formats: formats, map50: m50, map5095: m95))
            }
            let weights = ((try? fm.contentsOfDirectory(atPath: root.appending(path: "weights").path(percentEncoded: false))) ?? [])
                .filter { $0.hasSuffix(".pt") || $0.hasSuffix(".onnx") }.sorted()
            let datasets = ((try? fm.contentsOfDirectory(atPath: root.appending(path: "datasets").path(percentEncoded: false))) ?? [])
                .filter { !$0.hasPrefix(".") }.sorted()
            let found = ms
            await MainActor.run {
                self.models = found.sorted { ($0.name == "fire" ? 0 : 1, $0.name) < ($1.name == "fire" ? 0 : 1, $1.name) }
                self.weights = weights
                self.datasets = datasets
            }
        }
    }

    /// metrics.md written by train/train.py:
    /// | class | precision | recall | mAP50 | mAP50-95 |   then the row  | **all** | ... |
    nonisolated static func readMetrics(_ url: URL) -> (Double?, Double?) {
        guard let text = try? String(contentsOf: url, encoding: .utf8) else { return (nil, nil) }
        func cells(_ line: Substring) -> [String] {
            line.split(separator: "|").map { $0.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: "**", with: "") }
        }
        let rows = text.split(separator: "\n").filter { $0.hasPrefix("|") }
        guard let header = rows.first.map(cells),
              let i50 = header.firstIndex(of: "mAP50"),
              let all = rows.map(cells).first(where: { $0.first == "all" }) else { return (nil, nil) }
        let i95 = header.firstIndex(of: "mAP50-95")
        return (i50 < all.count ? Double(all[i50]) : nil, i95.flatMap { $0 < all.count ? Double(all[$0]) : nil })
    }

    nonisolated static func readMAP50(root: URL?) -> Double? {
        guard let root else { return nil }
        return readMetrics(root.appending(path: "models/fire/metrics.md")).0
    }
}
