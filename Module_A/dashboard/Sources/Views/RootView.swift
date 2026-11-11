import SwiftUI

struct RootView: View {
    @Environment(AppModel.self) private var model
    @State private var columnVisibility: NavigationSplitViewVisibility = .all

    var body: some View {
        @Bindable var model = model
        NavigationSplitView(columnVisibility: $columnVisibility) {
            Sidebar(selection: $model.section)
                .navigationSplitViewColumnWidth(min: 220, ideal: 236, max: 280)
        } detail: {
            detail
                .id(model.section)
                .transition(.opacity)
                .toolbar { MainToolbar() }
        }
        .animation(.easeInOut(duration: 0.18), value: model.section)
        .overlay(alignment: .top) { DetectionToast() }
        .sheet(isPresented: $model.showMissionSettings) { MissionSettingsSheet().environment(model) }
        .preferredColorScheme(.dark)
        .tint(Theme.accent)
    }

    @ViewBuilder private var detail: some View {
        switch model.section {
        case .overview: OverviewView()
        case .mission: MissionControlView()
        case .flightTests: FlightTestsView()
        case .simulation: SimulationView()
        case .results: ResultsView()
        case .spec: SpecView()
        case .aiModel: AIModelView()
        case .economics: EconomicsView()
        case .documents: DocumentsView()
        }
    }
}

// MARK: - Sidebar

private struct Sidebar: View {
    @Binding var selection: AppSection
    @Environment(AppModel.self) private var model

    var body: some View {
        List(selection: $selection) {
            Brand()
                .listRowSeparator(.hidden)
                .selectionDisabled()
            ForEach(AppSection.Group.allCases) { group in
                Section(group.rawValue) {
                    ForEach(group.sections) { s in
                        NavigationLink(value: s) {
                            Label {
                                HStack(spacing: 6) {
                                    Text(s.title)
                                    Spacer(minLength: 4)
                                    trailing(for: s)
                                }
                            } icon: {
                                Image(systemName: s.symbol)
                                    .foregroundStyle(selection == s ? Theme.accent : Theme.textSecondary)
                            }
                        }
                    }
                }
            }
        }
        .listStyle(.sidebar)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            LinkFooter().padding(.horizontal, 10).padding(.bottom, 10)
        }
    }

    @ViewBuilder private func trailing(for s: AppSection) -> some View {
        switch s {
        case .mission where model.mission.connected:
            LiveDot(color: Theme.ok, live: true)
        case .simulation where model.simulationRunning:
            LiveDot(color: Theme.accent, live: true)
        case .spec:
            Text("\(model.spec.passCount)/7").font(Theme.mono(10.5)).foregroundStyle(Theme.textTertiary)
        default:
            EmptyView()
        }
    }
}

private struct Brand: View {
    var body: some View {
        HStack(spacing: 10) {
            Image(nsImage: NSApp.applicationIconImage)
                .resizable()
                .interpolation(.high)
                .frame(width: 32, height: 32)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 1) {
                Text("BRICS Dashboard")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Text("Aerial Robotics · Case 1")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.textSecondary)
            }
        }
        .padding(.top, 2)
        .padding(.bottom, 8)
    }
}

private struct LinkFooter: View {
    @Environment(AppModel.self) private var model
    @State private var editing = false

    var body: some View {
        Button { editing = true } label: { content }
            .buttonStyle(.plain)
            .help("Change the drone address")
            .popover(isPresented: $editing, arrowEdge: .trailing) {
                DroneAddressEditor().environment(model)
            }
    }

    private var content: some View {
        let m = model.mission
        return HStack(spacing: 9) {
            LiveDot(color: m.connected ? Theme.ok : (m.droneReachable ? Theme.signal : Theme.textTertiary), live: m.connected, size: 7)
            VStack(alignment: .leading, spacing: 1) {
                Text(model.settings.missionSource == .drone ? "TECHNIC 6S" : "Simulator")
                    .font(.system(size: 11.5, weight: .semibold))
                Text(m.connected ? m.endpoint.label : (m.droneReachable ? "online · \(m.endpoint.host)" : "no link · \(m.endpoint.label)"))
                    .font(Theme.mono(10))
                    .foregroundStyle(Theme.textTertiary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            Spacer(minLength: 0)
            BatteryBadge()
            Image(systemName: "pencil")
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(Theme.textTertiary)
        }
        .padding(.horizontal, 11)
        .padding(.vertical, 9)
        .contentShape(.rect(cornerRadius: 10))
        .background(Color.white.opacity(0.04), in: .rect(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Theme.hairline))
    }
}

// MARK: - Toolbar

private struct MainToolbar: ToolbarContent {
    @Environment(AppModel.self) private var model

    var body: some ToolbarContent {
        ToolbarItem(placement: .principal) {
            ActivityField()
        }
        ToolbarItemGroup(placement: .primaryAction) {
            Button("Return Home", systemImage: "house") { model.mission.send(.returnHome) }
                .help("Return home and land  ⇧⌘H")
                .disabled(!model.mission.connected)
            Button("Land", systemImage: "airplane.arrival") { model.mission.send(.land) }
                .help("Land where it is now  ⇧⌘L")
                .disabled(!model.mission.connected)
        }
    }
}

/// Xcode-style activity field in the centre of the toolbar: link state, source, phase, endpoint.
/// Clicking it switches the live source (drone / simulator).
private struct ActivityField: View {
    @Environment(AppModel.self) private var model
    @State private var editingAddress = false

    var body: some View {
        let m = model.mission
        let source = model.settings.missionSource
        Menu {
            Picker("Live source", selection: Binding(
                get: { model.settings.missionSource },
                set: { model.settings.missionSource = $0; model.applyMissionSource() })) {
                Label("TECHNIC 6S drone", systemImage: "airplane").tag(MissionSource.drone)
                Label("Local simulator", systemImage: "cube.transparent").tag(MissionSource.simulator)
            }
            .pickerStyle(.inline)
            Divider()
            Button("Drone Address…", systemImage: "network") { editingAddress = true }
            Button("Open Mission Control", systemImage: "scope") { model.section = .mission }
        } label: {
            HStack(spacing: 8) {
                Image(systemName: source == .drone ? "airplane" : "cube.transparent")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Theme.textSecondary)
                Text(source == .drone ? "TECHNIC 6S" : "Simulator")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Rectangle().fill(Theme.hairlineStrong).frame(width: 1, height: 12)
                LiveDot(color: m.connected ? Theme.ok : (m.droneReachable ? Theme.signal : Theme.textTertiary), live: m.connected, size: 6)
                Text(m.connected ? m.phase.capitalized : (m.droneReachable ? "Online · no mission" : "Offline"))
                    .font(.system(size: 12))
                    .foregroundStyle(m.connected ? Theme.color(forPhase: m.phase) : (m.droneReachable ? Theme.signal : Theme.textSecondary))
                    .contentTransition(.interpolate)
                Text(m.endpoint.label)
                    .font(Theme.mono(10.5))
                    .foregroundStyle(Theme.textTertiary)
                if model.battery.percent != nil {
                    Rectangle().fill(Theme.hairlineStrong).frame(width: 1, height: 12)
                    BatteryBadge(large: true)
                }
            }
            .padding(.horizontal, 10)
            .animation(.smooth(duration: 0.25), value: m.connected)
            .animation(.smooth(duration: 0.25), value: m.phase)
        }
        .menuStyle(.button)
        .menuIndicator(.hidden)
        .buttonStyle(.plain)
        .fixedSize()
        .help("Live source and link status - click to switch drone / simulator or change the drone address")
        .popover(isPresented: $editingAddress, arrowEdge: .bottom) {
            DroneAddressEditor().environment(model)
        }
    }
}

// MARK: - Detection toast (glass: it floats above content)

private struct DetectionToast: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ZStack {
            if let d = model.mission.newDetectionAlert {
                HStack(spacing: 12) {
                    Image(systemName: Theme.symbol(forObject: d.name))
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(Theme.color(forObject: d.name))
                        .frame(width: 30, height: 30)
                        .background(Theme.color(forObject: d.name).opacity(0.15), in: .rect(cornerRadius: 8))
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(d.name.capitalized) #\(d.id ?? 0) confirmed")
                            .font(.system(size: 13, weight: .semibold))
                        Text(String(format: "x %.2f  y %.2f m  ·  %.0f%%  ·  %@", d.x ?? .nan, d.y ?? .nan, (d.conf ?? 0) * 100, d.time ?? ""))
                            .font(Theme.mono(11))
                            .foregroundStyle(Theme.textSecondary)
                    }
                    Button { model.mission.dismissAlert() } label: { Image(systemName: "xmark").font(.system(size: 10, weight: .bold)) }
                        .buttonStyle(.quiet)
                        .help("Dismiss")
                }
                .padding(.leading, 10)
                .padding(.trailing, 8)
                .padding(.vertical, 8)
                .glassEffect(.regular, in: .rect(cornerRadius: 14))
                .padding(.top, 12)
                .transition(.move(edge: .top).combined(with: .opacity))
                .task(id: d.stableID) {
                    try? await Task.sleep(for: .seconds(5))
                    model.mission.dismissAlert()
                }
            }
        }
        .animation(.spring(duration: 0.4, bounce: 0.2), value: model.mission.newDetectionAlert?.stableID)
    }
}
