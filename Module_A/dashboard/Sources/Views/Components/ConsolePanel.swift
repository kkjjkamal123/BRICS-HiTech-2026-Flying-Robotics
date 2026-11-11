import SwiftUI

/// Live output of local and drone-side commands: job chips, a safe Stop, and a lazily rendered,
/// auto-following terminal. Only `ConsoleOutput` observes `job.lines`, so a new line never re-renders the header.
struct ConsolePanel: View {
    @Environment(AppModel.self) private var model
    var height: CGFloat = 260

    var body: some View {
        let console = model.console
        let job = console.selectedJob
        GlassCard(padding: 0) {
            VStack(spacing: 0) {
                ConsoleToolbar(console: console, job: job)
                Rectangle().fill(Theme.hairline).frame(height: 1)
                Group {
                    if let job {
                        ConsoleOutput(job: job)
                            .id(job.id)
                    } else {
                        ConsoleEmpty()
                    }
                }
                .frame(height: height)
            }
        }
        #if DEBUG
        .task { ConsoleDemo.startIfRequested(console) }
        #endif
    }
}

// MARK: - Toolbar

private struct ConsoleToolbar: View {
    let console: ProcessConsole
    let job: ProcessJob?

    var body: some View {
        HStack(spacing: 12) {
            HStack(spacing: 7) {
                Image(systemName: "terminal")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.textTertiary)
                Eyebrow(text: "Console")
            }
            .fixedSize()

            if console.jobs.isEmpty {
                Spacer(minLength: 0)
            } else {
                JobChips(console: console, selectedID: job?.id)
            }

            if let job {
                JobControls(job: job)
            }

            Button {
                withAnimation(.snappy(duration: 0.2)) { console.clearFinished() }
            } label: {
                Image(systemName: "trash")
                    .font(.system(size: 11.5, weight: .medium))
                    .frame(width: 14)
            }
            .buttonStyle(.secondary)
            .help("Remove finished jobs")
            .disabled(console.jobs.allSatisfy(\.isRunning))
        }
        .padding(.horizontal, 14)
        .frame(height: 46)
    }
}

/// Elapsed time + Stop for the selected job. Elapsed uses a system timer text (no view re-render per second).
private struct JobControls: View {
    let job: ProcessJob

    var body: some View {
        HStack(spacing: 10) {
            Group {
                if job.isRunning {
                    Text(timerInterval: job.startedAt...Date.distantFuture, countsDown: false)
                } else {
                    Text(Duration.seconds(job.duration).formatted(.time(pattern: .minuteSecond)))
                }
            }
            .font(Theme.mono(11.5, .medium))
            .monospacedDigit()
            .foregroundStyle(job.isRunning ? Theme.textPrimary : Theme.textSecondary)
            .frame(minWidth: 40, alignment: .trailing)
            .help("Elapsed")

            if job.isRunning {
                Button { job.terminate() } label: {
                    Label(job.remoteStop != nil ? "Stop & land" : "Stop", systemImage: "stop.fill")
                        .labelStyle(.titleAndIcon)
                }
                .buttonStyle(.primary(Theme.critical))
                .fixedSize()
                .help(job.remoteStop != nil
                      ? "Sends Ctrl+C to the drone script: it lands where it is, then exits"
                      : "Interrupt this command")
                .transition(.opacity.combined(with: .scale(scale: 0.96)))
            }
        }
        .animation(.snappy(duration: 0.2), value: job.isRunning)
    }
}

// MARK: - Job chips

private struct JobChips: View {
    let console: ProcessConsole
    let selectedID: ProcessJob.ID?

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 2) {
                    ForEach(console.jobs) { job in
                        JobChip(job: job, selected: job.id == selectedID) {
                            withAnimation(.snappy(duration: 0.18)) { console.selectedJobID = job.id }
                        }
                        .id(job.id)
                    }
                }
                .padding(2)
                .background(Theme.well, in: .rect(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Theme.hairline))
            }
            .scrollClipDisabled(false)
            .frame(maxWidth: .infinity, alignment: .leading)
            .onChange(of: selectedID) { _, id in
                guard let id else { return }
                withAnimation(.snappy(duration: 0.2)) { proxy.scrollTo(id, anchor: .trailing) }
            }
        }
    }
}

private struct JobChip: View {
    let job: ProcessJob
    let selected: Bool
    let action: () -> Void
    @State private var hover = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                StateGlyph(state: job.state)
                Text(job.title)
                    .lineLimit(1)
                    .fixedSize()
            }
            .font(.system(size: 11.5, weight: selected ? .semibold : .medium))
            .foregroundStyle(selected ? Theme.textPrimary : Theme.textSecondary)
            .padding(.horizontal, 9)
            .frame(height: 24)
            .background {
                RoundedRectangle(cornerRadius: 6)
                    .fill(selected ? Theme.panelRaised : Color.white.opacity(hover ? 0.04 : 0))
            }
            .overlay {
                if selected { RoundedRectangle(cornerRadius: 6).strokeBorder(Theme.hairlineStrong) }
            }
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
        .animation(.easeOut(duration: 0.12), value: hover)
        .help(job.commandLine)
    }
}

private struct StateGlyph: View {
    let state: ProcessJob.State

    var body: some View {
        Group {
            switch state {
            case .running:
                LiveDot(color: Theme.accent, live: true, size: 6)
            case .succeeded:
                Image(systemName: "checkmark").foregroundStyle(Theme.ok)
            case .failed:
                Image(systemName: "xmark").foregroundStyle(Theme.critical)
            case .stopped:
                Image(systemName: "stop.fill").foregroundStyle(Theme.caution)
            }
        }
        .font(.system(size: 8.5, weight: .bold))
        .frame(width: 10, height: 10)
    }
}

// MARK: - Output

private struct ConsoleOutput: View {
    let job: ProcessJob
    @State private var following = true
    @State private var atBottom = true
    @State private var userScrolling = false

    var body: some View {
        let lines = job.lines
        VStack(spacing: 0) {
            CommandBar(command: job.commandLine, count: lines.count, state: job.state)
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        ForEach(lines) { line in
                            ConsoleRow(line: line)
                        }
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .textSelection(.enabled)
                }
                .scrollIndicators(.automatic)
                .onScrollGeometryChange(for: Bool.self) { g in
                    g.contentOffset.y + g.containerSize.height >= g.contentSize.height - 28
                } action: { _, bottom in
                    atBottom = bottom
                    if bottom { following = true }
                }
                .onScrollPhaseChange { old, new in
                    userScrolling = (new == .interacting || new == .decelerating)
                    if new == .idle, old == .interacting || old == .decelerating { following = atBottom }
                }
                .onAppear { if let last = lines.last { proxy.scrollTo(last.id, anchor: .bottom) } }
                .onChange(of: lines.last?.id) { _, id in
                    guard following, !userScrolling, let id else { return }
                    proxy.scrollTo(id, anchor: .bottom)
                }
                .overlay(alignment: .bottomTrailing) {
                    if !following, !lines.isEmpty {
                        Button {
                            following = true
                            if let last = lines.last {
                                withAnimation(.snappy(duration: 0.25)) { proxy.scrollTo(last.id, anchor: .bottom) }
                            }
                        } label: {
                            Label("Latest", systemImage: "arrow.down.to.line")
                        }
                        .buttonStyle(.secondary)
                        .background(Theme.panelRaised, in: .rect(cornerRadius: 8))
                        .padding(12)
                        .transition(.opacity)
                        .help("Jump to the newest output and keep following")
                    }
                }
                .animation(.easeOut(duration: 0.15), value: following)
            }
            .background(Theme.well)
            .overlay {
                if lines.isEmpty {
                    Text(job.isRunning ? "Waiting for output…" : "No output")
                        .font(Theme.mono(11.5))
                        .foregroundStyle(Theme.textTertiary)
                }
            }
        }
        .clipShape(UnevenRoundedRectangle(bottomLeadingRadius: Theme.radius - 1, bottomTrailingRadius: Theme.radius - 1))
    }
}

private struct CommandBar: View {
    let command: String
    let count: Int
    let state: ProcessJob.State

    var body: some View {
        HStack(spacing: 12) {
            Text("$")
                .foregroundStyle(Theme.textTertiary)
            Text(command)
                .foregroundStyle(Theme.textSecondary)
                .lineLimit(1)
                .truncationMode(.middle)
                .textSelection(.enabled)
            Spacer(minLength: 8)
            Text(stateText)
                .foregroundStyle(stateColor)
            Text("\(count) lines")
                .foregroundStyle(Theme.textTertiary)
                .contentTransition(.numericText())
                .frame(minWidth: 72, alignment: .trailing)
        }
        .font(Theme.mono(10.5))
        .monospacedDigit()
        .padding(.horizontal, 14)
        .frame(height: 26)
        .background(Theme.well)
        .overlay(alignment: .bottom) { Rectangle().fill(Theme.hairline).frame(height: 1) }
    }

    private var stateText: String {
        switch state {
        case .running: "RUNNING"
        case .succeeded: "EXIT 0"
        case .failed(let code): "EXIT \(code)"
        case .stopped: "STOPPED"
        }
    }

    private var stateColor: Color {
        switch state {
        case .running: Theme.accent
        case .succeeded: Theme.ok
        case .failed: Theme.critical
        case .stopped: Theme.caution
        }
    }
}

/// One output line. Splits a leading `HH:MM:SS` stamp into a dim gutter so the message column aligns.
private struct ConsoleRow: View {
    let line: ConsoleLine

    var body: some View {
        let (stamp, message) = Self.split(line.text)
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text(stamp)
                .foregroundStyle(Theme.textTertiary)
                .frame(width: 58, alignment: .leading)
            Text(message.isEmpty ? " " : message)
                .foregroundStyle(Self.color(for: line))
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .font(Theme.mono(11.5))
        .padding(.vertical, 1.5)
    }

    private static func split(_ text: String) -> (String, String) {
        let u = Array(text.utf8.prefix(9))
        guard u.count == 9, u[2] == 58, u[5] == 58, u[8] == 32,
              [0, 1, 3, 4, 6, 7].allSatisfy({ (48...57).contains(u[$0]) })
        else { return ("", text) }
        return (String(text.prefix(8)), String(text.dropFirst(9)))
    }

    private static func color(for line: ConsoleLine) -> Color {
        let t = line.text
        if t.contains("Traceback") || t.contains("ERROR") || t.contains("[error]") || t.contains("ABORT")
            || t.contains("NOT SAFE") || t.contains("PROBLEM") || t.contains("FAIL") { return Theme.critical }
        if t.contains("CONFIRMED") || t.contains("ALARM") { return Theme.accent }
        if t.contains("RESULT") || t.contains("PASS") || t.contains("[report]") || t.contains("landed")
            || t.contains("DONE") { return Theme.ok }
        if t.contains("WARNING") || t.hasPrefix("■") { return Theme.caution }
        if t.contains("[phase]") { return Theme.textPrimary }
        return Theme.textPrimary.opacity(line.isError ? 0.62 : 0.78)
    }
}

private struct ConsoleEmpty: View {
    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: "terminal")
                .font(.system(size: 18, weight: .regular))
                .foregroundStyle(Theme.textTertiary)
            Text("No commands yet")
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(Theme.textSecondary)
            Text("Output from simulations, flight tests and drone actions streams here.")
                .font(.system(size: 12))
                .foregroundStyle(Theme.textTertiary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.well)
        .clipShape(UnevenRoundedRectangle(bottomLeadingRadius: Theme.radius - 1, bottomTrailingRadius: Theme.radius - 1))
    }
}

#if DEBUG
/// Debug-only screenshot aid: `-consoleDemo /path/to/log` streams a log file into the console as a job,
/// `-consoleDemoRemote YES` marks it as a drone job (shows "Stop & land"). Never active without the launch argument.
@MainActor
enum ConsoleDemo {
    private static var started = false

    static func startIfRequested(_ console: ProcessConsole) {
        guard !started, let path = UserDefaults.standard.string(forKey: "consoleDemo") else { return }
        started = true
        console.run(title: "Hover 1.5 m (dry)", executable: URL(filePath: "/bin/echo"),
                    arguments: ["00:20:01 [hover] dry run: preflight OK, would climb to 1.50 m - not arming"])
        console.run(title: "Test connection", executable: URL(filePath: "/bin/sh"),
                    arguments: ["-c", "echo 'ssh: connect to host 10.42.0.1 port 22: Operation timed out' >&2; exit 255"])
        let job = console.run(title: "Simulation · Case 1 mission", executable: URL(filePath: "/usr/bin/tail"),
                              arguments: ["-n", "+1", "-f", path])
        if UserDefaults.standard.bool(forKey: "consoleDemoRemote") { job.remoteStop = {} }
    }
}
#endif
