import AVFoundation
import AppKit
import CoreVideo
import Observation

/// Which camera feeds the REC button records.
enum RecordCameras: String, CaseIterable, Identifiable {
    case main, thermal, both
    var id: String { rawValue }
    var title: String {
        switch self {
        case .main: "Main camera"
        case .thermal: "Thermal camera"
        case .both: "Both cameras (two files)"
        }
    }
    var tracks: [String] {
        switch self {
        case .main: ["main"]
        case .thermal: ["thermal"]
        case .both: ["main", "thermal"]
        }
    }
}

/// Records the live camera panes to H.264 .mp4 files on this Mac: one file per camera, in
/// runs/recordings/flight_<date>_<time>/ (main.mp4, thermal.mp4). It records exactly what the pane shows: the
/// mission view with detections, or the topic picked in the camera menu (e.g. the plain main camera or a debug view).
@MainActor
@Observable
final class FlightRecorder {
    var cameras: RecordCameras = RecordCameras(rawValue: UserDefaults.standard.string(forKey: "recordCameras") ?? "") ?? .both {
        didSet { UserDefaults.standard.set(cameras.rawValue, forKey: "recordCameras") }
    }
    private(set) var isRecording = false
    private(set) var startedAt: Date?
    /// Folder of the current / last recording.
    private(set) var folder: URL?
    /// Frames written per camera in the current / last recording.
    private(set) var frameCounts: [String: Int] = [:]
    private(set) var lastError: String?
    private var writers: [String: VideoTrackWriter] = [:]
    /// Writers of the last recording, kept alive while AVFoundation finishes the files.
    private var retired: [VideoTrackWriter] = []

    func start(root: URL) {
        guard !isRecording else { return }
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyyMMdd_HHmmss"
        let dir = root.appending(path: "runs/recordings/flight_\(f.string(from: .now))", directoryHint: .isDirectory)
        do {
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        } catch {
            lastError = "Cannot create \(dir.path(percentEncoded: false)): \(error.localizedDescription)"
            return
        }
        folder = dir
        writers = Dictionary(uniqueKeysWithValues: cameras.tracks.map { ($0, VideoTrackWriter(url: dir.appending(path: "\($0).mp4"))) })
        frameCounts = Dictionary(uniqueKeysWithValues: cameras.tracks.map { ($0, 0) })
        lastError = nil
        startedAt = .now
        isRecording = true
    }

    func stop() {
        guard isRecording else { return }
        isRecording = false
        let done = writers
        writers = [:]
        for (_, w) in done { w.finish() }
        retired = Array(done.values)
        // a camera that never sent a frame leaves no file behind
        if let folder, frameCounts.values.allSatisfy({ $0 == 0 }) {
            lastError = "No frames arrived - nothing was recorded."
            try? FileManager.default.removeItem(at: folder)
            self.folder = nil
        }
    }

    func toggle(root: URL) { isRecording ? stop() : start(root: root) }

    /// Called by MissionClient for every frame shown in a pane ("main" or "thermal").
    func append(_ image: NSImage?, track: String) {
        guard isRecording, let image, let w = writers[track],
              let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return }
        if w.append(cg) { frameCounts[track, default: 0] += 1 }
        if let e = w.error { lastError = "\(track): \(e)" }
    }

    func revealInFinder() {
        guard let folder else { return }
        NSWorkspace.shared.activateFileViewerSelecting([folder])
    }
}

/// One .mp4 file. The size is fixed by the first frame (later frames of another size are fitted in, letterboxed);
/// timestamps are wall-clock, so a variable frame rate or a Wi-Fi gap plays back at true speed.
@MainActor
final class VideoTrackWriter {
    let url: URL
    private(set) var error: String?
    private var writer: AVAssetWriter?
    private var input: AVAssetWriterInput?
    private var adaptor: AVAssetWriterInputPixelBufferAdaptor?
    private var width = 0, height = 0
    private var start: Date?
    private var lastT = -1.0

    init(url: URL) { self.url = url }

    @discardableResult
    func append(_ cg: CGImage) -> Bool {
        let now = Date()
        if writer == nil {
            guard setUp(width: cg.width, height: cg.height) else { return false }
            start = now
        }
        guard let writer, writer.status == .writing, let input, let adaptor, let start,
              input.isReadyForMoreMediaData, let pool = adaptor.pixelBufferPool else { return false }
        let t = now.timeIntervalSince(start)
        guard t > lastT + 0.001 else { return false }
        var buffer: CVPixelBuffer?
        CVPixelBufferPoolCreatePixelBuffer(nil, pool, &buffer)
        guard let buffer else { return false }
        CVPixelBufferLockBaseAddress(buffer, [])
        if let ctx = CGContext(data: CVPixelBufferGetBaseAddress(buffer), width: width, height: height, bitsPerComponent: 8,
                               bytesPerRow: CVPixelBufferGetBytesPerRow(buffer), space: CGColorSpaceCreateDeviceRGB(),
                               bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue) {
            ctx.setFillColor(CGColor(gray: 0, alpha: 1))
            ctx.fill(CGRect(x: 0, y: 0, width: width, height: height))
            let s = min(Double(width) / Double(cg.width), Double(height) / Double(cg.height))
            let w = Double(cg.width) * s, h = Double(cg.height) * s
            ctx.interpolationQuality = .high
            ctx.draw(cg, in: CGRect(x: (Double(width) - w) / 2, y: (Double(height) - h) / 2, width: w, height: h))
        }
        CVPixelBufferUnlockBaseAddress(buffer, [])
        guard adaptor.append(buffer, withPresentationTime: CMTime(seconds: t, preferredTimescale: 600)) else {
            error = writer.error?.localizedDescription ?? "frame not written"
            return false
        }
        lastT = t
        return true
    }

    private func setUp(width w: Int, height h: Int) -> Bool {
        width = max(16, w & ~1)            // H.264 wants even sizes
        height = max(16, h & ~1)
        do {
            let writer = try AVAssetWriter(outputURL: url, fileType: .mp4)
            let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
                AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: width, AVVideoHeightKey: height,
                AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: max(1_000_000, width * height * 6)],
            ])
            input.expectsMediaDataInRealTime = true
            let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [
                kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
                kCVPixelBufferWidthKey as String: width, kCVPixelBufferHeightKey as String: height,
            ])
            guard writer.canAdd(input) else { error = "cannot add video track"; return false }
            writer.add(input)
            guard writer.startWriting() else { error = writer.error?.localizedDescription ?? "cannot start"; return false }
            writer.startSession(atSourceTime: .zero)
            self.writer = writer
            self.input = input
            self.adaptor = adaptor
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    func finish() {
        guard let writer, writer.status == .writing else { return }
        input?.markAsFinished()
        writer.finishWriting {}
    }
}
