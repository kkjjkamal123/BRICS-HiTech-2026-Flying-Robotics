import AVKit
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
            SimVideoCard()
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

// MARK: - Replay video

private struct SimVideoCard: View {
    @Environment(AppModel.self) private var model
    @State private var player: AVPlayer?
    @State private var clip = "—"
    @State private var frame = "—"

    private var url: URL { model.settings.toolkitRoot.appending(path: "runs/sim_videos/aruco_roam_sim.mp4") }

    var body: some View {
        let exists = FileManager.default.fileExists(atPath: url.path(percentEncoded: false))
        GlassCard {
            VStack(alignment: .leading, spacing: 12) {
                CardHeader(title: "ArUco roam test · simulation replay", symbol: "film",
                           trailing: Text("runs/sim_videos/aruco_roam_sim.mp4")
                            .font(Theme.mono(11)).foregroundStyle(Theme.textTertiary)
                            .lineLimit(1).truncationMode(.head).eraseToAnyView())
                if exists {
                    HStack(alignment: .top, spacing: 20) {
                        video
                            .frame(maxWidth: 760)
                            .layoutPriority(1)
                        details
                            .frame(minWidth: 230, maxWidth: .infinity, alignment: .leading)
                    }
                } else {
                    ContentUnavailableView("No replay yet", systemImage: "film",
                                           description: Text("Render it to runs/sim_videos/aruco_roam_sim.mp4"))
                        .frame(maxWidth: .infinity)
                        .frame(height: 220)
                        .background(Theme.well, in: .rect(cornerRadius: Theme.radius))
                }
            }
        }
        .task(id: url) { await load(exists: exists) }
        .onDisappear { player?.pause() }
    }

    private var video: some View {
        PlayerView(player: player)
            .aspectRatio(16 / 9, contentMode: .fit)
            .background(Color.black)
            .clipShape(.rect(cornerRadius: Theme.radius))
            .overlay(RoundedRectangle(cornerRadius: Theme.radius).strokeBorder(Theme.hairline))
    }

    private var details: some View {
        VStack(alignment: .leading, spacing: 0) {
            fact("Script", "aruco_roam_test.py")
            fact("Clip", clip)
            fact("Frame", frame)
            Rectangle().fill(Theme.hairline).frame(height: 1).padding(.vertical, 12)
            Eyebrow(text: "Sequence").padding(.bottom, 8)
            VStack(alignment: .leading, spacing: 7) {
                step(1, "Lock start on marker map")
                step(2, "Roam random points in the safe zone")
                step(3, "Fly back to the start point")
                step(4, "Slow descent, land, disarm")
            }
        }
    }

    private func fact(_ label: String, _ value: String) -> some View {
        HStack(spacing: 8) {
            Text(label)
                .font(.system(size: 12))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: 52, alignment: .leading)
            Text(value)
                .font(Theme.mono(11.5))
                .foregroundStyle(Theme.textPrimary)
                .lineLimit(1)
                .truncationMode(.middle)
                .contentTransition(.numericText())
            Spacer(minLength: 0)
        }
        .frame(height: 24)
    }

    private func step(_ n: Int, _ text: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text("\(n)")
                .font(Theme.mono(10.5, .semibold))
                .foregroundStyle(Theme.textTertiary)
                .frame(width: 14, alignment: .leading)
            Text(text)
                .font(.system(size: 12))
                .foregroundStyle(Theme.textSecondary)
                .lineLimit(1)
                .minimumScaleFactor(0.9)
        }
    }

    private func load(exists: Bool) async {
        guard exists else { return }
        if player == nil { player = AVPlayer(url: url) }
        let asset = AVURLAsset(url: url)
        if let d = try? await asset.load(.duration), d.isNumeric {
            clip = Duration.seconds(d.seconds).formatted(.time(pattern: .minuteSecond))
        }
        if let track = try? await asset.loadTracks(withMediaType: .video).first,
           let size = try? await track.load(.naturalSize) {
            frame = "\(Int(size.width)) × \(Int(size.height))"
        }
    }
}

/// AppKit `AVPlayerView` host. SwiftUI's `VideoPlayer` aborts at launch on this macOS build
/// (AVKit_SwiftUI class-metadata fault), so the AppKit view is used directly.
private struct PlayerView: NSViewRepresentable {
    let player: AVPlayer?

    func makeNSView(context: Context) -> AVPlayerView {
        let view = AVPlayerView()
        view.controlsStyle = .floating
        view.videoGravity = .resizeAspect
        view.showsFullScreenToggleButton = true
        view.player = player
        return view
    }

    func updateNSView(_ view: AVPlayerView, context: Context) {
        if view.player !== player { view.player = player }
    }
}
