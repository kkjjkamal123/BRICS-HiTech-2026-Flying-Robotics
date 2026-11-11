import Charts
import SwiftUI

// Mission Control: the live console. The page itself reads no observable state; every panel below is its
// own view and reads only the `MissionClient` properties it needs, so a 6 Hz camera frame redraws only the
// camera layer, and the ~2 Hz status poll redraws only the panels showing status.

struct MissionControlView: View {
    var body: some View {
        Page(section: .mission, trailing: SourceBadge().eraseToAnyView()) {
            SplitColumns {
                CameraCard()
                LiveMapCard()
            }
            TelemetryRail()
            SplitColumns(height: 268) {
                DetectionsCard()
                AltitudeCard()
            }
            MissionLogCard()
            ConsolePanel(height: 260)
        }
        .scrollEdgeEffectStyle(.soft, for: .bottom)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            CommandBar()
                .padding(.horizontal, 28)
                .padding(.bottom, 14)
                .padding(.top, 6)
                .frame(maxWidth: 1640)
                .frame(maxWidth: .infinity)
        }
    }
}

/// Two columns that line up across rows: the left column is a 16:9 camera, the right one is square at the
/// same height. With `height` set, a row reuses the same column widths at a fixed height.
private struct SplitColumns: Layout {
    var spacing: CGFloat = Theme.spacing
    var height: CGFloat?

    private func columns(_ width: CGFloat) -> (left: CGFloat, right: CGFloat, hero: CGFloat) {
        let hero = max(200, (width - spacing) / (16.0 / 9.0 + 1))
        let left = (hero * 16 / 9).rounded()
        return (left, max(0, width - spacing - left), hero.rounded())
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let w = proposal.width ?? 900
        return CGSize(width: w, height: height ?? columns(w).hero)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let c = columns(bounds.width)
        let h = bounds.height
        if subviews.count > 0 {
            subviews[0].place(at: bounds.origin, proposal: ProposedViewSize(width: c.left, height: h))
        }
        if subviews.count > 1 {
            subviews[1].place(at: CGPoint(x: bounds.minX + c.left + spacing, y: bounds.minY),
                              proposal: ProposedViewSize(width: c.right, height: h))
        }
    }
}

private struct SourceBadge: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let m = model.mission
        HStack(spacing: 10) {
            Text(model.settings.missionSource == .drone ? "TECHNIC 6S · \(m.endpoint.label)" : "SIMULATOR · \(m.endpoint.label)")
                .font(Theme.mono(11))
                .foregroundStyle(Theme.textTertiary)
                .lineLimit(1)
            StatusPill(text: m.connected ? "Link" : (m.droneReachable ? "Drone online · no mission" : "No link"),
                       color: m.connected ? Theme.ok : (m.droneReachable ? Theme.signal : Theme.textTertiary), pulsing: m.connected)
        }
        .fixedSize()
    }
}

// MARK: - Mission phase model

private enum MissionPhase {
    static let steps = ["WAITING", "TAKEOFF", "MISSION", "INSPECT", "RETURN", "LAND", "DONE"]

    /// Index of the timeline step for a phase reported by the mission, nil when it is not on the timeline.
    static func step(_ phase: String) -> Int? {
        switch phase.uppercased() {
        case "WAITING", "IDLE", "PREFLIGHT", "STARTING": 0
        case "TAKEOFF": 1
        case "MISSION": 2
        case "INSPECT": 3
        case "RETURN": 4
        case "LAND", "ABORT": 5
        case "REPORT", "DONE": 6
        default: nil
        }
    }

    static func color(_ phase: String) -> Color {
        switch phase.uppercased() {
        case "STOPPED", "ABORT": Theme.critical
        case "WAITING", "IDLE", "PREFLIGHT": Theme.textPrimary
        case "STARTING": Theme.caution
        default: Theme.color(forPhase: phase)
        }
    }

    static func isAirborne(_ phase: String) -> Bool {
        ["TAKEOFF", "MISSION", "INSPECT", "RETURN", "LAND"].contains(phase.uppercased())
    }

    static func isFinished(_ phase: String) -> Bool {
        ["DONE", "REPORT", "STOPPED"].contains(phase.uppercased())
    }
}

// MARK: - Command bar (floating glass)

private struct CommandBar: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let m = model.mission
        let phase = m.phase
        let connected = m.connected
        let known = MissionPhase.step(phase) != nil || MissionPhase.isFinished(phase)
        // Drone is there but no mission script runs: the buttons act on the drone directly.
        let direct = !connected && m.droneReachable && model.settings.missionSource == .drone
        let link = DroneLink(settings: model.settings, console: model.console)
        HStack(spacing: 16) {
            PhaseReadout(phase: phase, live: connected && !MissionPhase.isFinished(phase))
            BarDivider()
            VStack(alignment: .leading, spacing: 5) {
                ViewThatFits(in: .horizontal) {
                    PhaseTimeline(phase: phase, connected: connected)
                    PhaseSegments(phase: phase, connected: connected)
                }
                StatusLine(status: direct ? "Drone online, no mission running. Run mission takes off after a 3 s countdown; Land calls the drone's land service."
                                          : (m.status?.status ?? ""),
                           connected: connected || direct, last: m.lastCommand)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            HStack(spacing: 8) {
                if direct {
                    Menu {
                        Button("ArUco scan (manual flight, never arms)", systemImage: "qrcode.viewfinder") {
                            link.copyAndRunScript("ArUco scan (manual flight)", toolkit: model.settings.toolkitRoot, script: "aruco_scan.py", args: [])
                        }
                        Button("Test connection", systemImage: "bolt.horizontal") { link.testConnection() }
                        Divider()
                        Button("Hover, roam and motor tests…", systemImage: "airplane.departure") { model.section = .flightTests }
                    } label: {
                        Label("Run", systemImage: "chevron.up")
                            .font(.system(size: 13.5, weight: .medium))
                            .foregroundStyle(Theme.textPrimary)
                            .padding(.horizontal, 12)
                            .frame(height: 34)
                            .background(Color.white.opacity(0.03), in: .rect(cornerRadius: 8))
                            .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Theme.hairline))
                    }
                    .menuStyle(.button)
                    .buttonStyle(.plain)
                    .menuIndicator(.hidden)
                    .fixedSize()
                    .help("Run a script on the drone. Output appears in the console at the bottom of this page.")
                    MissionSettingsButton()
                    RunMissionButton()
                } else if model.settings.missionSource == .drone {
                    MissionSettingsButton()
                    RunMissionButton()
                } else {
                    MissionSettingsButton()
                    Button { m.send(.start) } label: { Label("Start", systemImage: "play.fill") }
                        .buttonStyle(.primaryLarge)
                        .disabled(!connected || (known && MissionPhase.step(phase) != 0))
                        .help("Start the mission (⇧⌘R)")
                }
                Button { m.send(.returnHome) } label: { Label("Return Home", systemImage: "house") }
                    .buttonStyle(.secondaryLarge)
                    .disabled(!connected || (known && !["TAKEOFF", "MISSION", "INSPECT"].contains(phase.uppercased())))
                    .help("Fly back to the home pad and land (⇧⌘H)")
                Button { if direct { link.landNow() } else { m.send(.land) } } label: { Label("Land", systemImage: "arrow.down.to.line") }
                    .buttonStyle(.secondaryLarge)
                    .disabled(direct ? false : (!connected || (known && !MissionPhase.isAirborne(phase))))
                    .help(direct ? "Calls the drone's land service directly - works whatever script is flying it"
                                 : "Land where the drone is now (⇧⌘L)")
            }
            .labelStyle(.titleAndIcon)
            .fixedSize()
            BarDivider()
            HoldToConfirmButton(title: "ABORT", symbol: "xmark") { if direct { link.landNow() } else { m.send(.abort) } }
                .disabled(direct ? false : (!connected || MissionPhase.isFinished(phase)))
                .fixedSize()
                .scaleEffect(34.0 / 38.0)   // the shared hold button is 38 pt; match the 34 pt row
                .frame(height: 34)
        }
        .padding(.leading, 18)
        .padding(.trailing, 12)
        .frame(height: 62)
        .glassEffect(.regular.tint(Theme.canvas.opacity(0.35)), in: .rect(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).strokeBorder(Theme.hairline))
    }
}

/// Run mission (drone): always a clean new run. A previous mission on the ground is stopped first; while the drone
/// is flying the button is disabled (land first).
private struct RunMissionButton: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let m = model.mission
        let blocked = !model.missionSettings.problems(markerField: MissionSettings.Venue.markerField(from: m.status?.markers)).isEmpty
        let replacing = m.connected || model.console.jobs.contains { $0.isRunning && $0.title.hasPrefix("Case 1 mission") }
        Button { model.runNewDroneMission() } label: {
            Label(replacing ? "Run new mission" : "Run mission", systemImage: "play.fill")
        }
        .buttonStyle(.primaryLarge)
        .disabled(model.droneMissionAirborne || blocked)
        .help(model.droneMissionAirborne ? "The drone is flying - land it first (Land / ABORT)."
              : blocked ? "Mission settings have a problem - open Settings."
              : replacing ? "Stops the previous mission (only while the motors are disarmed), clears the screen and runs a fresh one: pre-flight, 3 s countdown, take-off."
              : "Runs the Case 1 mission with your Mission settings: pre-flight check, 3 s countdown, take-off. ABORT cancels.")
    }
}

/// Opens the Mission settings sheet; shows a dot when the settings differ from the venue defaults.
private struct MissionSettingsButton: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let ms = model.missionSettings
        let blocked = !ms.problems(markerField: MissionSettings.Venue.markerField(from: model.mission.status?.markers)).isEmpty
        Button { model.showMissionSettings = true } label: {
            Label("Settings", systemImage: "slider.horizontal.3")
                .overlay(alignment: .topTrailing) {
                    if blocked || !ms.isVenueDefault {
                        Circle().fill(blocked ? Theme.critical : Theme.accent).frame(width: 6, height: 6).offset(x: 6, y: -3)
                    }
                }
        }
        .buttonStyle(.secondaryLarge)
        .help(blocked ? "Mission settings have a problem - the mission will not start. Click to fix."
                      : "Mission settings: \(ms.summary)")
    }
}

private struct BarDivider: View {
    var body: some View {
        Rectangle().fill(Theme.hairlineStrong).frame(width: 1, height: 30)
    }
}

private struct PhaseReadout: View {
    let phase: String
    let live: Bool

    var body: some View {
        let color = MissionPhase.color(phase)
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 6) {
                LiveDot(color: live ? color : Theme.textTertiary, live: live)
                Eyebrow(text: "Phase")
            }
            Text(phase.uppercased())
                .font(Theme.mono(17, .semibold))
                .foregroundStyle(color)
                .lineLimit(1)
                .contentTransition(.interpolate)
                .animation(.smooth(duration: 0.25), value: phase)
        }
        .frame(width: 104, alignment: .leading)
        .accessibilityElement(children: .combine)
    }
}

/// WAITING › TAKEOFF › MISSION › … with the current step highlighted.
private struct PhaseTimeline: View {
    let phase: String
    let connected: Bool

    var body: some View {
        let current = connected ? MissionPhase.step(phase) : nil
        let color = MissionPhase.color(phase)
        HStack(spacing: 4) {
            ForEach(Array(MissionPhase.steps.enumerated()), id: \.element) { i, step in
                if i > 0 {
                    Image(systemName: "chevron.compact.right")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(Theme.textTertiary.opacity(0.7))
                }
                Text(step)
                    .font(Theme.mono(9.5, i == current ? .bold : .medium))
                    .tracking(0.3)
                    .foregroundStyle(stepColor(i, current: current, color: color))
                    .padding(.horizontal, 5)
                    .frame(height: 17)
                    .background {
                        if i == current {
                            RoundedRectangle(cornerRadius: 4).fill(color.opacity(0.14))
                            RoundedRectangle(cornerRadius: 4).strokeBorder(color.opacity(0.35), lineWidth: 0.75)
                        }
                    }
            }
        }
        .fixedSize()
        .animation(.snappy(duration: 0.25), value: current)
    }

    private func stepColor(_ i: Int, current: Int?, color: Color) -> Color {
        guard let current else { return Theme.textTertiary }
        if i == current { return color }
        return i < current ? Theme.textSecondary : Theme.textTertiary
    }
}

/// Compact fallback for narrow windows: seven segments plus the step count.
private struct PhaseSegments: View {
    let phase: String
    let connected: Bool

    var body: some View {
        let current = connected ? MissionPhase.step(phase) : nil
        let color = MissionPhase.color(phase)
        HStack(spacing: 8) {
            HStack(spacing: 3) {
                ForEach(0..<MissionPhase.steps.count, id: \.self) { i in
                    Capsule()
                        .fill(i == current ? color : (current.map { i < $0 } ?? false) ? Theme.textSecondary : Color.white.opacity(0.1))
                        .frame(width: 14, height: 3)
                }
            }
            Text(current.map { "STEP \($0 + 1)/\(MissionPhase.steps.count)" } ?? "—")
                .font(Theme.mono(9.5, .medium))
                .foregroundStyle(Theme.textTertiary)
        }
        .frame(height: 17)
        .fixedSize()
        .animation(.snappy(duration: 0.25), value: current)
    }
}

/// Mission status text, temporarily replaced by the result of the last command sent.
private struct StatusLine: View {
    let status: String
    let connected: Bool
    let last: (command: MissionCommand, ok: Bool, at: Date)?
    @State private var showFeedback = false

    var body: some View {
        Group {
            if showFeedback, let last {
                Label(last.ok ? "\(last.command.title.uppercased()) sent" : "\(last.command.title.uppercased()) not delivered: use the RC",
                      systemImage: last.ok ? "checkmark" : "exclamationmark.triangle.fill")
                    .foregroundStyle(last.ok ? Theme.ok : Theme.critical)
            } else {
                Text(connected ? (status.isEmpty ? "No status message" : status) : "No link. Commands disabled.")
                    .foregroundStyle(connected && !status.isEmpty ? Theme.textSecondary : Theme.textTertiary)
            }
        }
        .font(.system(size: 11.5))
        .lineLimit(1)
        .truncationMode(.tail)
        .transition(.opacity)
        .task(id: last?.at) {
            guard let at = last?.at, Date().timeIntervalSince(at) < 4 else { return }
            withAnimation(.smooth(duration: 0.2)) { showFeedback = true }
            try? await Task.sleep(for: .seconds(4))
            withAnimation(.smooth(duration: 0.3)) { showFeedback = false }
        }
    }
}

// MARK: - Camera

private struct CameraCard: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        HStack(spacing: 0) {
            ZStack {
                Color.black
                CameraFrameLayer()
                CameraHUD()
                    .padding(12)
            }
            if model.mission.showsThermalPane {
                Rectangle().fill(Theme.hairlineStrong).frame(width: 1)
                ThermalPane()
            }
        }
        .background(Color.black)
        .clipShape(.rect(cornerRadius: Theme.cardRadius))
        .overlay(RoundedRectangle(cornerRadius: Theme.cardRadius).strokeBorder(Theme.hairline))
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Live camera with detections")
    }
}

/// Second feed: the thermal camera, straight from the drone. The only view that reads `thermalImage`.
private struct ThermalPane: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let m = model.mission
        ZStack {
            Color.black
            if let image = m.thermalImage {
                Image(nsImage: image)
                    .resizable()
                    .interpolation(.high)
                    .aspectRatio(contentMode: .fit)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if m.thermalTopic == nil {
                NoSignal(title: "NO THERMAL CAMERA", detail: "The drone does not see it. Plug the TR256i into the drone's USB port.")
            } else {
                NoSignal(title: "ACQUIRING THERMAL", detail: "Opening the thermal camera", busy: true)
            }
            VStack {
                HStack(spacing: 6) {
                    HUDChip {
                        LiveDot(color: m.thermalImage != nil ? Theme.critical : Theme.textTertiary, live: m.thermalImage != nil)
                        Text("THERMAL").foregroundStyle(Theme.textPrimary)
                    }
                    if m.thermalIsRaw {
                        Button { m.thermalPalette.toggle() } label: {
                            HUDChip {
                                Image(systemName: "thermometer.medium").foregroundStyle(Theme.textTertiary)
                                Text(m.thermalPalette ? "IRON" : "WHITE HOT").foregroundStyle(Theme.textPrimary)
                            }
                        }
                        .buttonStyle(.plain)
                        .help("Picture only (no temperatures): the drone's thermal node is not running. Switch palette.")
                    } else if m.thermalImage != nil {
                        HUDChip {
                            Image(systemName: "thermometer.medium").foregroundStyle(Theme.textTertiary)
                            Text(String(format: "°C · FIRE ≥ %.0f", (m.connected ? m.status?.settings?.fire_c : nil) ?? model.missionSettings.fireC))
                                .foregroundStyle(Theme.textPrimary)
                        }
                    }
                    Spacer(minLength: 0)
                }
                Spacer(minLength: 0)
            }
            .padding(12)
        }
        .accessibilityLabel("Thermal camera")
    }
}

/// The only view that reads `frame` (≈ 6 Hz).
private struct CameraFrameLayer: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let m = model.mission
        if let frame = m.frame {
            Image(nsImage: frame)
                .resizable()
                .interpolation(m.thermalFrame && m.directVideo ? .high : .medium)
                .aspectRatio(contentMode: .fit)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .opacity(m.videoLive ? 1 : 0.35)
                .saturation(m.videoLive ? 1 : 0)
                .overlay {
                    if m.videoLive {
                        Reticle()
                            .stroke(Color.white.opacity(0.32), lineWidth: 1)
                            .frame(width: 44, height: 44)
                            .allowsHitTesting(false)
                    } else {
                        NoSignal(title: "SIGNAL LOST", detail: "Showing the last frame received")
                    }
                }
        } else if m.connected {
            NoSignal(title: "ACQUIRING VIDEO", detail: "Telemetry is live, waiting for the first camera frame", busy: true)
        } else if m.directVideo {
            NoSignal(title: "ACQUIRING VIDEO", detail: "Drone found, opening \(m.cameraTopic ?? "camera")", busy: true)
        } else {
            NoSignal(title: "NO SIGNAL", detail: "Connect to the drone or start the simulator")
        }
    }
}

private struct NoSignal: View {
    let title: String
    let detail: String
    var busy = false

    var body: some View {
        VStack(spacing: 8) {
            if busy {
                ProgressView().controlSize(.small)
            } else {
                Image(systemName: "video.slash")
                    .font(.system(size: 20, weight: .light))
                    .foregroundStyle(Theme.textTertiary)
            }
            Text(title)
                .font(Theme.mono(12, .semibold))
                .tracking(2)
                .foregroundStyle(Theme.textSecondary)
            Text(detail)
                .font(.system(size: 11.5))
                .foregroundStyle(Theme.textTertiary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// Centre crosshair with a gap, like a gimbal OSD.
private struct Reticle: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        let gap: CGFloat = 7
        p.move(to: CGPoint(x: r.minX, y: r.midY)); p.addLine(to: CGPoint(x: r.midX - gap, y: r.midY))
        p.move(to: CGPoint(x: r.midX + gap, y: r.midY)); p.addLine(to: CGPoint(x: r.maxX, y: r.midY))
        p.move(to: CGPoint(x: r.midX, y: r.minY)); p.addLine(to: CGPoint(x: r.midX, y: r.midY - gap))
        p.move(to: CGPoint(x: r.midX, y: r.midY + gap)); p.addLine(to: CGPoint(x: r.midX, y: r.maxY))
        return p
    }
}

/// Corner chips over the image. Reads status (~2 Hz), never the frame.
private struct CameraHUD: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let m = model.mission
        let s = m.status
        let live = m.videoLive
        let fps = (s?.fps ?? [:]).sorted { $0.key < $1.key }
        VStack {
            HStack(alignment: .top) {
                HStack(spacing: 6) {
                    HUDChip {
                        LiveDot(color: live ? Theme.critical : Theme.textTertiary, live: live)
                        Text(live ? "LIVE" : "OFFLINE").foregroundStyle(live ? Theme.textPrimary : Theme.textTertiary)
                    }
                    if m.videoLive || model.recorder.isRecording { RecordButton() }
                    if m.videoEndpoint != nil, m.directVideo || (m.connected && m.droneReachable) { CameraTopicMenu() }
                    if m.directVideo, m.thermalFrame {
                        Button { m.thermalPalette.toggle() } label: {
                            HUDChip {
                                Image(systemName: "thermometer.medium").foregroundStyle(Theme.textTertiary)
                                Text(m.thermalPalette ? "IRON" : "WHITE HOT").foregroundStyle(Theme.textPrimary)
                            }
                        }
                        .buttonStyle(.plain)
                        .help("Thermal camera: switch between the iron palette and white-hot greyscale")
                    }
                }
                Spacer(minLength: 8)
                HStack(spacing: 6) {
                    ForEach(fps, id: \.key) { cam, v in
                        HUDChip {
                            Text(cam.uppercased()).foregroundStyle(Theme.textTertiary)
                            Text(String(format: "%.0f", v)).foregroundStyle(v >= 10 ? Theme.textPrimary : Theme.caution)
                                .contentTransition(.numericText(value: v))
                            Text("FPS").foregroundStyle(Theme.textTertiary)
                        }
                    }
                }
            }
            Spacer(minLength: 8)
            HStack(alignment: .bottom) {
                if let p = s?.position {
                    HUDChip {
                        Text("ALT").foregroundStyle(Theme.textTertiary)
                        Text(String(format: "%.2f", p.z)).foregroundStyle(Theme.textPrimary)
                            .contentTransition(.numericText())
                        Text("m").foregroundStyle(Theme.textTertiary)
                    }
                }
                Spacer(minLength: 8)
                if let p = s?.position {
                    HUDChip {
                        Text("X").foregroundStyle(Theme.textTertiary)
                        Text(String(format: "%.2f", p.x)).foregroundStyle(Theme.textPrimary)
                        Text("Y").foregroundStyle(Theme.textTertiary)
                        Text(String(format: "%.2f", p.y)).foregroundStyle(Theme.textPrimary)
                    }
                }
            }
        }
        .animation(.smooth(duration: 0.3), value: s?.pos)
    }
}

/// Main pane camera menu: the mission's own view (while a mission runs), the main camera, the debug views the drone
/// publishes (ArUco markers / map pose), thermal, plus the stream quality. Works with and without a mission.
private struct CameraTopicMenu: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let m = model.mission
        let topics = m.cameraTopics.filter { $0 != "/thermal/temp" }     // raw °C numbers, not a picture
        let selection = Binding<String>(get: { m.shownTopic ?? "" }, set: { t in
            if m.connected {
                m.missionViewTopic = t.isEmpty ? nil : t
            } else if !t.isEmpty {
                UserDefaults.standard.set(t, forKey: "cameraTopicChosen")
                m.cameraTopic = t
            }
        })
        Menu {
            Picker("Camera view", selection: selection) {
                if m.connected {
                    Label("Mission view (detections drawn)", systemImage: "scope").tag("")
                }
                ForEach(MissionClient.TopicGroup.allCases, id: \.self) { group in
                    let items = topics.filter { MissionClient.group($0) == group }
                    if !items.isEmpty {
                        Section(group.rawValue) {
                            ForEach(items, id: \.self) { topic in
                                Text(MissionClient.topicTitle(topic) == topic ? topic : "\(MissionClient.topicTitle(topic))   \(topic)").tag(topic)
                            }
                        }
                    }
                }
            }
            .pickerStyle(.inline)
            Divider()
            Picker("Stream quality", selection: Binding(get: { m.streamQuality }, set: { m.streamQuality = $0 })) {
                Text("Low (30) - weak Wi-Fi").tag(30)
                Text("Medium (50)").tag(50)
                Text("High (80)").tag(80)
                Text("Full (95)").tag(95)
            }
            .help("JPEG quality of camera topics streamed straight from the drone. The mission view has its own quality (ui.quality).")
        } label: {
            HUDChip {
                Image(systemName: "video").foregroundStyle(Theme.textTertiary)
                Text(m.shownTopic.map(MissionClient.topicTitle) ?? "Mission view").foregroundStyle(Theme.textPrimary).lineLimit(1)
                Image(systemName: "chevron.down").font(.system(size: 7, weight: .bold)).foregroundStyle(Theme.textTertiary)
            }
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Choose what the main pane shows: mission view, main camera, ArUco debug views, thermal. Stream quality is in the same menu.")
    }
}

/// REC: click to start / stop recording; the menu picks the camera(s). Both = two .mp4 files at the same time.
private struct RecordButton: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let r = model.recorder
        Menu {
            Picker("Record", selection: Binding(get: { r.cameras }, set: { r.cameras = $0 })) {
                ForEach(RecordCameras.allCases) { Text($0.title).tag($0) }
            }
            .pickerStyle(.inline)
            .disabled(r.isRecording)
            Divider()
            Button(r.isRecording ? "Stop recording" : "Start recording", systemImage: r.isRecording ? "stop.fill" : "record.circle") {
                r.toggle(root: model.settings.toolkitRoot)
            }
            if r.folder != nil {
                Button("Show recordings in Finder", systemImage: "folder") { r.revealInFinder() }
            }
            if let e = r.lastError { Text(e) }
        } label: {
            HUDChip {
                Circle().fill(r.isRecording ? Theme.critical : Theme.textTertiary).frame(width: 7, height: 7)
                if r.isRecording, let t0 = r.startedAt {
                    TimelineView(.periodic(from: t0, by: 1)) { ctx in
                        let s = max(0, Int(ctx.date.timeIntervalSince(t0)))
                        Text(String(format: "REC %d:%02d", s / 60, s % 60)).foregroundStyle(Theme.textPrimary)
                    }
                    Text(r.cameras == .both ? "MAIN+THERMAL" : r.cameras == .main ? "MAIN" : "THERMAL").foregroundStyle(Theme.textTertiary)
                } else {
                    Text("REC").foregroundStyle(Theme.textSecondary)
                    Text(r.cameras == .both ? "BOTH" : r.cameras == .main ? "MAIN" : "THERMAL").foregroundStyle(Theme.textTertiary)
                }
            }
        } primaryAction: {
            r.toggle(root: model.settings.toolkitRoot)
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
        .fixedSize()
        .help(r.isRecording ? "Recording to \(r.folder?.lastPathComponent ?? "") - click to stop"
                            : "Click to record the camera view to .mp4 (runs/recordings). Hold or right-click to choose main, thermal or both.")
    }
}

private struct HUDChip<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        HStack(spacing: 5) { content }
            .font(Theme.mono(10.5, .semibold))
            .monospacedDigit()
            .lineLimit(1)
            .padding(.horizontal, 8)
            .frame(height: 22)
            .background(Color.black.opacity(0.55), in: .rect(cornerRadius: 6))
            .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Color.white.opacity(0.12), lineWidth: 0.75))
            .fixedSize()
    }
}

// MARK: - Map

private struct LiveMapCard: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let s = model.mission.status
        let track = (s?.track ?? []).compactMap { $0.count >= 2 ? SIMD2($0[0], $0[1]) : nil }
        GlassCard(padding: 12) {
            VStack(alignment: .leading, spacing: 6) {
                CardHeader(title: "Live map", symbol: "map",
                           trailing: HeadingReadout(heading: FieldMap.heading(from: track), live: s?.xy != nil).eraseToAnyView())
                    .padding(.horizontal, 4)
                FieldMap(area: s?.area, home: s?.home, markers: s?.markers ?? [],
                         drone: s?.xy.flatMap { $0.count >= 2 ? SIMD2($0[0], $0[1]) : nil },
                         track: track,
                         objects: (s?.detections ?? []).map {
                             MapObject(id: $0.stableID, label: $0.mapLabel, name: $0.name,
                                       x: $0.x ?? 0, y: $0.y ?? 0, time: $0.time)
                         })
                .overlay {
                    if s == nil {
                        Label("Awaiting telemetry", systemImage: "location.slash")
                            .font(.system(size: 11.5, weight: .medium))
                            .foregroundStyle(Theme.textTertiary)
                            .padding(.horizontal, 10)
                            .frame(height: 26)
                            .background(Theme.panelRaised, in: .rect(cornerRadius: 7))
                            .overlay(RoundedRectangle(cornerRadius: 7).strokeBorder(Theme.hairline))
                    }
                }
            }
            .frame(maxHeight: .infinity, alignment: .top)
        }
        .frame(maxHeight: .infinity)
    }
}

private struct HeadingReadout: View {
    let heading: Double?
    let live: Bool

    var body: some View {
        Text(heading.map { String(format: "HDG %03.0f°", compass($0)) } ?? (live ? "HDG ---" : "ARUCO_MAP"))
            .font(Theme.mono(10.5, .medium))
            .foregroundStyle(Theme.textTertiary)
            .monospacedDigit()
    }

    /// Map angle (from +x, counter-clockwise) → compass-style bearing with +y as 000°.
    private func compass(_ h: Double) -> Double {
        let deg = 90 - h * 180 / .pi
        return (deg.truncatingRemainder(dividingBy: 360) + 360).truncatingRemainder(dividingBy: 360)
    }
}

// MARK: - Telemetry rail

private struct TelemetryRail: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let s = model.mission.status
        let p = s?.position
        let bat = model.battery
        let cell = bat.isFresh ? bat.voltage.map { $0 / 6 } : s?.cellVoltage
        let percent = bat.percent ?? cell.map { BatteryMonitor.percent(cellVoltage: $0) }
        let thermal = s?.fps?["thermal"] ?? s?.fps?["rgb"]
        let fires = s?.counts?.filter { ["fire", "flame", "hotspot"].contains($0.key.lowercased()) }.values.reduce(0, +) ?? 0
        let objects = s?.detections?.count ?? 0
        let plan = PlanInfo(log: s?.log ?? [])
        HStack(spacing: 0) {
            RailCell(title: "Battery", symbol: BatteryLevel.symbol(percent),
                     value: percent.map { String(format: "%.0f", $0) }, unit: "%",
                     footnote: cell.map { String(format: "%.1f V pack · %.2f V/cell", $0 * 6, $0) } ?? "6S pack",
                     tint: BatteryLevel.tint(percent),
                     gauge: percent.map { Gauge(fraction: $0 / 100, tint: BatteryLevel.tint($0)) })
            RailDivider()
            RailCell(title: "Altitude", symbol: "arrow.up.and.down",
                     value: p.map { String(format: "%.2f", $0.z) }, unit: "m",
                     footnote: plan.targetAltitude.map { String(format: "target %.2f m", $0) } ?? "rangefinder + EKF2",
                     gauge: p.map { Gauge(fraction: $0.z / (plan.ceiling ?? 3), tint: Theme.signal,
                                          mark: plan.targetAltitude.map { $0 / (plan.ceiling ?? 3) }) })
            RailDivider()
            RailCell(title: "Position", symbol: "location",
                     value: p.map { String(format: "%.2f %.2f", $0.x, $0.y) }, unit: "m",
                     footnote: "x · y in aruco_map")
            RailDivider()
            RailCell(title: "Thermal", symbol: "speedometer",
                     value: thermal.map { String(format: "%.1f", $0) }, unit: "FPS",
                     footnote: "C4 target ≥ 10 FPS",
                     tint: (thermal ?? 99) < 10 ? Theme.caution : Theme.textPrimary,
                     gauge: thermal.map { Gauge(fraction: $0 / 30, tint: $0 < 10 ? Theme.caution : Theme.textSecondary, mark: 10.0 / 30) })
            RailDivider()
            RailCell(title: "Fires", symbol: "flame",
                     value: s == nil ? nil : "\(fires)", unit: nil,
                     footnote: objects == 1 ? "1 object confirmed" : "\(objects) objects confirmed",
                     tint: fires > 0 ? Theme.accent : Theme.textPrimary)
            RailDivider()
            FlightTimeCell(log: s?.log ?? [], phase: s?.phase ?? "")
        }
        .frame(height: 92)
        .background(Theme.panel, in: .rect(cornerRadius: Theme.radius))
        .overlay(RoundedRectangle(cornerRadius: Theme.radius).strokeBorder(Theme.hairline))
        .animation(.smooth(duration: 0.3), value: s?.pos)
    }

    private func batteryTint(_ v: Double?) -> Color {
        guard let v else { return Theme.textPrimary }
        return v < 3.5 ? Theme.critical : v < 3.65 ? Theme.caution : Theme.textPrimary
    }
}

private struct Gauge {
    var fraction: Double
    var tint: Color
    var mark: Double?
}

private struct RailDivider: View {
    var body: some View { Rectangle().fill(Theme.hairline).frame(width: 1).padding(.vertical, 14) }
}

private struct RailCell: View {
    let title: String
    let symbol: String
    let value: String?
    let unit: String?
    let footnote: String
    var tint: Color = Theme.textPrimary
    var gauge: Gauge?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 6) {
                Image(systemName: symbol)
                    .font(.system(size: 10.5, weight: .medium))
                    .foregroundStyle(Theme.textTertiary)
                    .frame(width: 13)
                Eyebrow(text: title)
                    .lineLimit(1)
            }
            Spacer(minLength: 4)
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text(value ?? "—")
                    .font(Theme.mono(21, .medium))
                    .foregroundStyle(value == nil ? Theme.textTertiary : tint)
                    .monospacedDigit()
                    .contentTransition(.numericText())
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                if let unit, value != nil {
                    Text(unit)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(Theme.textTertiary)
                        .lineLimit(1)
                        .fixedSize()
                }
            }
            Spacer(minLength: 4)
            ZStack(alignment: .leading) {
                if let gauge { GaugeBar(gauge: gauge) } else { Color.clear }
            }
            .frame(height: 3)
            .padding(.bottom, 5)
            Text(footnote)
                .font(.system(size: 10.5))
                .foregroundStyle(Theme.textTertiary)
                .lineLimit(1)
                .truncationMode(.tail)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }
}

private struct GaugeBar: View {
    let gauge: Gauge

    var body: some View {
        GeometryReader { geo in
            let f = min(max(gauge.fraction, 0), 1)
            ZStack(alignment: .leading) {
                Capsule().fill(Color.white.opacity(0.07))
                Capsule().fill(gauge.tint.opacity(0.85)).frame(width: max(2, geo.size.width * f))
                if let m = gauge.mark {
                    Rectangle().fill(Theme.textSecondary).frame(width: 1, height: 7)
                        .offset(x: geo.size.width * min(max(m, 0), 1) - 0.5)
                }
            }
            .animation(.smooth(duration: 0.4), value: f)
        }
    }
}

/// Flight time from the mission log: TAKEOFF → LAND/REPORT/DONE (drone clock), or → now while airborne.
private struct FlightTimeCell: View {
    let log: [String]
    let phase: String

    var body: some View {
        let t = FlightClock(log: log, phase: phase)
        RailCell(title: "Flight time", symbol: "timer",
                 value: t.seconds.map(Self.format), unit: nil,
                 footnote: t.seconds == nil ? "starts at takeoff" : t.running ? "since takeoff" : "takeoff → landing")
    }

    static func format(_ s: Int) -> String { String(format: "%d:%02d", s / 60, s % 60) }
}

private struct FlightClock {
    var seconds: Int?
    var running = false

    init(log: [String], phase: String) {
        var takeoff: Int?, end: Int?, latest: Int?
        for line in log {
            guard let t = LogLine.seconds(line) else { continue }
            latest = t
            if line.contains("[phase] TAKEOFF") { takeoff = t; end = nil }
            if takeoff != nil, end == nil,
               line.contains("[phase] LAND") || line.contains("[phase] REPORT") || line.contains("[phase] DONE") || line.contains("[phase] STOPPED") {
                end = t
            }
        }
        guard let takeoff else { return }
        if let end {
            seconds = Self.diff(end, takeoff)
            return
        }
        running = MissionPhase.isAirborne(phase)
        // The drone clock may not match this Mac (no RTC/NTP in the hall). Use the local clock only if it agrees
        // with the latest log line; otherwise fall back to the latest log time.
        let now = Calendar.current.dateComponents([.hour, .minute, .second], from: .now)
        let local = (now.hour ?? 0) * 3600 + (now.minute ?? 0) * 60 + (now.second ?? 0)
        let ref = latest.map { Self.diff(local, $0) < 900 ? local : $0 } ?? local
        seconds = Self.diff(ref, takeoff)
    }

    private static func diff(_ a: Int, _ b: Int) -> Int { ((a - b) % 86_400 + 86_400) % 86_400 }
}

/// Values the mission writes into its log once at the start.
private struct PlanInfo {
    var targetAltitude: Double?
    var ceiling: Double?

    init(log: [String]) {
        for line in log.prefix(20) {
            if line.contains("[plan]"), let r = line.range(of: "at z=") {
                targetAltitude = Double(line[r.upperBound...].prefix { $0.isNumber || $0 == "." })
            }
            if line.contains("[safety]"), let r = line.range(of: "max altitude ") {
                ceiling = Double(line[r.upperBound...].prefix { $0.isNumber || $0 == "." })
            }
        }
    }
}

// MARK: - Detections

private struct DetectionsCard: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let dets = (model.mission.status?.detections ?? []).sorted { ($0.id ?? 0) > ($1.id ?? 0) }
        GlassCard(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader(title: "Confirmed objects", symbol: "scope",
                           trailing: Text("\(dets.count)").font(Theme.mono(11, .semibold))
                               .foregroundStyle(dets.isEmpty ? Theme.textTertiary : Theme.accent)
                               .contentTransition(.numericText()).eraseToAnyView())
                    .padding(.horizontal, 16)
                    .padding(.top, 12)
                    .padding(.bottom, 8)
                DetectionColumns(header: true)
                    .padding(.horizontal, 16)
                    .frame(height: 22)
                Rectangle().fill(Theme.hairline).frame(height: 1)
                if dets.isEmpty {
                    VStack(spacing: 6) {
                        Image(systemName: "flame").font(.system(size: 18, weight: .light)).foregroundStyle(Theme.textTertiary)
                        Text("No objects confirmed yet").font(.system(size: 12.5, weight: .medium)).foregroundStyle(Theme.textSecondary)
                        Text("An object is confirmed after 3 consistent sightings.")
                            .font(.system(size: 11.5)).foregroundStyle(Theme.textTertiary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ScrollView {
                        LazyVStack(spacing: 0) {
                            ForEach(dets, id: \.stableID) { d in
                                DetectionRow(d: d)
                                    .transition(.asymmetric(insertion: .move(edge: .top).combined(with: .opacity), removal: .opacity))
                            }
                        }
                        .padding(.vertical, 4)
                        .animation(.smooth(duration: 0.35), value: dets.map(\.stableID))
                    }
                    .scrollIndicators(.automatic)
                }
            }
            .frame(maxHeight: .infinity, alignment: .top)
        }
        .frame(maxHeight: .infinity)
    }
}

/// Fixed column widths shared by the header and the rows.
private struct DetectionColumns: View {
    var header = false
    var d: MissionDetection?

    var body: some View {
        HStack(spacing: 12) {
            cell(d.map { String(format: "#%d", $0.id ?? 0) } ?? "ID", width: 34, align: .leading, primary: true)
            HStack(spacing: 6) {
                if let d {
                    Image(systemName: Theme.symbol(forObject: d.name))
                        .font(.system(size: 10.5, weight: .semibold))
                        .foregroundStyle(Theme.color(forObject: d.name))
                        .frame(width: 12)
                }
                Text(d?.name.capitalized ?? "CLASS")
                    .font(header ? Theme.mono(9.5, .semibold) : .system(size: 12.5, weight: .medium))
                    .foregroundStyle(header ? Theme.textTertiary : Theme.textPrimary)
                    .lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            cell(d.map { String(format: "%.2f", $0.x ?? .nan) } ?? "X (m)", width: 52, align: .trailing)
            cell(d.map { String(format: "%.2f", $0.y ?? .nan) } ?? "Y (m)", width: 52, align: .trailing)
            cell(d.map { String(format: "%.0f%%", ($0.conf ?? 0) * 100) } ?? "CONF", width: 42, align: .trailing)
            cell(d.map { $0.time ?? "—" } ?? "TIME", width: 62, align: .trailing)
        }
    }

    private func cell(_ text: String, width: CGFloat, align: Alignment, primary: Bool = false) -> some View {
        Text(text)
            .font(header ? Theme.mono(9.5, .semibold) : Theme.mono(11.5, primary ? .semibold : .regular))
            .tracking(header ? 0.4 : 0)
            .foregroundStyle(header ? Theme.textTertiary : primary ? Theme.textPrimary : Theme.textSecondary)
            .monospacedDigit()
            .lineLimit(1)
            .minimumScaleFactor(0.8)
            .frame(width: width, alignment: align)
    }
}

private struct DetectionRow: View {
    let d: MissionDetection
    @State private var hover = false

    var body: some View {
        DetectionColumns(d: d)
            .padding(.horizontal, 10)
            .frame(height: 30)
            .background(Color.white.opacity(hover ? 0.045 : 0), in: .rect(cornerRadius: 6))
            .padding(.horizontal, 6)
            .onHover { hover = $0 }
            .animation(.easeOut(duration: 0.12), value: hover)
            .accessibilityElement(children: .combine)
    }
}

// MARK: - Altitude

private struct AltitudeCard: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let m = model.mission
        let h = m.history
        let plan = PlanInfo(log: m.status?.log ?? [])
        GlassCard(padding: 16) {
            VStack(alignment: .leading, spacing: 10) {
                CardHeader(title: "Altitude", symbol: "chart.line.uptrend.xyaxis",
                           trailing: Text(h.last.map { String(format: "%.2f m", $0.altitude) } ?? "—")
                               .font(Theme.mono(11, .medium)).foregroundStyle(Theme.textSecondary)
                               .contentTransition(.numericText()).eraseToAnyView())
                if h.count < 2 {
                    VStack(spacing: 6) {
                        Image(systemName: "chart.xyaxis.line").font(.system(size: 18, weight: .light)).foregroundStyle(Theme.textTertiary)
                        Text("No altitude data yet").font(.system(size: 12.5, weight: .medium)).foregroundStyle(Theme.textSecondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    AltitudeChart(samples: h, target: plan.targetAltitude, ceiling: plan.ceiling)
                }
            }
            .frame(maxHeight: .infinity, alignment: .top)
        }
        .frame(maxHeight: .infinity)
    }
}

private struct AltitudeChart: View {
    let samples: [TelemetrySample]
    let target: Double?
    let ceiling: Double?

    var body: some View {
        let t0 = samples.first?.time ?? .now
        let points = samples.map { (t: $0.time.timeIntervalSince(t0), z: $0.altitude) }
        let tMax = max(60, points.last?.t ?? 0)
        let top = max(ceiling ?? 2, points.map(\.z).max() ?? 1) + 0.3
        Chart {
            ForEach(points, id: \.t) { p in
                AreaMark(x: .value("t", p.t), y: .value("Altitude", p.z))
                    .foregroundStyle(LinearGradient(colors: [Theme.signal.opacity(0.25), Theme.signal.opacity(0)], startPoint: .top, endPoint: .bottom))
                    .interpolationMethod(.monotone)
                LineMark(x: .value("t", p.t), y: .value("Altitude", p.z))
                    .foregroundStyle(Theme.signal)
                    .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
                    .interpolationMethod(.monotone)
            }
            if let target {
                RuleMark(y: .value("Target", target))
                    .foregroundStyle(Theme.textSecondary.opacity(0.6))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                    .annotation(position: .top, alignment: .leading, spacing: 2) {
                        ruleLabel(String(format: "TARGET %.1f m", target), color: Theme.textTertiary)
                    }
            }
            if let ceiling {
                RuleMark(y: .value("Ceiling", ceiling))
                    .foregroundStyle(Theme.critical.opacity(0.5))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                    .annotation(position: .bottom, alignment: .leading, spacing: 2) {
                        ruleLabel(String(format: "GEOFENCE %.1f m", ceiling), color: Theme.critical.opacity(0.8))
                    }
            }
        }
        .chartXScale(domain: 0...tMax)
        .chartYScale(domain: 0...top)
        .chartYAxis {
            AxisMarks(position: .leading, values: .automatic(desiredCount: 4)) { v in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 1, dash: [2, 3])).foregroundStyle(Color.white.opacity(0.06))
                AxisValueLabel {
                    if let z = v.as(Double.self) { Text(String(format: "%.1f", z)).font(Theme.mono(10)).foregroundStyle(Theme.textTertiary) }
                }
            }
        }
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 5)) { v in
                AxisValueLabel {
                    if let t = v.as(Double.self) {
                        Text(String(format: "%d:%02d", Int(t) / 60, Int(t) % 60)).font(Theme.mono(10)).foregroundStyle(Theme.textTertiary)
                    }
                }
            }
        }
        .chartPlotStyle { $0.clipped() }
    }

    private func ruleLabel(_ s: String, color: Color) -> some View {
        Text(s).font(Theme.mono(9, .medium)).foregroundStyle(color).padding(.leading, 4)
    }
}

// MARK: - Log

private struct LogLine: Identifiable {
    /// Content + occurrence index: unchanged when lines are appended or the 80-line window drops old ones.
    let id: String
    let time: String
    let tag: String
    let message: String
    let kind: Kind

    enum Kind { case alarm, safety, phase, normal }

    init(_ raw: String, occurrence: Int) {
        id = "\(occurrence)|\(raw)"
        var rest = Substring(raw)
        if Self.seconds(raw) != nil {
            time = String(raw.prefix(8))
            rest = rest.dropFirst(8).drop { $0 == " " }
        } else {
            time = ""
        }
        if rest.hasPrefix("["), let close = rest.firstIndex(of: "]") {
            tag = String(rest[rest.index(after: rest.startIndex)..<close])
            message = String(rest[rest.index(after: close)...]).trimmingCharacters(in: .whitespaces)
        } else {
            tag = ""
            message = String(rest)
        }
        let t = tag.lowercased()
        if t == "alarm" || raw.contains("CONFIRMED") { kind = .alarm }
        else if t == "safety" || t == "error" || raw.contains("ABORT") { kind = .safety }
        else if t == "phase" { kind = .phase }
        else { kind = .normal }
    }

    /// "HH:MM:SS ..." → seconds of day.
    static func seconds(_ line: String) -> Int? {
        let p = line.prefix(8)
        guard p.count == 8 else { return nil }
        let parts = p.split(separator: ":")
        guard parts.count == 3, let h = Int(parts[0]), let m = Int(parts[1]), let s = Int(parts[2]) else { return nil }
        return h * 3600 + m * 60 + s
    }

    static func parse(_ lines: [String]) -> [LogLine] {
        var seen: [String: Int] = [:]
        return lines.map { raw in
            let n = seen[raw, default: 0]
            seen[raw] = n + 1
            return LogLine(raw, occurrence: n)
        }
    }
}

private struct MissionLogCard: View {
    @Environment(AppModel.self) private var model
    @State private var eventsOnly = false

    var body: some View {
        let all = LogLine.parse(model.mission.status?.log ?? [])
        let lines = eventsOnly ? all.filter { $0.kind != .normal } : all
        GlassCard(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader(title: "Mission log", symbol: "text.alignleft", trailing: filter.eraseToAnyView())
                    .padding(.horizontal, 16)
                    .padding(.top, 10)
                    .padding(.bottom, 8)
                Rectangle().fill(Theme.hairline).frame(height: 1)
                if lines.isEmpty {
                    Text(all.isEmpty ? "The log fills in once the mission is running." : "No events yet.")
                        .font(.system(size: 12))
                        .foregroundStyle(Theme.textTertiary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 0) {
                            ForEach(lines) { LogRow(line: $0) }
                        }
                        .padding(.vertical, 6)
                    }
                    .defaultScrollAnchor(.bottom)
                    .defaultScrollAnchor(.bottom, for: .sizeChanges)
                }
            }
        }
        .frame(height: 220)
    }

    private var filter: some View {
        Picker("Filter", selection: $eventsOnly) {
            Text("All").tag(false)
            Text("Events").tag(true)
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .controlSize(.small)
        .fixedSize()
    }
}

private struct LogRow: View {
    let line: LogLine
    @State private var hover = false

    var body: some View {
        let color: Color = switch line.kind {
        case .alarm: Theme.accent
        case .safety: Theme.critical
        case .phase: Theme.textPrimary
        case .normal: Theme.textSecondary
        }
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(line.time)
                .foregroundStyle(Theme.textTertiary)
                .frame(width: 58, alignment: .leading)
            Text(line.tag.uppercased())
                .foregroundStyle(line.kind == .alarm || line.kind == .safety ? color : Theme.textTertiary)
                .frame(width: 72, alignment: .leading)
                .lineLimit(1)
            Text(line.message)
                .foregroundStyle(color)
                .fontWeight(line.kind == .phase ? .semibold : .regular)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
        }
        .font(Theme.mono(11))
        .padding(.horizontal, 10)
        .padding(.vertical, 2.5)
        .background(Color.white.opacity(hover ? 0.035 : 0), in: .rect(cornerRadius: 4))
        .padding(.horizontal, 6)
        .onHover { hover = $0 }
    }
}
