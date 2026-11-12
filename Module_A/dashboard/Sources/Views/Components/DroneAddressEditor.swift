import SwiftUI

/// Popover: type any drone address (IP or host name), connect, and see what answers there.
/// Reachable from the toolbar status field and the link box at the bottom of the sidebar.
struct DroneAddressEditor: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var draft = ""
    @State private var checks: [Check] = []
    @State private var checking = false
    @FocusState private var focused: Bool

    struct Check: Identifiable {
        let id: String
        let port: Int
        var open: Bool?
        let closedHint: String
    }

    private var cleaned: String { DashboardSettings.cleanHost(draft) }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Drone address")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Theme.textPrimary)

            HStack(spacing: 8) {
                TextField("Address", text: $draft, prompt: Text("IP or host name, e.g. 10.115.4.20"))
                    .labelsHidden()
                    .textFieldStyle(.roundedBorder)
                    .font(Theme.mono(13))
                    .autocorrectionDisabled()
                    .focused($focused)
                    .onSubmit(connect)
                Button("Connect", action: connect)
                    .buttonStyle(.primary)
                    .disabled(cleaned.isEmpty || checking)
                    .keyboardShortcut(.defaultAction)
            }

            HStack(spacing: 6) {
                Text("Quick fill").font(.system(size: 11)).foregroundStyle(Theme.textTertiary)
                ForEach(presets, id: \.self) { host in
                    Button(host) { draft = host; connect() }
                        .buttonStyle(.quiet)
                        .font(Theme.mono(11))
                }
            }

            HStack(spacing: 8) {
                Button {
                    Task { await search() }
                } label: {
                    Label("Find drone on this Wi-Fi", systemImage: "dot.radiowaves.left.and.right")
                }
                .buttonStyle(.quiet)
                .disabled(model.droneSearching)
                if let p = model.droneSearchProgress {
                    ProgressView().controlSize(.mini)
                    Text(p.total > 0 ? "checked \(p.done) of \(p.total)" : "starting")
                        .font(Theme.mono(11)).foregroundStyle(Theme.textTertiary)
                }
            }
            if let found = model.droneSearchResult, !model.droneSearching {
                if found.isEmpty {
                    Text("No drone found on this Wi-Fi. Is the drone switched on and on the same network as this Mac? A VPN can hide local addresses; switch it off. Or use the drone's own hotspot (10.42.0.1).")
                        .font(.system(size: 11)).foregroundStyle(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    HStack(spacing: 6) {
                        Text(found.count == 1 ? "Drone found at" : "Drones found:")
                            .font(.system(size: 11)).foregroundStyle(Theme.textSecondary)
                        ForEach(found, id: \.self) { host in
                            Button(host) { draft = host; connect() }
                                .buttonStyle(.quiet)
                                .font(Theme.mono(11))
                        }
                    }
                }
            }

            if !checks.isEmpty {
                Divider().overlay(Theme.hairline)
                VStack(alignment: .leading, spacing: 7) {
                    ForEach(checks) { c in
                        HStack(spacing: 8) {
                            Group {
                                if let open = c.open {
                                    Image(systemName: open ? "checkmark.circle.fill" : "xmark.circle.fill")
                                        .foregroundStyle(open ? Theme.ok : Theme.critical)
                                } else {
                                    ProgressView().controlSize(.mini)
                                }
                            }
                            .frame(width: 16)
                            Text(c.id).font(.system(size: 12)).foregroundStyle(Theme.textPrimary)
                            Text(":\(String(c.port))").font(Theme.mono(11)).foregroundStyle(Theme.textTertiary)
                            Spacer(minLength: 8)
                            Text(c.open == nil ? "checking" : (c.open == true ? "answers" : c.closedHint))
                                .font(.system(size: 11))
                                .foregroundStyle(Theme.textSecondary)
                        }
                    }
                }
                if let verdict {
                    Text(verdict)
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .padding(16)
        .frame(width: 400)
        .onAppear {
            draft = model.settings.droneHost
            focused = true
        }
    }

    /// The drone's own hotspot, plus the last addresses that were used.
    private var presets: [String] {
        var out = ["10.42.0.1"]
        for h in model.settings.recentHosts where !out.contains(h) { out.append(h) }
        return Array(out.prefix(4))
    }

    private var verdict: String? {
        guard !checking, checks.allSatisfy({ $0.open != nil }) else { return nil }
        let ssh = checks.first { $0.id == "SSH" }?.open == true
        let mission = checks.first { $0.id == "Mission UI" }?.open == true
        if checks.allSatisfy({ $0.open == false }) {
            return "Nothing answers at \(model.settings.droneHost). Check the address, that this Mac and the drone are on the same Wi-Fi, and that a VPN is not blocking local addresses."
        }
        if mission { return "Mission is running. The live view is connected." }
        if ssh { return "Drone found. The live view shows Offline until a mission is started on the drone; Flight Tests work now." }
        return "Something answers here, but SSH does not. Is this the drone's address?"
    }

    private func connect() {
        let host = cleaned
        guard !host.isEmpty else { return }
        draft = host
        model.connectToDrone(host: host)
        let s = model.settings
        checks = [Check(id: "SSH", port: 22, closedHint: "no answer"),
                  Check(id: "Camera stream", port: s.videoPort, closedHint: "no answer"),
                  Check(id: "Mission UI", port: s.missionPort, closedHint: "mission not running")]
        checking = true
        Task {
            await withTaskGroup(of: (String, Bool).self) { group in
                for c in checks {
                    group.addTask { (c.id, await PortProbe.isOpen(host: host, port: c.port)) }
                }
                for await (id, open) in group {
                    if let i = checks.firstIndex(where: { $0.id == id }) { checks[i].open = open }
                }
            }
            checking = false
            // nothing at this address: the drone probably got a new one from the Wi-Fi -> look for it
            if checks.allSatisfy({ $0.open == false }) { await search() }
        }
    }

    /// findDrone switches the app to the drone when the saved address is not one it found; then re-run the checks there.
    private func search() async {
        let before = model.settings.droneHost
        await model.findDrone()
        if model.settings.droneHost != before {
            draft = model.settings.droneHost
            connect()
        }
    }
}
