import Foundation
import Observation
import SwiftUI

/// Root state of the app. Owns the long-lived services; views read only what they need.
@MainActor
@Observable
final class AppModel {
    var section: AppSection = .overview

    let settings = DashboardSettings()
    /// Scan area, boundary, altitude, line spacing, fire temperature: sent to every mission run as --set.
    let missionSettings = MissionSettings()
    /// The Mission settings sheet (opened from Mission Control, Flight Tests and Simulation).
    var showMissionSettings = false
    /// REC button: records the main and / or thermal pane to .mp4 files in runs/recordings/.
    let recorder = FlightRecorder()
    private var autoRecordStarted = false
    let mission: MissionClient
    let console = ProcessConsole()
    let battery = BatteryMonitor()
    let runs: RunsStore
    let economics: EconomicsStore
    let spec: SpecStore
    let documents: DocumentsStore
    let aiModel: AIModelStore

    private(set) var simulationRunning = false
    private var simulationJob: ProcessJob?

    init() {
        let root = settings.toolkitRoot
        mission = MissionClient()
        mission.recorder = recorder
        runs = RunsStore(root: root)
        economics = EconomicsStore(root: root)
        spec = SpecStore()
        documents = DocumentsStore(root: root)
        aiModel = AIModelStore(root: root)
        if let arg = UserDefaults.standard.string(forKey: "initialSection"), let s = AppSection(rawValue: arg) {
            section = s
        }
        applyMissionSource()
        showMissionSettings = UserDefaults.standard.bool(forKey: "openMissionSettings")   // `-openMissionSettings YES`
    }

    func start() {
        mission.startPolling()
        runs.reload { [weak self] in
            guard let self else { return }
            self.spec.evaluate(latest: self.runs.latestCase1)
        }
        economics.reload()
        documents.reload()
        aiModel.reload()
        // `-autoRecordSeconds 8`: record both panes for N seconds after launch (self-test of the REC button)
        let secs = UserDefaults.standard.double(forKey: "autoRecordSeconds")
        if secs > 0, !autoRecordStarted {
            autoRecordStarted = true
            Task { [weak self] in
                try? await Task.sleep(for: .seconds(4))
                guard let self else { return }
                self.recorder.start(root: self.settings.toolkitRoot)
                try? await Task.sleep(for: .seconds(secs))
                self.recorder.stop()
            }
        }
    }

    /// Which mission UI the live view listens to: the real drone or the local simulator.
    func applyMissionSource() {
        switch settings.missionSource {
        case .drone: mission.endpoint = MissionEndpoint(host: settings.droneHost, port: settings.missionPort)
        case .simulator: mission.endpoint = MissionEndpoint(host: "127.0.0.1", port: settings.simulatorPort)
        }
        mission.videoEndpoint = settings.missionSource == .drone
            ? URL(string: "http://\(settings.droneHost):\(settings.videoPort)")
            : nil
        battery.follow(sshTarget: settings.missionSource == .drone ? settings.sshTarget : nil, password: settings.sshPassword)
    }

    /// Point the whole app (live view, camera, SSH, deploy) at this drone address.
    func connectToDrone(host: String) {
        let host = DashboardSettings.cleanHost(host)
        guard !host.isEmpty else { return }
        settings.droneHost = host
        settings.rememberHost(host)
        settings.missionSource = .drone
        applyMissionSource()
    }

    // MARK: Drone mission

    /// The mission runs (or is about to) on the drone: Run mission is not allowed then.
    var droneMissionAirborne: Bool {
        guard settings.missionSource == .drone, mission.connected else { return false }
        return ["TAKEOFF", "MISSION", "INSPECT", "RETURN", "LAND"].contains(mission.phase.uppercased())
    }

    /// Run mission: replaces any previous run cleanly. The old console job is detached, the screen is cleared, and on
    /// the drone tools/run_mission.sh stops the old script (only if the motors are disarmed) before starting the new one.
    func runNewDroneMission() {
        guard !droneMissionAirborne else { return }
        for job in console.jobs where job.isRunning && job.title.hasPrefix("Case 1 mission") { job.detach() }
        settings.missionSource = .drone
        applyMissionSource()
        mission.clearForNewMission()
        DroneLink(settings: settings, console: console).launchMission(settings: missionSettings.setArguments)
    }

    // MARK: Simulation

    func startSimulation(timeScale: Double = 3, autostart: Bool = false) {
        if simulationRunning, let old = simulationJob {
            // a new run replaces the running one: stop it, start again when it has exited
            old.onExit = { [weak self] _ in
                Task { @MainActor in
                    self?.simulationRunning = false
                    self?.startSimulation(timeScale: timeScale, autostart: autostart)
                }
            }
            old.terminate()
            return
        }
        mission.clearForNewMission()
        settings.missionSource = .simulator
        applyMissionSource()
        let root = settings.toolkitRoot
        var args = [root.appending(path: "drone/case1_fire.py").path(percentEncoded: false),
                    "--config", root.appending(path: "config/case1_fire.yaml").path(percentEncoded: false),
                    "--mock", "--time-scale", String(timeScale),
                    "--ui-port", String(settings.simulatorPort), "--keep-ui", "600"] + missionSettings.setArguments
        if autostart { args.append("--autostart") }
        let job = console.run(title: "Simulation · Case 1 mission",
                              executable: settings.pythonURL,
                              arguments: args,
                              workingDirectory: root,
                              environment: ["BRICS_RUNS": root.appending(path: "runs").path(percentEncoded: false)])
        simulationJob = job
        simulationRunning = true
        job.onExit = { [weak self] _ in
            Task { @MainActor in
                self?.simulationRunning = false
                self?.runs.reload { [weak self] in
                    guard let self else { return }
                    self.spec.evaluate(latest: self.runs.latestCase1)
                }
            }
        }
    }

    func stopSimulation() {
        simulationJob?.terminate()
        simulationRunning = false
    }
}
