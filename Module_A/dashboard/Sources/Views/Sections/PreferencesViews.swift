import AppKit
import SwiftUI

struct SettingsWindow: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        TabView {
            Tab("General", systemImage: "gearshape") { GeneralSettings() }
            Tab("Appearance", systemImage: "paintpalette") { AppearanceSettings() }
            Tab("Drone", systemImage: "antenna.radiowaves.left.and.right") { SettingsView() }
            Tab("Video", systemImage: "video") { VideoSettings() }
            Tab("Alerts", systemImage: "bell.badge") { AlertSettings() }
            Tab("Advanced", systemImage: "wrench.and.screwdriver") { AdvancedSettings() }
        }
        .environment(model)
        .frame(width: 620, height: 760)
        .preferredColorScheme(.dark)
        .tint(Theme.accent)
    }
}

/// Grouped form with the dashboard's look, shared by the settings tabs.
private struct SettingsForm<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        Form { content }
            .formStyle(.grouped)
            .scrollContentBackground(.hidden)
            .background(Color(hex: 0x0A0B0D))
    }
}

private func footnote(_ text: String) -> some View {
    Text(text)
        .font(.system(size: 11))
        .foregroundStyle(Theme.textTertiary)
        .fixedSize(horizontal: false, vertical: true)
}

// MARK: - General

private struct GeneralSettings: View {
    @Environment(AppModel.self) private var model
    @AppStorage(Pref.launchSection) private var launchSection = "last"
    @AppStorage(Pref.keepAwake) private var keepAwake = true
    @AppStorage(Pref.confirmQuit) private var confirmQuit = true

    var body: some View {
        @Bindable var settings = model.settings
        SettingsForm {
            Section {
                Picker("Open at launch", selection: $launchSection) {
                    Text("Last page used").tag("last")
                    Divider()
                    ForEach(AppSection.allCases) { Text($0.title).tag($0.rawValue) }
                }
                Picker("Live source", selection: Binding(get: { settings.missionSource },
                                                         set: { settings.missionSource = $0; model.applyMissionSource() })) {
                    ForEach(MissionSource.allCases) { Text($0.title).tag($0) }
                }
            } header: {
                Text("Startup")
            } footer: {
                footnote("The live source is what Mission Control connects to: the real drone or the simulator on this Mac.")
            }

            Section("While flying") {
                Toggle("Keep this Mac awake while a mission is connected", isOn: $keepAwake)
                Toggle("Ask before quitting while the drone is in the air", isOn: $confirmQuit)
            }

            Section("Keyboard") {
                shortcut("Start mission", "⇧⌘R")
                shortcut("Return home", "⇧⌘H")
                shortcut("Land now", "⇧⌘L")
                shortcut("Run simulation", "⇧⌘S")
                shortcut("Switch page", "⌘1 – ⌘9")
                shortcut("Settings", "⌘,")
            }
        }
    }

    private func shortcut(_ title: String, _ keys: String) -> some View {
        LabeledContent(title) { Text(keys).font(Theme.mono(12)).foregroundStyle(Theme.textSecondary) }
    }
}

// MARK: - Video

private struct VideoSettings: View {
    @Environment(AppModel.self) private var model
    @AppStorage(Pref.autoRecord) private var autoRecord = false
    @AppStorage(Pref.videoTelemetry) private var telemetry = true
    @AppStorage(Pref.reticle) private var reticle = true
    @AppStorage(Pref.mapLabels) private var mapLabels = true

    var body: some View {
        @Bindable var mission = model.mission
        @Bindable var recorder = model.recorder
        SettingsForm {
            Section {
                Picker("Stream quality", selection: $mission.videoMode) {
                    ForEach(MissionClient.VideoMode.allCases) { Text($0.title).tag($0) }
                }
                Picker("Thermal palette", selection: $mission.thermalPalette) {
                    Text("Iron").tag(true)
                    Text("White hot").tag(false)
                }
            } header: {
                Text("Live video")
            } footer: {
                footnote("Data saver pulls about 5× less over the drone's Wi-Fi. Use it whenever the link feels slow.")
            }

            Section("Overlays") {
                Toggle("Altitude, position and FPS on the video", isOn: $telemetry)
                Toggle("Centre crosshair", isOn: $reticle)
                Toggle("Object labels on the map", isOn: $mapLabels)
            }

            Section {
                Picker("Record", selection: $recorder.cameras) {
                    ForEach(RecordCameras.allCases) { Text($0.title).tag($0) }
                }
                Toggle("Start recording at takeoff, stop after landing", isOn: $autoRecord)
                LabeledContent("Folder") {
                    Button("Show in Finder", systemImage: "folder") {
                        let dir = model.settings.toolkitRoot.appending(path: "runs/recordings", directoryHint: .isDirectory)
                        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
                        NSWorkspace.shared.open(dir)
                    }
                    .buttonStyle(.secondary)
                    .fixedSize()
                }
            } header: {
                Text("Recording")
            } footer: {
                footnote("Recordings are H.264 .mp4 files in runs/recordings, one file per camera.")
            }
        }
    }
}

// MARK: - Alerts

private struct AlertSettings: View {
    @AppStorage(Pref.alertBanner) private var banner = true
    @AppStorage(Pref.alertSeconds) private var seconds = 5.0
    @AppStorage(Pref.alertSound) private var sound = "Glass"
    @AppStorage(Pref.alertNotify) private var notify = true
    @AppStorage(Pref.linkLostSound) private var linkLost = true
    @AppStorage(Pref.batteryCaution) private var caution = 35.0
    @AppStorage(Pref.batteryCritical) private var critical = 20.0

    var body: some View {
        SettingsForm {
            Section("When an object is confirmed") {
                Toggle("Show a banner", isOn: $banner)
                LabeledContent("Banner stays for") {
                    HStack(spacing: 10) {
                        Slider(value: $seconds, in: 2...15, step: 1).frame(width: 180)
                        Text("\(Int(seconds)) s").font(Theme.mono(12)).frame(width: 34, alignment: .trailing)
                    }
                }
                .disabled(!banner)
                Picker("Sound", selection: $sound) {
                    Text("None").tag("")
                    Divider()
                    ForEach(Alerts.sounds, id: \.self) { Text($0).tag($0) }
                }
                .onChange(of: sound) { _, s in Alerts.play(s) }
                Toggle("Notify when the dashboard is in the background", isOn: $notify)
                    .onChange(of: notify) { _, on in if on { Alerts.requestPermission() } }
            }

            Section("Link") {
                Toggle("Play a sound if the link drops during a flight", isOn: $linkLost)
            }

            Section {
                LabeledContent("Caution below") {
                    Stepper("\(Int(caution)) %", value: $caution, in: max(critical + 5, 25)...60, step: 5)
                        .font(Theme.mono(12))
                }
                LabeledContent("Critical below") {
                    Stepper("\(Int(critical)) %", value: $critical, in: 10...min(caution - 5, 35), step: 5)
                        .font(Theme.mono(12))
                }
            } header: {
                Text("Battery colours")
            } footer: {
                footnote("Only changes how the dashboard colours the battery. The drone's own low-battery landing is set in its mission config and is not affected.")
            }
        }
    }
}

// MARK: - Advanced

private struct AdvancedSettings: View {
    @Environment(AppModel.self) private var model
    @State private var confirmReset = false

    var body: some View {
        SettingsForm {
            Section("Data") {
                folderRow("Mission runs", model.settings.toolkitRoot.appending(path: "runs", directoryHint: .isDirectory))
                folderRow("Logs saved after flights", MissionLogArchive.folder)
                folderRow("Toolkit", model.settings.toolkitRoot)
            }

            Section {
                LabeledContent("Appearance") {
                    Button("Restore defaults") {
                        withAnimation(.smooth(duration: 0.45)) {
                            let a = Appearance.shared
                            a.theme = .ember
                            a.surface = .solid
                            a.missionLayout = .split
                            a.animatedBackground = true
                            a.pageAnimations = true
                            a.compact = false
                        }
                    }
                    .buttonStyle(.secondary)
                    .fixedSize()
                }
                LabeledContent("Everything") {
                    Button("Reset all settings…", role: .destructive) { confirmReset = true }
                        .buttonStyle(.secondary)
                        .fixedSize()
                }
            } header: {
                Text("Reset")
            } footer: {
                footnote("Resetting everything also clears the drone address, login and ports, then relaunches the dashboard.")
            }

            Section("About") {
                LabeledContent("Version", value: version)
                TextField("Team", text: Binding(get: { model.settings.teamName }, set: { model.settings.teamName = $0 }))
            }
        }
        .confirmationDialog("Reset all settings?", isPresented: $confirmReset) {
            Button("Reset and Relaunch", role: .destructive, action: resetAll)
        } message: {
            Text("Every setting goes back to its default. Mission runs and recordings are not touched.")
        }
    }

    private var version: String {
        let info = Bundle.main.infoDictionary
        return "\(info?["CFBundleShortVersionString"] as? String ?? "1.0") (\(info?["CFBundleVersion"] as? String ?? "1"))"
    }

    private func folderRow(_ title: String, _ url: URL) -> some View {
        LabeledContent(title) {
            HStack(spacing: 8) {
                Text(url.path(percentEncoded: false).replacingOccurrences(of: NSHomeDirectory(), with: "~"))
                    .font(Theme.code(11))
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(1)
                    .truncationMode(.head)
                    .frame(maxWidth: 260, alignment: .trailing)
                Button { NSWorkspace.shared.open(url) } label: { Image(systemName: "arrow.up.forward.app") }
                    .buttonStyle(.quiet)
                    .help("Open in Finder")
            }
        }
    }

    private func resetAll() {
        guard let id = Bundle.main.bundleIdentifier else { return }
        UserDefaults.standard.removePersistentDomain(forName: id)
        UserDefaults.standard.synchronize()
        let config = NSWorkspace.OpenConfiguration()
        config.createsNewApplicationInstance = true
        NSWorkspace.shared.openApplication(at: Bundle.main.bundleURL, configuration: config) { _, _ in
            DispatchQueue.main.async { exit(0) }      // plain exit: the old values must not be written back on quit
        }
    }
}
