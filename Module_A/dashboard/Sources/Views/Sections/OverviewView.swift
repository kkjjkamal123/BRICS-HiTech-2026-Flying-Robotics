import SwiftUI

struct OverviewView: View {
    var body: some View {
        Page(section: .overview) {
            HStack(alignment: .top, spacing: Theme.spacing) {
                AircraftPanel()
                    .frame(maxWidth: .infinity)
                VStack(spacing: Theme.spacing) {
                    SystemStatusPanel()
                    NextActionsPanel()
                        .frame(maxHeight: .infinity, alignment: .top)
                }
                .frame(width: 380)
            }
            .fixedSize(horizontal: false, vertical: true)
            HStack(alignment: .top, spacing: Theme.spacing) {
                CriteriaPanel()
                    .frame(maxWidth: .infinity)
                RecentRunsPanel()
                    .frame(width: 380)
            }
        }
    }
}

// MARK: - Aircraft

private struct AircraftPanel: View {
    @Environment(AppModel.self) private var model

    private let specs: [(String, String)] = [
        ("Flight controller", "PX4 · EKF2"),
        ("Companion", "Orange Pi 5 Pro · RK3588S"),
        ("NPU", "6 TOPS · RKNN"),
        ("Thermal", "TR256i · 256×192 · °C"),
        ("Navigation", "ArUco map · flow · range"),
        ("Battery", "6S LiPo"),
    ]

    var body: some View {
        GlassCard(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 6) {
                        Eyebrow(text: "Case 1 · University 2035")
                        Text("Autonomous forest-fire monitoring")
                            .font(.system(size: 22, weight: .semibold))
                            .tracking(-0.3)
                        Text("GPS-denied survey on an ArUco marker field. Thermal YOLO on the NPU finds ignition sources and reports each one with position and time.")
                            .font(.system(size: 13))
                            .foregroundStyle(Theme.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: 520, alignment: .leading)
                    }
                    Spacer(minLength: 16)
                    VStack(alignment: .trailing, spacing: 8) {
                        Button { model.section = .mission } label: { Label("Mission Control", systemImage: "scope") }
                            .buttonStyle(.primaryLarge)
                        Button {
                            model.startSimulation(autostart: true)
                            model.section = .mission
                        } label: { Label("Run simulation", systemImage: "play") }
                            .buttonStyle(.secondaryLarge)
                            .disabled(model.simulationRunning)
                    }
                    .fixedSize()
                }
                .padding(20)

                ZStack {
                    BlueprintGrid()
                    if let image = Bundle.main.image(forResource: "drone_iso") {
                        Image(nsImage: image)
                            .resizable()
                            .interpolation(.high)
                            .aspectRatio(contentMode: .fit)
                            .colorInvert()
                            .brightness(-0.08)
                            .opacity(0.92)
                            .padding(.horizontal, 40)
                            .padding(.vertical, 16)
                    }
                }
                .frame(height: 300)
                .clipped()

                Divider().overlay(Theme.hairline)
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 0, alignment: .leading), count: 3), spacing: 0) {
                    ForEach(specs, id: \.0) { s in
                        VStack(alignment: .leading, spacing: 3) {
                            Eyebrow(text: s.0)
                            Text(s.1).font(Theme.mono(12)).foregroundStyle(Theme.textPrimary).lineLimit(1)
                        }
                        .padding(.horizontal, 20)
                        .padding(.vertical, 12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
        }
    }
}

/// Faint engineering grid behind the aircraft render.
private struct BlueprintGrid: View {
    var body: some View {
        Canvas { ctx, size in
            var minor = Path(), major = Path()
            let step: CGFloat = 16
            for i in 0...Int(size.width / step) {
                let x = CGFloat(i) * step
                let line = [CGPoint(x: x, y: 0), CGPoint(x: x, y: size.height)]
                if i % 5 == 0 { major.addLines(line) } else { minor.addLines(line) }
            }
            for i in 0...Int(size.height / step) {
                let y = CGFloat(i) * step
                let line = [CGPoint(x: 0, y: y), CGPoint(x: size.width, y: y)]
                if i % 5 == 0 { major.addLines(line) } else { minor.addLines(line) }
            }
            ctx.stroke(minor, with: .color(.white.opacity(0.025)), lineWidth: 0.5)
            ctx.stroke(major, with: .color(.white.opacity(0.05)), lineWidth: 0.5)
        }
        .background(Theme.well)
        .drawingGroup()
    }
}

// MARK: - System status

private struct SystemStatusPanel: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let m = model.mission
        let ai = model.aiModel
        let spec = model.spec
        GlassCard(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader(title: "System status", symbol: "waveform.path.ecg").padding(.horizontal, 16).padding(.top, 14).padding(.bottom, 8)
                StatusRow(title: "Mission link", detail: m.connected ? "\(m.phase.lowercased()) · \(m.endpoint.label)" : (m.droneReachable ? "drone online, no mission running" : "not connected"),
                          state: m.connected ? .ok : (m.droneReachable ? .warn : .off))
                StatusRow(title: "Camera stream", detail: m.frame != nil ? "receiving" : "no frames", state: m.frame != nil ? .ok : .off)
                StatusRow(title: "Fire model", detail: ai.fireModel.map { m in m.map50.map { String(format: "mAP50 %.3f", $0) } ?? "trained" } ?? "not trained",
                          state: (ai.fireModel?.map50 ?? 0) >= 0.85 ? .ok : ai.fireModel == nil ? .warn : .warn)
                StatusRow(title: "NPU export", detail: (ai.fireModel?.formats.contains("rknn") ?? false) ? "RKNN ready" : "pending",
                          state: (ai.fireModel?.formats.contains("rknn") ?? false) ? .ok : .warn)
                StatusRow(title: "Thermal camera", detail: spec.checked.contains("thermal") ? "verified" : "not verified",
                          state: spec.checked.contains("thermal") ? .ok : .warn)
                StatusRow(title: "ArUco map", detail: spec.checked.contains("aruco") ? "verified" : "not verified",
                          state: spec.checked.contains("aruco") ? .ok : .warn)
                StatusRow(title: "Kill switch", detail: "RC channel 8", state: spec.checked.contains("kill") ? .ok : .warn, last: true)
            }
        }
    }
}

private struct StatusRow: View {
    enum State { case ok, warn, off }
    let title: String
    let detail: String
    let state: State
    var last = false

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Circle().fill(color).frame(width: 6, height: 6)
                Text(title).font(.system(size: 12.5))
                Spacer(minLength: 8)
                Text(detail).font(Theme.mono(11.5)).foregroundStyle(Theme.textSecondary).lineLimit(1)
            }
            .padding(.horizontal, 16)
            .frame(height: 36)
            if !last { Divider().overlay(Theme.hairline).padding(.leading, 32) }
        }
    }

    private var color: Color {
        switch state {
        case .ok: Theme.ok
        case .warn: Theme.caution
        case .off: Theme.textTertiary
        }
    }
}

// MARK: - Criteria

private struct CriteriaPanel: View {
    @Environment(AppModel.self) private var model

    /// Compact thresholds for the overview table (full text lives in Judging Spec).
    static let short: [String: String] = [
        "C1": "100 % · ≤ 0.25 m", "C2": "mAP50 ≥ 0.85", "C3": "1 of 1", "C4": "≥ 10 FPS · > 90 %",
        "C5": "≤ 0.5 m", "C6": "≤ 2 s", "C7": "≤ 2 s · ≤ 0.5 m",
    ]

    var body: some View {
        GlassCard(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader(title: "Mandatory characteristics · Module B2", symbol: "checklist",
                           trailing: Button("Open spec") { model.section = .spec }.buttonStyle(.quiet).eraseToAnyView())
                    .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 6)
                ForEach(model.spec.items) { item in
                    HStack(spacing: 12) {
                        Text(item.id).font(Theme.mono(11.5, .semibold)).foregroundStyle(Theme.textTertiary).frame(width: 24, alignment: .leading)
                        Text(item.title).font(.system(size: 12.5)).lineLimit(1)
                        Spacer(minLength: 8)
                        Text(Self.short[item.id] ?? item.threshold).font(Theme.mono(11)).foregroundStyle(Theme.textSecondary).lineLimit(1)
                            .frame(width: 150, alignment: .trailing)
                        Text(item.verdict.title)
                            .font(Theme.mono(10, .semibold))
                            .foregroundStyle(Theme.color(for: item.verdict))
                            .frame(width: 96, alignment: .trailing)
                    }
                    .padding(.horizontal, 16)
                    .frame(height: 34)
                    if item.id != "C7" { Divider().overlay(Theme.hairline).padding(.leading, 52) }
                }
            }
            .padding(.bottom, 6)
        }
    }
}

// MARK: - Recent runs

private struct RecentRunsPanel: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let runs = Array(model.runs.runs.filter { $0.duration > 1 || $0.kind != .mission }.prefix(7))
        GlassCard(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader(title: "Recent runs", symbol: "clock",
                           trailing: Button("All results") { model.section = .results }.buttonStyle(.quiet).eraseToAnyView())
                    .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 6)
                if runs.isEmpty {
                    Text("No runs yet").font(.system(size: 12.5)).foregroundStyle(Theme.textTertiary).padding(16)
                }
                ForEach(runs) { run in
                    HStack(spacing: 10) {
                        Image(systemName: run.isMock ? "cube.transparent" : "airplane")
                            .font(.system(size: 11))
                            .foregroundStyle(Theme.textTertiary)
                            .frame(width: 16)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(run.title).font(.system(size: 12.5)).lineLimit(1)
                            Text(run.date, format: .dateTime.day().month(.abbreviated).hour().minute())
                                .font(Theme.mono(10.5)).foregroundStyle(Theme.textTertiary)
                        }
                        Spacer(minLength: 6)
                        if run.kind == .mission {
                            Text("\(run.objects) obj").font(Theme.mono(11)).foregroundStyle(Theme.textSecondary)
                        }
                        Circle().fill(run.succeeded ? Theme.ok : Theme.caution).frame(width: 6, height: 6)
                    }
                    .padding(.horizontal, 16)
                    .frame(height: 42)
                }
            }
            .padding(.bottom, 6)
        }
    }
}

// MARK: - Next actions

private struct NextActionsPanel: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let spec = model.spec
        let steps: [(String, Bool)] = [
            ("Agree C1–C7 and [TBC] items with the lead expert", false),
            ("Thermal camera verified on the drone", spec.checked.contains("thermal")),
            ("Fire model ≥ 0.85 mAP50, exported to RKNN", (model.aiModel.fireModel?.map50 ?? 0) >= 0.85),
            ("Venue ArUco map checked with the roam test", spec.checked.contains("aruco")),
            ("Full mission flown and filmed", model.runs.missionRuns.contains { !$0.isMock }),
        ]
        GlassCard(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader(title: "Before the scored flight", symbol: "flag.checkered")
                    .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 4)
                ForEach(steps, id: \.0) { step in
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        Image(systemName: step.1 ? "checkmark.circle.fill" : "circle")
                            .font(.system(size: 12))
                            .foregroundStyle(step.1 ? Theme.ok : Theme.textTertiary)
                        Text(step.0)
                            .font(.system(size: 12.5))
                            .foregroundStyle(step.1 ? Theme.textTertiary : Theme.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 7)
                }
            }
            .padding(.bottom, 8)
            .frame(maxHeight: .infinity, alignment: .topLeading)
        }
    }
}
