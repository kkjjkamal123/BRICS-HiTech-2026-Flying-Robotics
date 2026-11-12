import SwiftUI

struct FlightTestsView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let link = DroneLink(settings: model.settings, console: model.console)
        Page(section: .flightTests, trailing: DroneActions(link: link).eraseToAnyView()) {
            SafetyBanner()
            Grid(horizontalSpacing: Theme.spacing, verticalSpacing: Theme.spacing) {
                GridRow {
                    TestCard(test: .motorRamp, link: link)
                    TestCard(test: .hover, link: link)
                }
                GridRow {
                    TestCard(test: .roam, link: link)
                    TestCard(test: .mission, link: link)
                }
            }
            ConsolePanel(height: 300)
        }
    }
}

// MARK: - Header actions

private struct DroneActions: View {
    let link: DroneLink
    @Environment(AppModel.self) private var model

    var body: some View {
        HStack(spacing: 8) {
            Menu {
                Button("Test connection", systemImage: "bolt.horizontal") { link.testConnection() }
                Divider()
                Button("Copy flight scripts to drone", systemImage: "square.and.arrow.up") {
                    link.syncScripts(toolkit: model.settings.toolkitRoot)
                }
                Button("Deploy full toolkit", systemImage: "shippingbox") { link.deployToolkit(toolkit: model.settings.toolkitRoot) }
                Button("Sync drone clock", systemImage: "clock.arrow.2.circlepath") { link.syncClock() }
                Divider()
                Button("Copy flight logs back", systemImage: "square.and.arrow.down") {
                    link.fetchResults(toolkit: model.settings.toolkitRoot)
                }
            } label: {
                MenuLabel(title: "Drone", symbol: "antenna.radiowaves.left.and.right")
            }
            .menuStyle(.button)
            .buttonStyle(.plain)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Drone connection, deployment and logs (\(model.settings.sshTarget))")

            Button {
                link.copyAndRunScript("ArUco scan (manual flight)", toolkit: model.settings.toolkitRoot, script: "aruco_scan.py", args: [])
            } label: {
                Label("ArUco scan", systemImage: "qrcode.viewfinder")
            }
            .buttonStyle(.secondaryLarge)
            .fixedSize()
            .help("You fly with the RC. This only watches the camera and lists every ArUco marker it sees. It never arms or moves the drone. Stop in the console prints the summary.")

            Button { link.landNow() } label: {
                Label("LAND NOW", systemImage: "arrow.down.to.line")
                    .font(Theme.mono(12.5, .bold))
                    .tracking(0.6)
            }
            .buttonStyle(.primary(Theme.critical, large: true))
            .fixedSize()
            .keyboardShortcut("l", modifiers: [.command, .shift])
            .help("Calls the TECHNIC /land service directly - works even if a script hangs (⇧⌘L)")
        }
    }
}

/// Menu label drawn to match `.secondaryLarge` (menus ignore custom button styles).
private struct MenuLabel: View {
    let title: String
    let symbol: String
    @State private var hover = false

    var body: some View {
        HStack(spacing: 7) {
            Image(systemName: symbol).font(.system(size: 12, weight: .medium))
            Text(title)
            Image(systemName: "chevron.down")
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(Theme.textTertiary)
        }
        .font(.system(size: 13.5, weight: .medium))
        .foregroundStyle(Theme.textPrimary)
        .padding(.horizontal, 14)
        .frame(height: 34)
        .background(Color.white.opacity(hover ? 0.06 : 0.025), in: .rect(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(hover ? Theme.hairlineStrong : Theme.hairline))
        .contentShape(.rect)
        .onHover { hover = $0 }
        .animation(.easeOut(duration: 0.15), value: hover)
    }
}

// MARK: - Safety banner

private struct SafetyBanner: View {
    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Theme.caution)
            Text("Before every flight")
                .font(.system(size: 12.5, weight: .semibold))
                .foregroundStyle(Theme.textPrimary)
                .fixedSize()
            HStack(spacing: 18) {
                item("RC transmitter on")
                item("Kill switch · CH 8")
                item("People ≥ 3 m back")
            }
            .fixedSize()
            Spacer(minLength: 12)
            ViewThatFits(in: .horizontal) {
                Text("Stop always lands the drone - it never cuts the motors in the air.")
                Text("Stop always lands - never cuts motors.")
                EmptyView()
            }
            .font(.system(size: 12))
            .foregroundStyle(Theme.textTertiary)
            .lineLimit(1)
        }
        .padding(.horizontal, 16)
        .frame(height: 40)
        .background(Theme.panel, in: .rect(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Theme.hairline))
        .overlay(alignment: .leading) {
            UnevenRoundedRectangle(topLeadingRadius: 10, bottomLeadingRadius: 10)
                .fill(Theme.caution.opacity(0.85))
                .frame(width: 2.5)
        }
        .accessibilityElement(children: .combine)
    }

    private func item(_ text: String) -> some View {
        HStack(spacing: 6) {
            Circle().fill(Theme.textTertiary).frame(width: 3.5, height: 3.5)
            Text(text)
        }
        .font(.system(size: 12.5))
        .foregroundStyle(Theme.textSecondary)
    }
}

// MARK: - Test definitions

enum FlightTest: String, Identifiable {
    case motorRamp, hover, roam, mission
    var id: String { rawValue }

    var title: String {
        switch self {
        case .motorRamp: "Motor ramp"
        case .hover: "Hover"
        case .roam: "ArUco lawn-mower"
        case .mission: "Case 1 mission"
        }
    }
    var summary: String {
        switch self {
        case .motorRamp: "Props off. Arm, ramp to peak throttle, slow ramp down, disarm."
        case .hover: "Take off, hold position, slow descent, land. Proves module M1."
        case .roam: "Lock start on the marker map, sweep the field line by line, return, land."
        case .mission: "Survey, thermal detection, inspection hover, return and report."
        }
    }
    var tag: String {
        switch self {
        case .motorRamp: "Bench"
        case .hover, .roam: "Flight"
        case .mission: "Mission"
        }
    }
    var script: String {
        switch self {
        case .motorRamp: "motor_ramp_test.py"
        case .hover: "hover_test.py"
        case .roam: "aruco_roam_test.py"
        case .mission: "tools/run_mission.sh"
        }
    }
    var runTitle: String {
        switch self {
        case .motorRamp: "Arm & ramp"
        case .hover, .roam: "Fly"
        case .mission: "Run mission"
        }
    }
    var runSymbol: String {
        switch self {
        case .motorRamp: "bolt.fill"
        case .hover, .roam: "airplane.departure"
        case .mission: "play.fill"
        }
    }
}

// MARK: - Test card

private struct TestCard: View {
    let test: FlightTest
    let link: DroneLink
    @Environment(AppModel.self) private var model

    @State private var throttle = 50.0
    @State private var altitude = 1.5
    @State private var hold = 5.0
    @State private var roamTime = 30.0
    @State private var radius = 0.75      // roam card: lawn-mower line spacing, m
    @State private var confirmRun = false

    var body: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: 0) {
                header
                Text(test.summary)
                    .font(.system(size: 12.5))
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .help(test.summary)
                    .padding(.top, 6)
                Rectangle().fill(Theme.hairline).frame(height: 1).padding(.vertical, 14)
                VStack(spacing: 10) { params }
                Spacer(minLength: 14)
                CommandPreview(text: commandPreview)
                    .padding(.bottom, 12)
                actions
            }
            .frame(maxHeight: .infinity, alignment: .top)
        }
        .frame(maxHeight: .infinity)
        .confirmationDialog(confirmTitle, isPresented: $confirmRun, titleVisibility: .visible) {
            Button(confirmButton, role: .destructive) { run(dry: false) }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text(confirmMessage)
        }
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text(test.title)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(Theme.textPrimary)
                .lineLimit(1)
            ParamTag(text: test.tag)
                .alignmentGuide(.firstTextBaseline) { $0[VerticalAlignment.center] + 4 }
            Spacer(minLength: 8)
            Text(test.script)
                .font(Theme.code(11))
                .foregroundStyle(Theme.textTertiary)
                .lineLimit(1)
        }
    }

    @ViewBuilder private var params: some View {
        switch test {
        case .motorRamp:
            ParamSlider(label: "Peak throttle", value: $throttle, range: 10...60, step: 5, format: "%.0f", unit: "%")
            ParamInfoRow(label: "Profile", value: "3 s up · 2 s hold · 10 s down")
        case .hover:
            ParamSlider(label: "Altitude", value: $altitude, range: 0.5...3.0, step: 0.1, format: "%.1f", unit: "m")
            ParamSlider(label: "Hold", value: $hold, range: 2...30, step: 1, format: "%.0f", unit: "s")
        case .roam:
            ParamSlider(label: "Altitude", value: $altitude, range: 1.0...3.0, step: 0.1, format: "%.1f", unit: "m")
            ParamSlider(label: "Line spacing", value: $radius, range: 0.5...1.5, step: 0.25, format: "%.2f", unit: "m")
            ParamInfoRow(label: "Area", value: "marker field minus 0.5 m")
        case .mission:
            let ms = model.missionSettings
            ParamInfoRow(label: "Flight", value: ms.kind == .flameRTH ? "Flame → return home (3 lines)" : "Full Case 1 survey")
            ParamInfoRow(label: "Scan area", value: String(format: "x %.2f…%.2f  y %.2f…%.2f m", ms.area[0], ms.area[2], ms.area[1], ms.area[3]))
            ParamInfoRow(label: "Boundary", value: String(format: "x %.2f…%.2f  y %.2f…%.2f m", ms.fence[0], ms.fence[2], ms.fence[1], ms.fence[3]))
            ParamInfoRow(label: "Height", value: String(format: "alt %.1f m · lines %@%.2f m · %.2f m/s", ms.altitude, ms.spacingAuto ? "auto " : "", ms.effectiveSpacing, ms.speed))
            HStack(spacing: 12) {
                ParamInfoRow(label: "Fire", value: String(format: "≥ %.0f °C", ms.fireC))
                Button("Edit…") { model.showMissionSettings = true }
                    .buttonStyle(.secondary)
                    .fixedSize()
            }
        }
    }

    private var actions: some View {
        HStack(spacing: 10) {
            if test == .mission {
                Button { openOperatorUI() } label: {
                    Label("Operator UI", systemImage: "safari").frame(maxWidth: .infinity)
                }
                .buttonStyle(.secondaryLarge)
                .help("Open http://\(model.settings.droneHost):\(model.settings.missionPort) in the browser")
            } else {
                Button { run(dry: true) } label: {
                    Label("Dry run", systemImage: "checklist").frame(maxWidth: .infinity)
                }
                .buttonStyle(.secondaryLarge)
                .help("Checks sensors, map and battery on the drone - never arms")
            }
            Button { confirmRun = true } label: {
                Label(test.runTitle, systemImage: test.runSymbol).frame(maxWidth: .infinity)
            }
            .buttonStyle(.primaryLarge)
            .disabled(test == .mission && model.droneMissionAirborne || test == .mission && !model.missionSettings.problems(markerField: MissionSettings.Venue.markerField(from: model.mission.status?.markers)).isEmpty)
            .help(test == .motorRamp ? "Arms the motors - props must be removed" : "Flies the real drone after confirmation")
        }
        .lineLimit(1)
    }

    // MARK: confirmation copy

    private var confirmTitle: String {
        switch test {
        case .motorRamp: "Arm the motors with the props removed?"
        case .mission: "Start the Case 1 mission on the real drone?"
        default: "Fly the \(test.title.lowercased()) test on the real drone?"
        }
    }
    private var confirmButton: String { test == .motorRamp ? "Props are off - arm" : "Area clear - fly" }
    private var confirmMessage: String {
        "RC transmitter on, kill switch on channel 8 ready, people at least 3 m back. Stop in the console lands the drone."
    }

    // MARK: commands

    private var scriptArgs: [String] {
        switch test {
        case .motorRamp: ["--max", String(format: "%.2f", throttle / 100)]
        case .hover: ["--alt", String(format: "%.1f", altitude), "--hold", String(Int(hold))]
        case .roam: ["--pattern", "lawnmower", "--alt", String(format: "%.1f", altitude), "--spacing", String(format: "%.2f", radius)]
        case .mission: model.missionSettings.launcherArguments
        }
    }

    private var commandPreview: String {
        ([test == .mission ? "bash" : "python3", test.script] + scriptArgs).joined(separator: " ")
    }

    private func openOperatorUI() {
        if let url = URL(string: "http://\(model.settings.droneHost):\(model.settings.missionPort)") {
            NSWorkspace.shared.open(url)
        }
    }

    private func run(dry: Bool) {
        let mode = dry ? ["--dry-run"] : ["--yes"]
        let suffix = dry ? " (dry)" : ""
        switch test {
        case .motorRamp:
            link.runScript("Motor ramp \(Int(throttle))%" + suffix, script: test.script, args: scriptArgs + mode)
        case .hover:
            link.copyAndRunScript("Hover \(String(format: "%.1f", altitude)) m" + suffix, toolkit: model.settings.toolkitRoot, script: test.script, args: scriptArgs + mode)
        case .roam:
            link.copyAndRunScript("ArUco lawn-mower" + suffix, toolkit: model.settings.toolkitRoot, script: test.script, args: scriptArgs + mode)
        case .mission:
            model.runNewDroneMission()      // same as Mission Control: replaces an older run on the ground, then countdown + take-off
        }
    }
}

// MARK: - Shared rows (also used by SimulationView)

/// Label / slider / mono value row. Fixed label and value columns keep every row aligned across cards.
struct ParamSlider: View {
    let label: String
    @Binding var value: Double
    let range: ClosedRange<Double>
    let step: Double
    let format: String
    var unit: String = ""

    private var snapped: Binding<Double> {
        Binding(get: { value }, set: { raw in
            let v = min(max((raw / step).rounded() * step, range.lowerBound), range.upperBound)
            if v != value { value = v }
        })
    }

    var body: some View {
        HStack(spacing: 12) {
            Text(label)
                .font(.system(size: 12.5))
                .foregroundStyle(Theme.textSecondary)
                .lineLimit(1)
                .frame(width: ParamLayout.labelWidth, alignment: .leading)
            // Continuous slider + snapped binding: same stepping, without the dense macOS tick row.
            Slider(value: snapped, in: range)
                .controlSize(.small)
                .tint(Theme.textSecondary)
                .accessibilityLabel(label)
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(String(format: format, value))
                    .font(Theme.mono(12.5, .medium))
                    .foregroundStyle(Theme.textPrimary)
                    .animation(.snappy(duration: 0.2), value: value)
                Text(unit)
                    .font(Theme.mono(11))
                    .foregroundStyle(Theme.textTertiary)
                    .frame(width: 12, alignment: .leading)
            }
            .monospacedDigit()
            .frame(width: ParamLayout.valueWidth, alignment: .trailing)
        }
        .frame(height: 22)
    }
}

/// Label / mono value row aligned to the `ParamSlider` label column.
struct ParamInfoRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack(spacing: 12) {
            Text(label)
                .font(.system(size: 12.5))
                .foregroundStyle(Theme.textSecondary)
                .lineLimit(1)
                .frame(width: ParamLayout.labelWidth, alignment: .leading)
            Text(value)
                .font(Theme.mono(12))
                .foregroundStyle(Theme.textPrimary)
                .lineLimit(1)
                .truncationMode(.middle)
                .textSelection(.enabled)
            Spacer(minLength: 0)
        }
        .frame(height: 22)
    }
}

enum ParamLayout {
    static let labelWidth: CGFloat = 96
    static let valueWidth: CGFloat = 64
}

/// Small mono category tag (neutral - it labels, it does not signal status).
struct ParamTag: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.system(size: 10, weight: .medium))
            .foregroundStyle(Theme.textSecondary)
            .padding(.horizontal, 5)
            .frame(height: 16)
            .overlay(RoundedRectangle(cornerRadius: 4).strokeBorder(Theme.hairlineStrong))
            .fixedSize()
    }
}

/// The exact command the card will run, in a recessed mono well.
private struct CommandPreview: View {
    let text: String

    var body: some View {
        HStack(spacing: 8) {
            Text("$").foregroundStyle(Theme.textTertiary)
            Text(text)
                .foregroundStyle(Theme.textSecondary)
                .lineLimit(1)
                .truncationMode(.middle)
                .textSelection(.enabled)
            Spacer(minLength: 0)
        }
        .font(Theme.code(11))
        .padding(.horizontal, 10)
        .frame(height: 28)
        .background(Theme.well, in: .rect(cornerRadius: 7))
        .overlay(RoundedRectangle(cornerRadius: 7).strokeBorder(Theme.hairline))
    }
}
