import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var model

    private var toolkitFound: Bool {
        FileManager.default.fileExists(atPath: model.settings.toolkitRoot.appending(path: "drone/mission_base.py").path(percentEncoded: false))
    }

    var body: some View {
        @Bindable var settings = model.settings
        Form {
            Section {
                TextField("Address", text: $settings.droneHost, prompt: Text("10.42.0.1"))
                    .font(Theme.mono(12))
                    .autocorrectionDisabled()
                    .onSubmit { model.connectToDrone(host: settings.droneHost) }
                PortRow(title: "Mission UI port", value: $settings.missionPort)
                PortRow(title: "Camera stream port", value: $settings.videoPort)
            } header: {
                Text("Drone")
            } footer: {
                footnote("Any IP or host name works. The drone's own hotspot is 10.42.0.1; on another Wi-Fi, use the address the drone got there. You can also change it from the link box at the bottom of the sidebar.")
            }

            Section {
                TextField("SSH user", text: $settings.sshUser, prompt: Text("orangepi"))
                    .font(Theme.mono(12))
                SecureField("Password", text: $settings.sshPassword)
                LabeledContent("SSH key") {
                    HStack(spacing: 8) {
                        Button("Test connection", action: test)
                            .buttonStyle(.secondary)
                        Button("Pair with drone", action: pair)
                            .buttonStyle(.primary)
                            .disabled(settings.sshPassword.isEmpty)
                    }
                    .fixedSize()
                }
            } header: {
                Text("Drone login")
            } footer: {
                footnote("The password is used automatically for every drone command (TECHNIC default: orangepi). Pairing is optional: it installs this Mac's SSH key on the drone.")
            }

            Section("Simulator") {
                PortRow(title: "Simulator UI port", value: $settings.simulatorPort)
            }

            Section("Toolkit") {
                LabeledContent("Folder") {
                    HStack(spacing: 8) {
                        TextField("Folder", text: $settings.toolkitPath, prompt: Text("/path/to/brics_toolkit"))
                            .labelsHidden()
                            .font(Theme.mono(11.5))
                            .truncationMode(.head)
                        Button("Choose…", action: chooseFolder)
                            .buttonStyle(.secondary)
                            .fixedSize()
                    }
                }
                LabeledContent("Status") {
                    Label(toolkitFound ? "Toolkit found" : "drone/mission_base.py not found in this folder",
                          systemImage: toolkitFound ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                        .font(.system(size: 12))
                        .foregroundStyle(toolkitFound ? Theme.ok : Theme.caution)
                        .lineLimit(1)
                }
            }
        }
        .formStyle(.grouped)
        .scrollContentBackground(.hidden)
        .background(Theme.canvas)
        .preferredColorScheme(.dark)
        .tint(Theme.accent)
        .onChange(of: settings.droneHost) { model.applyMissionSource() }
        .onChange(of: settings.missionPort) { model.applyMissionSource() }
    }

    private func footnote(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 11))
            .foregroundStyle(Theme.textTertiary)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func pair() {
        DroneLink(settings: model.settings, console: model.console).pair(password: model.settings.sshPassword)
    }

    private func test() {
        DroneLink(settings: model.settings, console: model.console).testConnection()
    }

    private func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.prompt = "Choose"
        panel.message = "Select the brics_toolkit folder"
        if !model.settings.toolkitPath.isEmpty { panel.directoryURL = model.settings.toolkitRoot }
        if panel.runModal() == .OK, let url = panel.url {
            model.settings.toolkitPath = url.path(percentEncoded: false)
        }
    }
}

/// Port number: fixed-width mono field + stepper, right-aligned so all ports line up.
private struct PortRow: View {
    let title: String
    @Binding var value: Int

    var body: some View {
        LabeledContent(title) {
            HStack(spacing: 6) {
                TextField(title, value: $value, format: .number.grouping(.never))
                    .labelsHidden()
                    .textFieldStyle(.roundedBorder)
                    .font(Theme.mono(12))
                    .multilineTextAlignment(.trailing)
                    .frame(width: 72)
                Stepper(title, value: $value, in: 1024...65535)
                    .labelsHidden()
            }
            .fixedSize()
        }
        .onChange(of: value) { _, v in
            let clamped = min(65535, max(1024, v))
            if clamped != v { value = clamped }
        }
    }
}
