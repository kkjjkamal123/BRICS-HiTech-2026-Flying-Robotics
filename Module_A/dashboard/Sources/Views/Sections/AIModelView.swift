import SwiftUI
import UniformTypeIdentifiers

// AI Model: fire-model readouts, the training pipeline, trained models and the thermal-camera probe.

struct AIModelView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        Page(section: .aiModel) {
            Readouts()
            PipelinePanel()
            HStack(alignment: .top, spacing: Theme.spacing) {
                ModelsTable()
                ThermalPanel()
                    .frame(width: 320)
            }
            ConsolePanel(height: 220)
        }
    }
}

private extension AIModelStore {
    /// Datasets the operator collected (excludes the synthetic pipeline self-tests).
    var realDatasets: [String] { datasets.filter { !$0.hasPrefix("_selftest") } }
}

// MARK: - Readouts

private struct Readouts: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let ai = model.aiModel
        let map = ai.fireModel?.map50
        let hasRKNN = ai.fireModel?.formats.contains("rknn") ?? false
        HStack(spacing: Theme.spacing) {
            StatTile(title: "Fire model mAP@0.5", value: map.map { String(format: "%.3f", $0) } ?? "—",
                     symbol: "flame", tint: map.map { $0 >= 0.85 ? Theme.ok : Theme.critical } ?? Theme.textPrimary,
                     footnote: map == nil ? "C2 target ≥ 0.85 · not trained" : "C2 target ≥ 0.85",
                     emphasis: map != nil)
            StatTile(title: "NPU format", value: hasRKNN ? "RKNN" : "—", symbol: "cpu",
                     footnote: hasRKNN ? "RK3588S · 6 TOPS" : "RK3588S · export pending")
            StatTile(title: "Datasets", value: "\(ai.realDatasets.count)", symbol: "photo.stack",
                     footnote: ai.realDatasets.isEmpty ? "Self-test sets only" : ai.realDatasets.joined(separator: ", "))
            StatTile(title: "Base weights", value: "\(ai.weights.count)", symbol: "shippingbox",
                     footnote: ai.weights.first.map { ai.weights.count > 1 ? "\($0) + \(ai.weights.count - 1) more" : $0 } ?? "weights/ is empty")
        }
        .fixedSize(horizontal: false, vertical: true)
    }
}

// MARK: - Pipeline

private enum StepState { case done, active, pending, manual

    var color: Color {
        switch self {
        case .done: Theme.ok
        case .active: Theme.caution
        case .pending, .manual: Theme.textTertiary
        }
    }
}

private struct PipelineStep: Identifiable {
    let id: String
    let symbol: String
    let detail: String
    let status: String
    let state: StepState
}

private struct PipelinePanel: View {
    @Environment(AppModel.self) private var model

    private var steps: [PipelineStep] {
        let ai = model.aiModel
        let collected = !ai.realDatasets.isEmpty
        let fire = ai.fireModel
        let trained = fire?.formats.contains("pt") ?? false
        let map = fire?.map50
        let rknn = fire?.formats.contains("rknn") ?? false
        let trainStatus: String = map.map { String(format: "mAP50 %.3f", $0) } ?? (trained ? "weights saved" : "not trained")
        let trainState: StepState = map.map { $0 >= 0.85 ? .done : .active } ?? (trained ? .active : .pending)
        return [
            PipelineStep(id: "Collect", symbol: "camera.metering.spot",
                         detail: "TR256i frames at 1–2 m: fires and hard negatives",
                         status: collected ? (ai.realDatasets.count == 1 ? "1 dataset" : "\(ai.realDatasets.count) datasets") : "no field data yet", state: collected ? .done : .pending),
            PipelineStep(id: "Auto-label", symbol: "wand.and.rays",
                         detail: "autolabel.py --thermal: hot spot → box",
                         status: "operator step", state: .manual),
            PipelineStep(id: "Review", symbol: "checkmark.rectangle.stack",
                         detail: "label_tool.py: fix or delete boxes",
                         status: "operator step", state: .manual),
            PipelineStep(id: "Train", symbol: "point.3.connected.trianglepath.dotted",
                         detail: "train.py → mAP report in metrics.md",
                         status: trainStatus, state: trainState),
            PipelineStep(id: "NPU export", symbol: "cpu",
                         detail: "convert_rknn.sh → best.rknn ≥ 10 FPS",
                         status: rknn ? "best.rknn ready" : "pending", state: rknn ? .done : .pending),
        ]
    }

    var body: some View {
        let steps = steps
        GlassCard(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader(title: "Fire-model pipeline", symbol: "arrow.triangle.branch")
                    .padding(.horizontal, 18)
                    .padding(.top, 14)
                    .padding(.bottom, 16)
                HStack(alignment: .top, spacing: 0) {
                    ForEach(Array(steps.enumerated()), id: \.element.id) { i, step in
                        StepView(index: i + 1, step: step, last: i == steps.count - 1,
                                 nextDone: i + 1 < steps.count && steps[i + 1].state == .done && step.state == .done)
                    }
                }
                .padding(.horizontal, 18)
                .padding(.bottom, 16)
                Rectangle().fill(Theme.hairline).frame(height: 1)
                TrainRow()
                    .padding(.horizontal, 18)
                    .padding(.vertical, 14)
            }
        }
    }
}

private struct StepView: View {
    let index: Int
    let step: PipelineStep
    let last: Bool
    let nextDone: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                node
                if !last {
                    Rectangle()
                        .fill(nextDone ? Theme.ok.opacity(0.5) : Theme.hairlineStrong)
                        .frame(height: 1)
                        .padding(.trailing, 10)
                }
            }
            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(String(format: "%02d", index)).font(Theme.mono(10.5)).foregroundStyle(Theme.textTertiary)
                    Text(step.id).font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.textPrimary).lineLimit(1)
                }
                Text(step.detail)
                    .font(.system(size: 11.5))
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(2, reservesSpace: true)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.trailing, 14)
            HStack(spacing: 6) {
                Circle().fill(step.state.color).frame(width: 5, height: 5)
                Text(step.status)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(step.state == .manual ? Theme.textTertiary : step.state == .pending ? Theme.textSecondary : step.state.color)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var node: some View {
        ZStack {
            Circle().fill(Theme.panelRaised)
            Circle().strokeBorder(step.state == .done ? Theme.ok.opacity(0.55) : Theme.hairlineStrong, lineWidth: 1)
            Image(systemName: step.symbol)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(step.state == .done ? Theme.textPrimary : Theme.textSecondary)
        }
        .frame(width: 30, height: 30)
    }
}

private struct TrainRow: View {
    @Environment(AppModel.self) private var model
    @State private var datasetPath = ""
    @FocusState private var focused: Bool

    var body: some View {
        HStack(spacing: 8) {
            Text("Dataset")
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(Theme.textTertiary)
                .fixedSize()
                .padding(.trailing, 4)
            HStack(spacing: 6) {
                Image(systemName: "folder").font(.system(size: 11)).foregroundStyle(Theme.textTertiary)
                TextField("Folder or zip, e.g. ~/Downloads/fire_thermal.zip", text: $datasetPath)
                    .textFieldStyle(.plain)
                    .font(Theme.mono(12))
                    .focused($focused)
            }
            .padding(.horizontal, 9)
            .frame(height: 28)
            .background(Theme.well, in: .rect(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(focused ? Theme.hairlineStrong : Theme.hairline))
            .animation(.easeOut(duration: 0.12), value: focused)
            datasetMenu
            Button("Train fire model", systemImage: "play.fill") { train() }
                .buttonStyle(.primary)
                .disabled(datasetPath.trimmingCharacters(in: .whitespaces).isEmpty)
                .fixedSize()
        }
    }

    private var datasetMenu: some View {
        Menu {
            let sets = model.aiModel.datasets
            if !sets.isEmpty {
                Section("datasets/") {
                    ForEach(sets, id: \.self) { name in
                        Button(name) {
                            datasetPath = model.settings.toolkitRoot.appending(path: "datasets/\(name)").path(percentEncoded: false)
                        }
                    }
                }
            }
            Button("Choose folder or zip…") { choose() }
        } label: {
            HStack(spacing: 6) {
                Text("Choose")
                Image(systemName: "chevron.down").font(.system(size: 9, weight: .semibold)).foregroundStyle(Theme.textSecondary)
            }
        }
        .menuStyle(.button)
        .menuIndicator(.hidden)
        .buttonStyle(.secondary)
        .fixedSize()
        .help("Pick a dataset from datasets/ or choose a folder or zip")
    }

    private func choose() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = true
        panel.allowedContentTypes = [.zip, .folder]
        if panel.runModal() == .OK, let url = panel.url { datasetPath = url.path(percentEncoded: false) }
    }

    private func train() {
        let root = model.settings.toolkitRoot
        let path = (datasetPath.trimmingCharacters(in: .whitespaces) as NSString).expandingTildeInPath
        model.console.run(title: "Train fire model", executable: model.settings.pythonURL,
                          arguments: [root.appending(path: "train/train.py").path(percentEncoded: false), "--data", path, "--name", "fire"],
                          workingDirectory: root)
    }
}

// MARK: - Models table

private enum ModelColumns {
    static let formats: CGFloat = 132
    static let map: CGFloat = 60
    static let map95: CGFloat = 70
    static let action: CGFloat = 26
    static let gap: CGFloat = 12
}

private struct ModelsTable: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let models = model.aiModel.models
        GlassCard(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader(title: "Trained models", symbol: "square.stack.3d.up",
                           trailing: Button("Reload", systemImage: "arrow.clockwise") { model.aiModel.reload() }
                    .buttonStyle(.quiet).fixedSize().eraseToAnyView())
                    .padding(.horizontal, 18)
                    .padding(.top, 12)
                    .padding(.bottom, 8)
                if models.isEmpty {
                    Rectangle().fill(Theme.hairline).frame(height: 1)
                    Text("No trained models in models/. Train the fire model above.")
                        .font(.system(size: 12.5))
                        .foregroundStyle(Theme.textTertiary)
                        .frame(maxWidth: .infinity, minHeight: 80)
                } else {
                    let real = models.filter { !$0.name.hasPrefix("_selftest") }
                    let tests = models.filter { $0.name.hasPrefix("_selftest") }
                    header
                    if real.isEmpty {
                        Rectangle().fill(Theme.hairline).frame(height: 1)
                        Text("No competition model yet. Train the fire model above.")
                            .font(.system(size: 12.5))
                            .foregroundStyle(Theme.textSecondary)
                            .padding(.horizontal, 18)
                            .frame(maxWidth: .infinity, minHeight: 40, alignment: .leading)
                    }
                    ForEach(real) { m in
                        Rectangle().fill(Theme.hairline).frame(height: 1)
                        ModelRow(model: m)
                    }
                    if !tests.isEmpty {
                        Rectangle().fill(Theme.hairline).frame(height: 1)
                        groupLabel("Pipeline self-tests · synthetic shapes, not competition models")
                        ForEach(tests) { m in
                            Rectangle().fill(Theme.hairline).frame(height: 1)
                            ModelRow(model: m)
                        }
                    }
                }
            }
            .padding(.bottom, 4)
        }
    }

    private func groupLabel(_ s: String) -> some View {
        Text(s)
            .font(.system(size: 11))
            .foregroundStyle(Theme.textTertiary)
            .lineLimit(1)
            .minimumScaleFactor(0.85)
            .padding(.horizontal, 18)
            .frame(maxWidth: .infinity, minHeight: 28, alignment: .leading)
            .background(Theme.well.opacity(0.6))
    }

    private var header: some View {
        HStack(spacing: ModelColumns.gap) {
            col("Model").frame(maxWidth: .infinity, alignment: .leading)
            col("Formats").frame(width: ModelColumns.formats, alignment: .leading)
            col("mAP50").frame(width: ModelColumns.map, alignment: .trailing)
            col("mAP50-95").frame(width: ModelColumns.map95, alignment: .trailing)
            Color.clear.frame(width: ModelColumns.action, height: 1)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 7)
        .background(Theme.well.opacity(0.6))
        .overlay(alignment: .top) { Rectangle().fill(Theme.hairline).frame(height: 1) }
    }

    private func col(_ s: String) -> some View {
        Text(s).font(.system(size: 11, weight: .medium)).foregroundStyle(Theme.textTertiary).lineLimit(1)
    }
}

private struct ModelRow: View {
    let model: ModelInfo
    @State private var hover = false

    private var selfTest: Bool { model.name.hasPrefix("_selftest") }
    private var isFire: Bool { model.name == "fire" }

    var body: some View {
        HStack(spacing: ModelColumns.gap) {
            HStack(spacing: 9) {
                Image(systemName: isFire ? "flame.fill" : "cube")
                    .font(.system(size: 11))
                    .foregroundStyle(isFire ? Theme.accent : Theme.textTertiary)
                    .frame(width: 14)
                Text(model.name)
                    .font(Theme.mono(12.5, isFire ? .semibold : .regular))
                    .foregroundStyle(selfTest ? Theme.textSecondary : Theme.textPrimary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            HStack(spacing: 4) {
                ForEach(model.formats, id: \.self) { FormatTag(text: $0, strong: $0 == "rknn" && !selfTest) }
            }
            .frame(width: ModelColumns.formats, alignment: .leading)
            metric(model.map50, target: true).frame(width: ModelColumns.map, alignment: .trailing)
            metric(model.map5095, target: false).frame(width: ModelColumns.map95, alignment: .trailing)
            Button { NSWorkspace.shared.open(model.folder) } label: {
                Image(systemName: "folder").font(.system(size: 11.5))
            }
            .buttonStyle(.quiet)
            .frame(width: ModelColumns.action)
            .help("Show \(model.name) in Finder")
        }
        .padding(.horizontal, 18)
        .frame(height: selfTest ? 34 : 40)
        .background(Color.white.opacity(hover ? 0.025 : 0))
        .opacity(selfTest ? 0.7 : 1)
        .onHover { hover = $0 }
        .animation(.easeOut(duration: 0.12), value: hover)
    }

    @ViewBuilder private func metric(_ v: Double?, target: Bool) -> some View {
        if let v {
            Text(String(format: "%.3f", v))
                .font(Theme.mono(12, .medium))
                .foregroundStyle(target && isFire ? (v >= 0.85 ? Theme.ok : Theme.critical) : Theme.textPrimary)
        } else {
            Text("—").font(Theme.mono(12)).foregroundStyle(Theme.textTertiary)
        }
    }
}

private struct FormatTag: View {
    let text: String
    var strong = false

    var body: some View {
        Text(text)
            .font(.system(size: 10, weight: .medium))
            .foregroundStyle(strong ? Theme.textPrimary : Theme.textSecondary)
            .padding(.horizontal, 5)
            .frame(height: 18)
            .background(Theme.well, in: .rect(cornerRadius: 4))
            .overlay(RoundedRectangle(cornerRadius: 4).strokeBorder(strong ? Theme.hairlineStrong : Theme.hairline))
            .fixedSize()
    }
}

// MARK: - Thermal camera

private struct ThermalPanel: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: 14) {
                CardHeader(title: "Thermal camera · TR256i", symbol: "thermometer.medium")
                Text("Connect the TR256i to this Mac, or probe it on the drone. Point it at a hand: the max temperature must react.")
                    .font(.system(size: 12.5))
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                VStack(spacing: 0) {
                    kv("Reference", "hand ≈ 34 °C")
                    Rectangle().fill(Theme.hairline).frame(height: 1)
                    kv("Fire hot-spot", "> 60 °C")
                    Rectangle().fill(Theme.hairline).frame(height: 1)
                    kv("Script", "thermal_probe.py")
                }
                .background(Theme.well, in: .rect(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Theme.hairline))
                VStack(spacing: 8) {
                    Button { probeLocal() } label: {
                        Label("Probe on this Mac", systemImage: "laptopcomputer").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.secondary)
                    Button { probeDrone() } label: {
                        Label("Probe on the drone", systemImage: "antenna.radiowaves.left.and.right").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.secondary)
                }
            }
        }
    }

    private func kv(_ k: String, _ v: String) -> some View {
        HStack {
            Text(k).font(.system(size: 12)).foregroundStyle(Theme.textSecondary)
            Spacer(minLength: 8)
            Text(v).font(Theme.mono(12)).foregroundStyle(Theme.textPrimary).lineLimit(1)
        }
        .padding(.horizontal, 10)
        .frame(height: 30)
    }

    private func probeLocal() {
        let root = model.settings.toolkitRoot
        model.console.run(title: "Thermal probe (Mac)", executable: model.settings.pythonURL,
                          arguments: [root.appending(path: "tools/thermal_probe.py").path(percentEncoded: false)], workingDirectory: root)
    }

    private func probeDrone() {
        DroneLink(settings: model.settings, console: model.console)
            .run("Thermal probe (drone)", remote: "cd ~ && python3 -u thermal_probe.py")
    }
}
