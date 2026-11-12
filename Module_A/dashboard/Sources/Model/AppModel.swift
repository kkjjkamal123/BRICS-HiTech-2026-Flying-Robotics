import Foundation
import Observation
import SwiftUI

/// Root state of the app. Owns the long-lived services; views read only what they need.
@MainActor
@Observable
final class AppModel {
    var section: AppSection = .overview {
        didSet { UserDefaults.standard.set(section.rawValue, forKey: Pref.lastSection) }
    }
    private var awakeActivity: NSObjectProtocol?
    private var autoRecording = false
    private var wasLinked = false
    private var wasAirborne = false

    let settings = DashboardSettings()
    /// Scan area, boundary, altitude, line spacing, fire temperature: sent to every mission run as --set.
    let missionSettings = MissionSettings()
    /// The Mission settings sheet (opened from Mission Control, Flight Tests and Simulation).
    var showMissionSettings = false
    /// REC button: records the main and / or thermal pane to .mp4 files in runs/recordings/.
    let recorder = FlightRecorder()
    /// The real arena floor (official ArUco map in config/): drawn under every map.
    private(set) var arena: ArenaMap?
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
        arena = ArenaMap.load(toolkit: root)
        runs = RunsStore(root: root)
        economics = EconomicsStore(root: root)
        spec = SpecStore()
        documents = DocumentsStore(root: root)
        aiModel = AIModelStore(root: root)
        if let arg = UserDefaults.standard.string(forKey: "initialSection"), let s = AppSection(rawValue: arg) {
            section = s
        } else {
            let pick = Pref.string(Pref.launchSection, "last")
            let raw = pick == "last" ? UserDefaults.standard.string(forKey: Pref.lastSection) : pick
            if let raw, let s = AppSection(rawValue: raw) { section = s }
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
        MissionLogArchive.mirror(runsDir: settings.toolkitRoot.appending(path: "runs"))
        watchForFinishedFlights()
        watchDroneAddress()
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

    /// Return / Land / Abort from any button or shortcut: over the mission link when it is up, otherwise over SSH
    /// when the drone answers (the dashboard has no HTTP link to the mission script, e.g. a weak Wi-Fi link).
    func command(_ c: MissionCommand) {
        guard !mission.connected, settings.missionSource == .drone, mission.droneReachable else {
            mission.send(c)
            return
        }
        let link = DroneLink(settings: settings, console: console)
        switch c {
        case .returnHome: link.returnHomeNow()
        case .land, .abort: link.landNow()
        case .start: mission.send(c)
        }
    }

    /// A Return / Land / Abort can reach the drone: mission link up, or the drone answers for the SSH path.
    var canCommand: Bool { mission.connected || (settings.missionSource == .drone && mission.droneReachable) }

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

    // MARK: Find the drone on the Wi-Fi

    /// Drone search: (hosts checked, hosts total) while it runs.
    private(set) var droneSearchProgress: (done: Int, total: Int)?
    private(set) var droneSearchResult: [String]?
    var droneSearching: Bool { droneSearchProgress != nil }

    /// Scans this Mac's Wi-Fi for the drone. If the saved address is not among those found, connects to the first. Returns what it found.
    @discardableResult
    func findDrone() async -> [String] {
        guard !droneSearching else { return droneSearchResult ?? [] }
        droneSearchProgress = (0, 0)
        droneSearchResult = nil
        let found = await DroneFinder.search(videoPort: settings.videoPort,
                                             hint: [settings.droneHost] + settings.recentHosts) { [weak self] d, t in
            self?.droneSearchProgress = (d, t)
        }
        droneSearchProgress = nil
        droneSearchResult = found
        if let first = found.first, !found.contains(settings.droneHost) { connectToDrone(host: first) }
        return found
    }

    /// The venue Wi-Fi gives the drone a new address after a reboot / reconnect. When the saved address stops
    /// answering for ~20 s, search the Wi-Fi and follow the drone to its new address.
    private func watchDroneAddress() {
        Task { [weak self] in
            var misses = 0
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(10))
                guard let self else { return }
                guard self.settings.missionSource == .drone, !self.droneSearching else { misses = 0; continue }
                let host = self.settings.droneHost
                var ok = await PortProbe.isOpen(host: host, port: self.settings.videoPort, timeout: 3)
                if !ok { ok = await PortProbe.isOpen(host: host, port: 22, timeout: 3) }
                misses = ok ? 0 : misses + 1
                if misses >= 2 {
                    misses = 0
                    await self.findDrone()
                }
            }
        }
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
        DroneLink(settings: settings, console: console)
            .launchMission(settings: missionSettings.launcherArguments,
                           title: "Case 1 mission (drone) · \(missionSettings.kind.short)")
    }

    // MARK: Mission logs -> Desktop

    private var lastPhase = ""
    private var runningDroneJobs: Set<ProcessJob.ID> = []
    private var fetchJob: ProcessJob?

    /// Every finished drone mission and flight test is copied to ~/Desktop/BRICS Mission Logs automatically.
    private func watchForFinishedFlights() {
        Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(2))
                self?.checkFinishedFlights()
                self?.applyFlightPreferences()
            }
        }
    }

    /// Keep-awake, auto-record and the link-lost alert, checked on the same 2 s tick as finished flights.
    private func applyFlightPreferences() {
        let linked = mission.connected
        let airborne = linked && MissionPhase.isAirborne(mission.phase)
        let wantAwake = linked && Pref.bool(Pref.keepAwake, true)
        if wantAwake, awakeActivity == nil {
            awakeActivity = ProcessInfo.processInfo.beginActivity(options: [.idleDisplaySleepDisabled, .userInitiated],
                                                                  reason: "Live drone mission")
        } else if !wantAwake, let a = awakeActivity {
            ProcessInfo.processInfo.endActivity(a)
            awakeActivity = nil
        }
        if airborne, Pref.bool(Pref.autoRecord, false), !recorder.isRecording {
            recorder.start(root: settings.toolkitRoot)
            autoRecording = recorder.isRecording
        }
        // stop only once the flight is really over: a Wi-Fi drop mid-flight must not split the recording
        if autoRecording, linked, MissionPhase.isFinished(mission.phase) {
            if recorder.isRecording { recorder.stop() }
            autoRecording = false
        }
        if wasLinked, !linked, wasAirborne { Alerts.linkLost() }
        wasLinked = linked
        wasAirborne = airborne
    }

    private func checkFinishedFlights() {
        var finished = false
        if settings.missionSource == .drone, mission.connected {
            let phase = mission.phase.uppercased()
            let done = ["DONE", "STOPPED"].contains(phase)
            if done, !lastPhase.isEmpty, !["DONE", "STOPPED"].contains(lastPhase) { finished = true }
            lastPhase = phase
        }
        // flight-test scripts (hover, roam, motor ramp, ArUco scan) and the mission job itself
        let droneTitles = ["Case 1 mission", "Hover", "Motor ramp", "ArUco"]
        let running = Set(console.jobs.filter { job in job.isRunning && droneTitles.contains { job.title.hasPrefix($0) } }.map(\.id))
        if !runningDroneJobs.subtracting(running).isEmpty { finished = true }
        runningDroneJobs = running
        guard finished, fetchJob?.isRunning != true else { return }
        try? FileManager.default.createDirectory(at: MissionLogArchive.folder, withIntermediateDirectories: true)
        let job = DroneLink(settings: settings, console: console)
            .fetchResults(toolkit: settings.toolkitRoot, title: "Save mission logs to Desktop")
        fetchJob = job
        job.onExit = { [weak self] _ in
            Task { @MainActor in
                self?.runs.reload { [weak self] in
                    guard let self else { return }
                    self.spec.evaluate(latest: self.runs.latestCase1)
                }
            }
        }
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
        let kind = missionSettings.kind
        var args = [root.appending(path: kind.script).path(percentEncoded: false),
                    "--config", root.appending(path: kind.config).path(percentEncoded: false),
                    "--mock", "--time-scale", String(timeScale),
                    "--ui-port", String(settings.simulatorPort), "--keep-ui", "600"] + missionSettings.setArguments
        if autostart { args.append("--autostart") }
        let job = console.run(title: "Simulation · \(kind.short)",
                              executable: settings.pythonURL,
                              arguments: args,
                              workingDirectory: root,
                              environment: ["BRICS_RUNS": root.appending(path: "runs").path(percentEncoded: false)])
        simulationJob = job
        simulationRunning = true
        job.onExit = { [weak self] _ in
            Task { @MainActor in
                self?.simulationRunning = false
                MissionLogArchive.mirror(runsDir: root.appending(path: "runs"))
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
