import SwiftUI

struct SimulationView: View {
    var body: some View {
        Page(section: .simulation) {
            HStack(alignment: .top, spacing: Theme.spacing) {
                SimLauncher()
                SimScope()
                    .frame(width: 400)
            }
            .fixedSize(horizontal: false, vertical: true)
            ConsolePanel(height: 260)
        }
    }
}

// MARK: - Launcher

private struct SimLauncher: View {
    @Environment(AppModel.self) private var model
    @State private var timeScale = 3.0
    @State private var autostart = true

    var body: some View {
        let running = model.simulationRunning
        GlassCard {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader(title: "Mock mission", symbol: "play.circle",
                           trailing: StatusPill(text: running ? "Running" : "Idle",
                                                color: running ? Theme.accent : Theme.textTertiary,
                                                pulsing: running).eraseToAnyView())
                Text("Runs drone/case1_fire.py --mock: the real planner, detectors, tracker, safety layer and report against a simulated drone and field.")
                    .font(.system(size: 12.5))
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 8)
                Rectangle().fill(Theme.hairline).frame(height: 1).padding(.vertical, 14)
                VStack(spacing: 10) {
                    ParamSlider(label: "Speed-up", value: $timeScale, range: 1...10, step: 1, format: "%.0f", unit: "×")
                        .disabled(running)
                    AutostartRow(isOn: $autostart)
                        .disabled(running)
                    ParamInfoRow(label: "Operator UI", value: "127.0.0.1:\(model.settings.simulatorPort)")
                    HStack(spacing: 12) {
                        ParamInfoRow(label: "Mission", value: model.missionSettings.summary)
                            .help(model.missionSettings.summary)
                        Button("Edit…") { model.showMissionSettings = true }
                            .buttonStyle(.secondary)
                            .fixedSize()
                    }
                }
                Spacer(minLength: 16)
                actions(running: running)
            }
            .frame(maxHeight: .infinity, alignment: .top)
        }
    }

    private func actions(running: Bool) -> some View {
        HStack(spacing: 10) {
            if running {
                Button { model.stopSimulation() } label: {
                    Label("Stop simulation", systemImage: "stop.fill").frame(maxWidth: .infinity)
                }
                .buttonStyle(.primary(Theme.critical, large: true))
            } else {
                Button {
                    model.startSimulation(timeScale: timeScale, autostart: autostart)
                    model.section = .mission
                } label: {
                    Label("Run simulation", systemImage: "play.fill").frame(maxWidth: .infinity)
                }
                .buttonStyle(.primaryLarge)
                .help("Starts the mock mission and opens Mission Control")
            }
            Button { model.section = .mission } label: {
                Label("Watch in Mission Control", systemImage: "scope").frame(maxWidth: .infinity)
            }
            .buttonStyle(.secondaryLarge)
        }
        .lineLimit(1)
        .animation(.snappy(duration: 0.2), value: running)
    }
}

/// Toggle row on the same label / control / value grid as `ParamSlider`.
private struct AutostartRow: View {
    @Binding var isOn: Bool

    var body: some View {
        HStack(spacing: 12) {
            Text("Autostart")
                .font(.system(size: 12.5))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: ParamLayout.labelWidth, alignment: .leading)
            Text("Begin without pressing START in the operator UI")
                .font(.system(size: 12))
                .foregroundStyle(Theme.textTertiary)
                .lineLimit(1)
                .truncationMode(.tail)
            Spacer(minLength: 8)
            Toggle("Autostart", isOn: $isOn)
                .toggleStyle(.switch)
                .controlSize(.mini)
                .labelsHidden()
                .frame(width: ParamLayout.valueWidth, alignment: .trailing)
        }
        .frame(height: 22)
    }
}

// MARK: - Scope

private struct SimScope: View {
    private let simulated: [(String, String)] = [
        ("Drone motion", "kinematic, TECHNIC navigate / land API"),
        ("Cameras", "RGB + thermal, °C per pixel"),
        ("Targets", "campfire, IR heater, green decoy"),
        ("Mission code", "planner, detectors, tracker, report"),
    ]
    private let notSimulated: [(String, String)] = [
        ("Aerodynamics", "thrust, drag, wind, ground effect"),
        ("Marker pose", "ArUco detection noise, dropouts"),
    ]

    var body: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader(title: "Scope", symbol: "square.dashed")
                group(title: "Simulated", symbol: "checkmark", tint: Theme.textSecondary, rows: simulated)
                    .padding(.top, 10)
                Rectangle().fill(Theme.hairline).frame(height: 1).padding(.vertical, 12)
                group(title: "Not simulated", symbol: "minus", tint: Theme.textTertiary, rows: notSimulated)
                Text("Covered by the flight tests instead.")
                    .font(.system(size: 11.5))
                    .foregroundStyle(Theme.textTertiary)
                    .padding(.top, 8)
                    .padding(.leading, 22)
            }
        }
    }

    private func group(title: String, symbol: String, tint: Color, rows: [(String, String)]) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Eyebrow(text: title)
                .padding(.bottom, 2)
            ForEach(rows, id: \.0) { row in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Image(systemName: symbol)
                        .font(.system(size: 9.5, weight: .bold))
                        .foregroundStyle(tint)
                        .frame(width: 14)
                    Text(row.0)
                        .font(.system(size: 12.5, weight: .medium))
                        .foregroundStyle(Theme.textPrimary)
                        .frame(width: 96, alignment: .leading)
                    Text(row.1)
                        .font(.system(size: 12))
                        .foregroundStyle(Theme.textSecondary)
                        .lineLimit(1)
                        .truncationMode(.tail)
                }
            }
        }
    }
}
