import QuickLookThumbnailing
import SwiftUI

struct DocumentsView: View {
    @Environment(AppModel.self) private var model
    @State private var regenerating = false

    var body: some View {
        let groups = DocGroup.grouped(model.documents.files)
        Page(section: .documents, trailing: actions.eraseToAnyView()) {
            if groups.isEmpty {
                empty
            } else {
                VStack(alignment: .leading, spacing: 24) {
                    ForEach(groups, id: \.group) { g in
                        DocSection(group: g.group, files: g.files)
                    }
                }
            }
        }
    }

    private var actions: some View {
        HStack(spacing: 8) {
            Button("Open folder", systemImage: "folder") { NSWorkspace.shared.open(model.documents.deliverablesFolder) }
                .help("Show the deliverables folder in Finder")
            Button(action: regenerate) {
                HStack(spacing: 6) {
                    if regenerating {
                        ProgressView().controlSize(.mini)
                    } else {
                        Image(systemName: "arrow.triangle.2.circlepath")
                    }
                    Text(regenerating ? "Regenerating…" : "Regenerate documents")
                }
            }
            .disabled(regenerating)
            .help("Rebuild the Case 1 documents with tools/make_docs.py")
        }
        .buttonStyle(.secondary)
        .fixedSize()
    }

    private var empty: some View {
        GlassCard {
            ContentUnavailableView {
                Label("No deliverables yet", systemImage: "doc.richtext")
            } description: {
                Text("Generate the Case 1 documents to see them here.")
            } actions: {
                Button("Regenerate documents", systemImage: "arrow.triangle.2.circlepath", action: regenerate)
                    .buttonStyle(.primary)
                    .fixedSize()
                    .disabled(regenerating)
            }
            .frame(maxWidth: .infinity, minHeight: 260)
        }
    }

    private func regenerate() {
        let root = model.settings.toolkitRoot
        regenerating = true
        let job = model.console.run(title: "Regenerate Case 1 documents", executable: model.settings.pythonURL,
                                    arguments: [root.appending(path: "tools/make_docs.py").path(percentEncoded: false), "case1"],
                                    workingDirectory: root)
        let documents = model.documents
        job.onExit = { _ in
            Task { @MainActor in
                documents.reload()
                regenerating = false
            }
        }
    }
}

// MARK: - Grouping

private enum DocGroup: String, CaseIterable {
    case presentation = "Presentation"
    case documents = "Documents"
    case spreadsheets = "Spreadsheets"
    case media = "Images & video"

    static func of(_ f: DeliverableFile) -> DocGroup {
        switch f.kind {
        case "PPTX": .presentation
        case "XLSX": .spreadsheets
        case "PNG", "MP4": .media
        default: f.url.lastPathComponent.localizedCaseInsensitiveContains("presentation") ? .presentation : .documents
        }
    }

    /// Groups in a fixed order; inside a group by kind, then by file name (keeps the 01_…08_ numbering).
    static func grouped(_ files: [DeliverableFile]) -> [(group: DocGroup, files: [DeliverableFile])] {
        let kinds = ["PPTX", "PDF", "HTML", "XLSX", "MD", "PNG", "MP4"]
        let byGroup = Dictionary(grouping: files, by: of)
        return allCases.compactMap { g in
            guard let list = byGroup[g], !list.isEmpty else { return nil }
            let sorted = list.sorted {
                let a = kinds.firstIndex(of: $0.kind) ?? 99, b = kinds.firstIndex(of: $1.kind) ?? 99
                return a == b ? $0.url.lastPathComponent < $1.url.lastPathComponent : a < b
            }
            return (g, sorted)
        }
    }
}

private struct DocSection: View {
    let group: DocGroup
    let files: [DeliverableFile]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Eyebrow(text: group.rawValue)
                Text("\(files.count)").font(Theme.mono(10.5)).foregroundStyle(Theme.textTertiary)
                Rectangle().fill(Theme.hairline).frame(height: 1)
            }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 216), spacing: Theme.spacing)], alignment: .leading, spacing: Theme.spacing) {
                ForEach(files) { DocumentTile(file: $0) }
            }
        }
    }
}

// MARK: - Tile

private struct DocumentTile: View {
    let file: DeliverableFile
    @State private var thumbnail: NSImage?
    @State private var hovering = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        Button { NSWorkspace.shared.open(file.url) } label: {
            VStack(alignment: .leading, spacing: 0) {
                preview
                    .padding(8)
                info
                    .padding(.horizontal, 12)
                    .padding(.top, 2)
                    .padding(.bottom, 12)
            }
            .background(Theme.panel, in: .rect(cornerRadius: Theme.radius))
            .overlay(RoundedRectangle(cornerRadius: Theme.radius).strokeBorder(hovering ? Theme.hairlineStrong : Theme.hairline))
            .shadow(color: .black.opacity(hovering ? 0.35 : 0), radius: 12, y: 6)
            .offset(y: hovering && !reduceMotion ? -2 : 0)
            .contentShape(.rect(cornerRadius: Theme.radius))
        }
        .buttonStyle(.plain)
        .onHover { h in withAnimation(.snappy(duration: 0.2)) { hovering = h } }
        .help(file.url.lastPathComponent)
        .accessibilityLabel("\(title), \(file.kind), \(sizeText)")
        .contextMenu {
            Button("Open", systemImage: "arrow.up.forward.app") { NSWorkspace.shared.open(file.url) }
            Button("Show in Finder", systemImage: "folder") { NSWorkspace.shared.activateFileViewerSelecting([file.url]) }
        }
        .task(id: file) {
            let req = QLThumbnailGenerator.Request(fileAt: file.url, size: CGSize(width: 400, height: 300), scale: 2,
                                                   representationTypes: .thumbnail)
            if let rep = try? await QLThumbnailGenerator.shared.generateBestRepresentation(for: req) {
                thumbnail = rep.nsImage
            }
        }
    }

    private var preview: some View {
        ZStack {
            Theme.well
            if let thumbnail {
                Image(nsImage: thumbnail)
                    .resizable()
                    .interpolation(.high)
                    .aspectRatio(contentMode: .fit)
                    .clipShape(.rect(cornerRadius: 2))
                    .shadow(color: .black.opacity(0.45), radius: 3, y: 1)
                    .padding(12)
                    .transition(.opacity)
            } else {
                Image(systemName: file.symbol)
                    .font(.system(size: 26, weight: .light))
                    .foregroundStyle(Theme.textTertiary)
            }
        }
        .frame(height: 140)
        .frame(maxWidth: .infinity)
        .clipShape(.rect(cornerRadius: 9))
        .overlay(RoundedRectangle(cornerRadius: 9).strokeBorder(Theme.hairline))
        .animation(.smooth(duration: 0.25), value: thumbnail != nil)
    }

    private var info: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(title)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                Spacer(minLength: 4)
                KindTag(kind: file.kind)
            }
            Text("\(sizeText) · \(Self.dateFormat.string(from: file.modified))")
                .font(Theme.mono(10.5))
                .foregroundStyle(Theme.textTertiary)
                .lineLimit(1)
        }
    }

    private static let dateFormat: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_GB")
        f.dateFormat = "d MMM HH:mm"
        return f
    }()

    /// "ALL DOCUMENTS" -> "All Documents"; other titles unchanged.
    private var title: String {
        file.title == file.title.uppercased() ? file.title.capitalized : file.title
    }

    private var sizeText: String {
        let b = Double(file.size)
        if b < 1024 { return "\(file.size) B" }
        if b < 1024 * 1024 { return String(format: "%.0f KB", b / 1024) }
        return String(format: "%.1f MB", b / 1024 / 1024)
    }
}

private struct KindTag: View {
    let kind: String

    var body: some View {
        Text(kind)
            .font(.system(size: 10, weight: .medium))
            .foregroundStyle(Theme.textSecondary)
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .overlay(RoundedRectangle(cornerRadius: 4).strokeBorder(Theme.hairlineStrong))
            .fixedSize()
    }
}
