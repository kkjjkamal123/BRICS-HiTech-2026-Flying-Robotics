import Foundation
import Observation

struct DeliverableFile: Identifiable, Hashable, Sendable {
    var id: URL { url }
    let url: URL
    let title: String
    let kind: String
    let symbol: String
    let size: Int64
    let modified: Date
}

@MainActor
@Observable
final class DocumentsStore {
    private(set) var files: [DeliverableFile] = []
    let root: URL

    init(root: URL) { self.root = root }

    var deliverablesFolder: URL { root.appending(path: "deliverables/case1_forest_fire") }

    func reload() {
        let root = root
        Task.detached(priority: .utility) {
            let list = DocumentsStore.scan(root: root)
            await MainActor.run { self.files = list }
        }
    }

    nonisolated static func scan(root: URL) -> [DeliverableFile] {
        let fm = FileManager.default
        let folders = [root.appending(path: "deliverables/case1_forest_fire"), root.appending(path: "runs/sim_videos")]
        let order = ["pptx", "pdf", "xlsx", "md", "html", "png", "mp4"]
        var out: [DeliverableFile] = []
        for folder in folders {
            for f in (try? fm.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.fileSizeKey, .contentModificationDateKey])) ?? [] {
                let ext = f.pathExtension.lowercased()
                guard order.contains(ext) else { continue }
                let v = try? f.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey])
                out.append(DeliverableFile(url: f, title: pretty(f.deletingPathExtension().lastPathComponent), kind: ext.uppercased(),
                                           symbol: symbol(ext), size: Int64(v?.fileSize ?? 0), modified: v?.contentModificationDate ?? .distantPast))
            }
        }
        return out.sorted {
            let a = order.firstIndex(of: $0.kind.lowercased()) ?? 99, b = order.firstIndex(of: $1.kind.lowercased()) ?? 99
            return a == b ? $0.title < $1.title : a < b
        }
    }

    nonisolated static func pretty(_ name: String) -> String {
        var s = name.replacingOccurrences(of: "_", with: " ")
        if let r = s.range(of: #"^\d\d "#, options: .regularExpression) { s.removeSubrange(r) }
        return s
    }

    nonisolated static func symbol(_ ext: String) -> String {
        switch ext {
        case "pptx": "play.rectangle.on.rectangle.fill"
        case "pdf": "doc.richtext.fill"
        case "xlsx": "tablecells.fill"
        case "md": "doc.text.fill"
        case "html": "globe"
        case "png": "photo.fill"
        case "mp4": "film.fill"
        default: "doc.fill"
        }
    }
}
