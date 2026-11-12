import SwiftUI

@main
struct BRICSDashboardApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup("BRICS Dashboard", id: "main") {
            RootView()
                .environment(model)
                .focusEffectDisabled()
                .frame(minWidth: 1180, minHeight: 760)
                .task { model.start() }
        }
        .defaultSize(width: 1480, height: 920)
        .windowResizability(.contentMinSize)
        .windowToolbarStyle(.unified(showsTitle: false))
        .commands {
            CommandMenu("Drone") {
                Button("Start Mission") { model.mission.send(.start) }
                    .keyboardShortcut("r", modifiers: [.command, .shift])
                Button("Return Home") { model.command(.returnHome) }
                    .keyboardShortcut("h", modifiers: [.command, .shift])
                Button("Land Now") { model.command(.land) }
                    .keyboardShortcut("l", modifiers: [.command, .shift])
                Divider()
                Button("Run Simulation") { model.startSimulation() }
                    .keyboardShortcut("s", modifiers: [.command, .shift])
                Button("Stop Simulation") { model.stopSimulation() }
            }
            CommandGroup(after: .sidebar) {
                ForEach(AppSection.allCases) { section in
                    Button(section.title) { model.section = section }
                        .keyboardShortcut(section.shortcut, modifiers: .command)
                }
            }
        }

        Settings {
            SettingsView()
                .environment(model)
                .frame(width: 560, height: 520)
        }
    }
}
