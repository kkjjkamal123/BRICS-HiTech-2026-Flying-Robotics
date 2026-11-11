import Foundation
import Observation

/// A running (or finished) command with its streamed output.
@MainActor
@Observable
final class ProcessJob: Identifiable {
    enum State: Equatable { case running, succeeded, failed(Int32), stopped }

    let id = UUID()
    let title: String
    let commandLine: String
    let startedAt = Date()
    private(set) var lines: [ConsoleLine] = []
    private(set) var state: State = .running
    private(set) var endedAt: Date?

    /// For remote flight scripts: how to stop them safely (SIGINT -> the script lands).
    var remoteStop: (() -> Void)?
    @ObservationIgnored var onExit: ((State) -> Void)?
    @ObservationIgnored fileprivate var process: Process?
    @ObservationIgnored fileprivate var partial = ""

    init(title: String, commandLine: String) {
        self.title = title
        self.commandLine = commandLine
    }

    var isRunning: Bool { state == .running }
    var duration: TimeInterval { (endedAt ?? .now).timeIntervalSince(startedAt) }

    fileprivate func append(_ text: String, isError: Bool) {
        partial += text
        var parts = partial.components(separatedBy: "\n")
        partial = parts.removeLast()
        for p in parts {
            let clean = p.replacingOccurrences(of: "\r", with: "")
            if !clean.isEmpty || !lines.isEmpty { lines.append(ConsoleLine(text: clean, isError: isError)) }
        }
        if lines.count > 4000 { lines.removeFirst(lines.count - 4000) }
    }

    fileprivate func finish(status: Int32, reason: Process.TerminationReason) {
        if !partial.isEmpty { lines.append(ConsoleLine(text: partial, isError: false)); partial = "" }
        if state == .stopped {
            // keep .stopped
        } else {
            state = (status == 0 && reason == .exit) ? .succeeded : .failed(status)
        }
        endedAt = .now
        onExit?(state)
    }

    /// Ends only the local side (ssh) of a drone job, without sending Stop to the drone. Used when a new mission
    /// replaces this one: the drone-side launcher stops the old script itself, and a late Stop must never hit the new one.
    func detach() {
        guard isRunning else { return }
        remoteStop = nil
        lines.append(ConsoleLine(text: "■ Replaced by a new mission run", isError: false))
        terminate()
    }

    func terminate() {
        guard isRunning else { return }
        if let remoteStop {
            remoteStop()               // remote script gets SIGINT and lands; ssh exits by itself
            lines.append(ConsoleLine(text: "■ Stop requested - the drone script lands and exits", isError: true))
            return
        }
        state = .stopped
        process?.interrupt()
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in
            if self?.process?.isRunning == true { self?.process?.terminate() }
        }
    }
}

struct ConsoleLine: Identifiable, Hashable, Sendable {
    let id = UUID()
    let text: String
    let isError: Bool
    let time = Date()
}

@MainActor
@Observable
final class ProcessConsole {
    private(set) var jobs: [ProcessJob] = []
    var selectedJobID: ProcessJob.ID?

    var selectedJob: ProcessJob? { jobs.first { $0.id == selectedJobID } ?? jobs.last }
    var runningCount: Int { jobs.filter(\.isRunning).count }

    @discardableResult
    func run(title: String, executable: URL, arguments: [String], workingDirectory: URL? = nil,
             environment: [String: String] = [:]) -> ProcessJob {
        let commandLine = ([executable.lastPathComponent] + arguments).joined(separator: " ")
        let job = ProcessJob(title: title, commandLine: commandLine)
        jobs.append(job)
        selectedJobID = job.id

        let process = Process()
        process.executableURL = executable
        process.arguments = arguments
        if let workingDirectory { process.currentDirectoryURL = workingDirectory }
        var env = ProcessInfo.processInfo.environment
        env["PYTHONUNBUFFERED"] = "1"
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        environment.forEach { env[$0.key] = $0.value }
        process.environment = env

        let out = Pipe(), err = Pipe()
        process.standardOutput = out
        process.standardError = err
        process.standardInput = FileHandle.nullDevice
        for (pipe, isError) in [(out, false), (err, true)] {
            pipe.fileHandleForReading.readabilityHandler = { [weak job] handle in
                let data = handle.availableData
                guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
                Task { @MainActor in job?.append(text, isError: isError) }
            }
        }
        process.terminationHandler = { [weak job] p in
            let status = p.terminationStatus, reason = p.terminationReason
            out.fileHandleForReading.readabilityHandler = nil
            err.fileHandleForReading.readabilityHandler = nil
            Task { @MainActor in job?.finish(status: status, reason: reason) }
        }
        job.process = process
        do {
            try process.run()
        } catch {
            job.append("Could not start \(executable.path(percentEncoded: false)): \(error.localizedDescription)\n", isError: true)
            job.finish(status: -1, reason: .exit)
        }
        return job
    }

    func clearFinished() {
        jobs.removeAll { !$0.isRunning }
        selectedJobID = jobs.last?.id
    }
}
