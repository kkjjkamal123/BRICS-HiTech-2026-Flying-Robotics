import AppKit
import Foundation
import Observation

struct MissionEndpoint: Equatable, Sendable {
    var host: String
    var port: Int
    var base: URL? { URL(string: "http://\(host):\(port)") }
    var label: String { "\(host):\(port)" }
}

enum MissionCommand: String, Sendable {
    case start, returnHome = "return", land, abort

    var title: String {
        switch self {
        case .start: "Start"
        case .returnHome: "Return Home"
        case .land: "Land"
        case .abort: "Abort"
        }
    }
}

/// One detected object as published by the mission UI (/status → detections).
struct MissionDetection: Decodable, Identifiable, Hashable, Sendable {
    let id: Int?
    let name: String
    let x: Double?
    let y: Double?
    let conf: Double?
    let time: String?
    /// Hottest temperature measured on this object, deg C (thermal detections only).
    var temp: Double?
    /// How many separate detections were merged into this one map entry.
    var hits: Int?

    /// "#1 FIRE 143°C" / "#2 FLAME" - what the map and the table show.
    var mapLabel: String {
        var s = "#\(id ?? 0) \(Theme.label(forObject: name))"
        if let temp { s += String(format: " %.0f°C", temp) }
        return s
    }

    var stableID: String { "\(id ?? -1)-\(name)" }
}

/// JSON served by common/ui_server.py at /status. Every field is optional: the mission fills them over time.
struct MissionStatus: Decodable, Sendable {
    var phase: String?
    var status: String?
    var battery: String?
    var pos: String?
    var detections: [MissionDetection]?
    var counts: [String: Int]?
    var log: [String]?
    var report: String?
    var area: [Double]?
    /// Centres of the floor markers [[x, y], ...] - the real arena, drawn on the map.
    var markers: [[Double]]?
    var home: [Double]?
    var xy: [Double]?
    var track: [[Double]]?
    var fps: [String: Double]?
    var ui_port: Int?
    /// Settings this run really uses (altitude, line spacing, fire temperature...), from the mission.
    var settings: RunSettings?
    var fence: [Double]?

    struct RunSettings: Decodable, Sendable {
        var altitude: Double?
        var step: Double?
        var step_used: Double?
        var overlap: Double?
        var speed: Double?
        var fire_c: Double?
    }

    /// "(1.20, 0.80, 1.50)" → (x, y, z)
    var position: (x: Double, y: Double, z: Double)? {
        guard let pos else { return nil }
        let parts = pos.trimmingCharacters(in: CharacterSet(charactersIn: "() ")).split(separator: ",")
            .compactMap { Double($0.trimmingCharacters(in: .whitespaces)) }
        guard parts.count == 3 else { return nil }
        return (parts[0], parts[1], parts[2])
    }

    /// "3.85 V/cell" → 3.85
    var cellVoltage: Double? {
        guard let battery else { return nil }
        return Double(battery.split(separator: " ").first ?? "")
    }
}

struct TelemetrySample: Identifiable, Sendable {
    let id = UUID()
    let time: Date
    let altitude: Double
    let fps: Double?
}

@MainActor
@Observable
final class MissionClient {
    var endpoint = MissionEndpoint(host: "10.42.0.1", port: 8090) {
        didSet { if endpoint != oldValue { reset() } }
    }
    /// web_video_server of the TECHNIC image (port 8080) - camera topics straight from ROS
    var videoEndpoint: URL?

    private(set) var status: MissionStatus?
    /// Mission link: the mission script's UI answers (commands, telemetry, detections).
    private(set) var connected = false
    /// The drone itself answers (its camera server), even when no mission script is running.
    private(set) var droneReachable = false
    /// Camera topics the drone publishes (from its web_video_server), for the direct feed.
    private(set) var cameraTopics: [String] = []
    var cameraTopic: String? {
        didSet {
            guard cameraTopic != oldValue else { return }
            UserDefaults.standard.set(cameraTopic, forKey: "cameraTopic")
            if !connected { frame = nil }
        }
    }
    /// While a mission runs: nil = the mission's own view (detections drawn on it), or any drone camera topic,
    /// e.g. a debug view such as /aruco_detect/debug, streamed straight from the drone instead.
    var missionViewTopic: String? = UserDefaults.standard.string(forKey: "missionViewTopic") {
        didSet {
            guard missionViewTopic != oldValue else { return }
            UserDefaults.standard.set(missionViewTopic, forKey: "missionViewTopic")
            if connected { frame = nil }
        }
    }
    /// JPEG quality of the main camera stream from the drone (lower = less Wi-Fi, more lag-proof).
    /// How much video the dashboard pulls over the drone's Wi-Fi. At the venue (11 Nov) full-rate video (3.7 Mbit/s)
    /// pushed the drone's replies to 1.3 s and the link kept dropping; Data saver needs about 5x less.
    enum VideoMode: String, CaseIterable, Identifiable {
        case saver, normal, full
        var id: String { rawValue }
        var title: String {
            switch self {
            case .saver: "Data saver (weak Wi-Fi)"
            case .normal: "Normal"
            case .full: "Full quality"
            }
        }
        /// Frames a second asked from the mission's live view (0 = as many as it makes).
        var missionFPS: Int { self == .saver ? 5 : self == .normal ? 10 : 0 }
    }
    var videoMode: VideoMode = VideoMode(rawValue: UserDefaults.standard.string(forKey: "videoMode") ?? "") ?? .saver {
        didSet {
            UserDefaults.standard.set(videoMode.rawValue, forKey: "videoMode")
            streamGeneration += 1                     // reopen the streams with the new settings
        }
    }
    /// Bumped when the video settings change: running streams end and reopen with the new URL.
    private(set) var streamGeneration = 0
    /// Time the last status reply took (the drone link's health): seconds, nil while offline.
    private(set) var linkLatency: Double?
    /// The topic the main pane shows right now (nil = the mission's own view).
    var shownTopic: String? { connected ? missionViewTopic : cameraTopic }
    /// Second feed: the thermal camera, straight from the drone, next to the main picture.
    private(set) var thermalImage: NSImage? {
        didSet { if thermalImage !== oldValue { recorder?.append(thermalImage, track: "thermal") } }
    }
    /// REC button: every frame shown in the two panes also goes to the recorder.
    var recorder: FlightRecorder?
    /// The drone's thermal camera topic (SKYRIS "second camera"), if it is publishing.
    /// Preferred: our thermal node (real temperatures, scale and FIRE boxes already drawn on the drone).
    /// Fallback: the drone's own second-camera topic (picture only, no temperatures).
    var thermalTopic: String? {
        cameraTopics.first { $0 == "/thermal/image_raw" }
            ?? cameraTopics.first { $0.contains("second_camera") && $0.hasSuffix("image_raw") }
    }
    /// The thermal pane shows the raw picture (no temperature scale), so the palette switch applies.
    private(set) var thermalIsRaw = false
    /// Show the thermal pane: the topic exists and the main pane is not already showing it.
    var streamsThermal: Bool {
        guard let t = thermalTopic, videoEndpoint != nil else { return false }
        return connected || cameraTopic != t
    }
    /// The thermal pane is always there for the real drone (it says so when the camera is not plugged in).
    var showsThermalPane: Bool {
        guard videoEndpoint != nil, connected || droneReachable else { return false }
        return thermalTopic == nil || streamsThermal
    }
    /// The current direct feed is the thermal camera (shown as its picture half only).
    private(set) var thermalFrame = false
    /// Thermal view: iron palette (true) or white-hot greyscale (false).
    var thermalPalette = UserDefaults.standard.object(forKey: "thermalPalette") as? Bool ?? true {
        didSet { UserDefaults.standard.set(thermalPalette, forKey: "thermalPalette") }
    }
    /// Video is coming straight from the drone's cameras, without a mission.
    var directVideo: Bool { !connected && droneReachable && cameraTopic != nil }
    var videoLive: Bool { connected || directVideo }
    private(set) var lastUpdate: Date?
    private(set) var frame: NSImage? {
        didSet { if frame !== oldValue { recorder?.append(frame, track: "main") } }
    }
    private(set) var history: [TelemetrySample] = []
    private(set) var lastCommand: (command: MissionCommand, ok: Bool, at: Date)?
    private(set) var newDetectionAlert: MissionDetection?

    private var pollTask: Task<Void, Never>?
    private var frameTask: Task<Void, Never>?
    private var thermalTask: Task<Void, Never>?
    private var lastTopicProbe = Date.distantPast
    private var knownDetections = Set<String>()
    private let session: URLSession = {
        let c = URLSessionConfiguration.ephemeral
        c.timeoutIntervalForRequest = 4               // a busy venue Wi-Fi answers late; late is not lost
        c.requestCachePolicy = .reloadIgnoringLocalCacheData
        c.httpMaximumConnectionsPerHost = 4
        return URLSession(configuration: c)
    }()

    private var streamUnsupported = false

    var phase: String { status?.phase ?? (connected ? "IDLE" : "OFFLINE") }

    func startPolling() {
        guard pollTask == nil else { return }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.pollStatus()
                // fast while live, gentle back-off while there is no link (no busy retry loop)
                let live = self?.connected ?? false
                try? await Task.sleep(for: .milliseconds(live ? 700 : 2000))
            }
        }
        thermalTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                if self.streamsThermal, self.connected || self.droneReachable, let topic = self.thermalTopic {
                    let gen = self.streamGeneration
                    _ = await self.streamFrames(from: self.cameraStreamURL(topic: topic),
                                                while: { $0.streamsThermal && $0.thermalTopic == topic && $0.streamGeneration == gen },
                                                into: { $0.thermalImage = $1 })
                    try? await Task.sleep(for: .milliseconds(400))
                } else {
                    if self.thermalImage != nil { self.thermalImage = nil }
                    try? await Task.sleep(for: .milliseconds(600))
                }
            }
        }
        frameTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                if self.directVideo, let topic = self.cameraTopic {
                    // No mission running: show the camera straight from the drone.
                    let gen = self.streamGeneration
                    _ = await self.streamFrames(from: self.cameraStreamURL(topic: topic),
                                                while: { $0.directVideo && $0.cameraTopic == topic && $0.streamGeneration == gen })
                    try? await Task.sleep(for: .milliseconds(300))
                    continue
                }
                guard self.connected else {
                    try? await Task.sleep(for: .milliseconds(500))
                    continue
                }
                if let topic = self.missionViewTopic, self.videoEndpoint != nil, self.droneReachable {
                    // Mission running, but the operator picked another camera view (e.g. an ArUco debug image).
                    let gen = self.streamGeneration
                    _ = await self.streamFrames(from: self.cameraStreamURL(topic: topic),
                                                while: { $0.connected && $0.missionViewTopic == topic && $0.streamGeneration == gen })
                    try? await Task.sleep(for: .milliseconds(300))
                    continue
                }
                // Preferred: frames pushed by the drone over one open connection (lowest latency).
                // Older mission code has no /stream.mjpg: fall back to fetching single frames.
                let gen = self.streamGeneration
                if !self.streamUnsupported, await self.streamFrames(from: self.missionStreamURL,
                                                                    while: { $0.connected && $0.streamGeneration == gen }) {
                    try? await Task.sleep(for: .milliseconds(200))
                } else {
                    await self.pollFrame()
                    try? await Task.sleep(for: .milliseconds(100))
                }
            }
        }
    }

    private func reset() {
        status = nil
        connected = false
        frame = nil
        streamUnsupported = false
        thermalImage = nil
        droneReachable = false
        cameraTopics = []
        history.removeAll()
        knownDetections.removeAll()
        newDetectionAlert = nil
    }

    private func pollStatus() async {
        guard let url = endpoint.base?.appending(path: "status") else { return }
        do {
            let t0 = Date()
            let (data, response) = try await session.data(from: url)
            linkLatency = Date().timeIntervalSince(t0)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
            let decoded = try JSONDecoder().decode(MissionStatus.self, from: data)
            apply(decoded)
            if videoEndpoint != nil, Date().timeIntervalSince(lastTopicProbe) > 5 {      // for the thermal pane
                lastTopicProbe = .now
                await probeDrone()
            }
        } catch {
            if connected, let last = lastUpdate, Date().timeIntervalSince(last) > 8 {       // ~2 missed replies on a slow link
                connected = false
            } else if lastUpdate == nil {
                connected = false
            }
            if !connected {
                linkLatency = nil
                await probeDrone()
            }
        }
    }

    /// No mission UI: is the drone itself there? Its web_video_server lists the camera topics on its index page.
    private func probeDrone() async {
        guard let base = videoEndpoint else {
            droneReachable = false
            return
        }
        let started = endpoint
        var topics: [String] = []
        var reachable = false
        if let (data, response) = try? await session.data(from: base),
           (response as? HTTPURLResponse)?.statusCode == 200 {
            reachable = true
            let html = String(decoding: data, as: UTF8.self)
            for match in html.matches(of: /stream_viewer\?topic=([^"&'<> ]+)/) {
                let t = String(match.1)
                if !topics.contains(t) { topics.append(t) }
            }
        }
        guard endpoint == started else { return }
        if droneReachable != reachable { droneReachable = reachable }
        if reachable, topics != cameraTopics { cameraTopics = topics }
        if reachable, cameraTopic == nil || !(topics.isEmpty || topics.contains(cameraTopic ?? "")) {
            let saved = UserDefaults.standard.string(forKey: "cameraTopic")
            cameraTopic = topics.first { $0 == saved }
                ?? topics.first { $0.hasSuffix("main_camera/image_raw") }
                ?? topics.first { $0.contains("main_camera") && !$0.contains("throttled") }
                ?? topics.first
                ?? "/main_camera/image_raw"
        }
        if !reachable, frame != nil, !connected { frame = nil }
        // the main pane should not sit on the thermal topic by default: thermal has its own pane
        if reachable, cameraTopic == thermalTopic, UserDefaults.standard.string(forKey: "cameraTopicChosen") == nil,
           let main = topics.first(where: { $0.hasSuffix("main_camera/image_raw") }) {
            cameraTopic = main
        }
    }

    private func apply(_ s: MissionStatus) {
        status = s
        connected = true
        lastUpdate = .now
        if let p = s.position, p.z.isFinite {
            history.append(TelemetrySample(time: .now, altitude: p.z, fps: s.fps?["thermal"] ?? s.fps?["rgb"]))
            if history.count > 400 { history.removeFirst(history.count - 400) }
        }
        for d in s.detections ?? [] where !knownDetections.contains(d.stableID) {
            knownDetections.insert(d.stableID)
            newDetectionAlert = d
        }
    }

    /// Shows the MJPEG stream until it ends or `valid` turns false. Returns true if at least one frame arrived.
    private func streamFrames(from url: URL?, while valid: (MissionClient) -> Bool,
                              into sink: ((MissionClient, NSImage) -> Void)? = nil) async -> Bool {
        let started = endpoint
        guard let url else { return false }
        let stream = MJPEGStream()
        var got = false
        for await data in stream.frames(from: url) {
            guard endpoint == started, valid(self), !Task.isCancelled else { break }
            guard let cg = ThermalFrame.cgImage(from: data) else { continue }
            let thermal = ThermalFrame.isThermal(cg)
            if sink == nil, thermalFrame != thermal { thermalFrame = thermal }
            if sink != nil, thermalIsRaw != thermal { thermalIsRaw = thermal }
            if let image = thermal ? ThermalFrame.render(cg, palette: thermalPalette)
                                   : NSImage(cgImage: cg, size: NSSize(width: cg.width, height: cg.height)) {
                if let sink { sink(self, image) } else { frame = image }
                got = true
            }
        }
        if stream.rejected, connected { streamUnsupported = true }
        return got
    }

    private func pollFrame() async {
        guard let url = endpoint.base?.appending(path: "frame.jpg") else { return }
        if let (data, response) = try? await session.data(from: url),
           (response as? HTTPURLResponse)?.statusCode == 200,
           let image = NSImage(data: data) {
            frame = image
        }
    }

    func send(_ command: MissionCommand) {
        guard let base = endpoint.base,
              var comps = URLComponents(url: base.appending(path: "cmd"), resolvingAgainstBaseURL: false) else { return }
        comps.queryItems = [URLQueryItem(name: "c", value: command.rawValue)]
        guard let url = comps.url else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        Task {
            let ok = (try? await session.data(for: request)).map { ($0.1 as? HTTPURLResponse)?.statusCode == 200 } ?? false
            lastCommand = (command, ok, .now)
        }
    }

    func dismissAlert() { newDetectionAlert = nil }

    /// New mission run: forget the previous run's status, detections, altitude history and picture.
    func clearForNewMission() {
        status = nil
        connected = false
        lastUpdate = nil
        frame = nil
        history.removeAll()
        knownDetections.removeAll()
        newDetectionAlert = nil
        lastCommand = nil
    }

    /// Friendly name of a drone camera topic for the camera menu.
    static func topicTitle(_ topic: String) -> String {
        let t = topic.lowercased()
        if t == "/thermal/image_raw" { return "Thermal (°C, FIRE boxes)" }
        if t.contains("second_camera") { return "Thermal (raw picture)" }
        if t.contains("aruco_detect") && t.contains("debug") { return "ArUco markers seen (debug)" }
        if t.contains("aruco_map") && t.contains("debug") { return "ArUco map pose (debug)" }
        if t.contains("aruco_map") && t.hasSuffix("/image") { return "ArUco map image" }
        if t.contains("optical_flow") { return "Optical flow (debug)" }
        if t.contains("face_annotated") { return "Second camera (annotated)" }
        if t.contains("image_web_raw") { return "Main camera (web copy)" }
        if t.hasSuffix("main_camera/image_raw") { return "Main camera" }
        if t.contains("main_camera") && t.contains("throttled") { return "Main camera (5 Hz)" }
        if t.contains("main_camera") && t.contains("rect") { return "Main camera (rectified)" }
        return topic
    }

    enum TopicGroup: String, CaseIterable { case main = "Main camera", debug = "Debug views", thermal = "Thermal", other = "Other" }
    static func group(_ topic: String) -> TopicGroup {
        let t = topic.lowercased()
        if t.hasPrefix("/thermal") || t.contains("second_camera") { return .thermal }
        if t.contains("debug") || t.contains("visualization") || t.contains("aruco") || t.contains("optical_flow") { return .debug }
        if t.contains("main_camera") { return .main }
        return .other
    }

    /// Camera stream straight from the drone's web_video_server (works without our mission running).
    /// The mission's live view, at most `videoMode.missionFPS` frames a second (older drone code ignores the limit).
    var missionStreamURL: URL? {
        guard let base = endpoint.base,
              var c = URLComponents(url: base.appending(path: "stream.mjpg"), resolvingAgainstBaseURL: false) else { return nil }
        if videoMode.missionFPS > 0 { c.queryItems = [URLQueryItem(name: "fps", value: String(videoMode.missionFPS))] }
        return c.url
    }

    /// Camera stream straight from the drone's web_video_server. Size, quality and - for the main camera - frame rate
    /// follow `videoMode` (measured at the venue: Data saver 29 + 64 KB/s, full 256 + 207 KB/s).
    func cameraStreamURL(topic: String) -> URL? {
        guard let base = videoEndpoint else { return nil }
        var t = topic
        var q = 50, size: (Int, Int)? = nil
        if topic.contains("second_camera") {
            q = 95                                         // raw picture: the temperature rows must survive JPEG
        } else if topic.hasPrefix("/thermal") {
            switch videoMode {
            case .saver: q = 60; size = (285, 192)
            case .normal: q = 75
            case .full: q = 85
            }
        } else {
            switch videoMode {
            case .saver:
                q = 40; size = (480, 360)
                // the throttled copy of the main camera (5 frames/s) instead of the full 30 frames/s
                if topic.hasSuffix("main_camera/image_raw"), cameraTopics.contains(topic + "_throttled") { t = topic + "_throttled" }
            case .normal: q = 50
            case .full: q = 80
            }
        }
        var c = URLComponents(url: base.appending(path: "stream"), resolvingAgainstBaseURL: false)
        c?.queryItems = [URLQueryItem(name: "topic", value: t), URLQueryItem(name: "type", value: "mjpeg"),
                         URLQueryItem(name: "quality", value: String(q))]
        if let size {
            c?.queryItems? += [URLQueryItem(name: "width", value: String(size.0)), URLQueryItem(name: "height", value: String(size.1))]
        }
        return c?.url
    }
}
