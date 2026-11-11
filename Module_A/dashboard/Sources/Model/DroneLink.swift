import Foundation

/// SSH access to the drone's Orange Pi. Uses key authentication (set up once with `pair`) so commands run
/// without a password prompt; a control socket keeps one connection open for fast repeated commands.
@MainActor
struct DroneLink {
    let settings: DashboardSettings
    let console: ProcessConsole

    static let ssh = URL(filePath: "/usr/bin/ssh")
    static let rosEnv = "source /opt/ros/noetic/setup.bash; source ~/technic_ws/devel/setup.bash"

    /// Key login if this Mac is paired, otherwise the password from Settings (answered by `askpass`, never typed).
    static let sshOptions: [String] = [
        "-o", "ConnectTimeout=6", "-o", "StrictHostKeyChecking=accept-new",
        "-o", "PreferredAuthentications=publickey,password", "-o", "NumberOfPasswordPrompts=1",
        "-o", "ServerAliveInterval=5", "-o", "ControlMaster=auto", "-o", "ControlPersist=10m",
        "-o", "ControlPath=/tmp/brics-dash-%C"]
    private var sshOptions: [String] { Self.sshOptions }

    /// Environment that makes ssh / scp / rsync take the password from Settings without a terminal.
    static func sshEnvironment(password: String) -> [String: String] {
        let helper = FileManager.default.temporaryDirectory.appending(path: "brics-askpass.sh")
        let path = helper.path(percentEncoded: false)
        if !FileManager.default.fileExists(atPath: path) {
            try? "#!/bin/sh\nprintf '%s\\n' \"$BRICS_SSH_PASSWORD\"\n".write(to: helper, atomically: true, encoding: .utf8)
            try? FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: path)
        }
        return ["SSH_ASKPASS": path, "SSH_ASKPASS_REQUIRE": "force", "BRICS_SSH_PASSWORD": password, "DISPLAY": ":0",
                "SSH_OPTS": sshOptions.joined(separator: " ")]
    }
    private var sshEnv: [String: String] { Self.sshEnvironment(password: settings.sshPassword) }

    /// Runs a remote shell command and streams its output into the console.
    @discardableResult
    func run(_ title: String, remote: String) -> ProcessJob {
        console.run(title: title, executable: Self.ssh, arguments: sshOptions + [settings.sshTarget, remote], environment: sshEnv)
    }

    /// Copies one script from tools/ to ~/ on the drone, then runs it - always the current version, one click.
    @discardableResult
    func copyAndRunScript(_ title: String, toolkit: URL, script: String, args: [String]) -> ProcessJob {
        let local = toolkit.appending(path: "tools/\(script)").path(percentEncoded: false)
        let quoted = args.map { "'\($0.replacingOccurrences(of: "'", with: ""))'" }.joined(separator: " ")
        let remote = "\(Self.rosEnv); cd ~; echo $$ > /tmp/brics_job.pid; exec python3 -u \(script) \(quoted)"
        let job = console.run(title: title, executable: URL(filePath: "/bin/bash"),
                              arguments: ["-c", "scp -q $SSH_OPTS \"$1\" \"$2:~/\" && exec ssh $SSH_OPTS \"$2\" \"$3\"", "bash",
                                          local, settings.sshTarget, remote],
                              environment: sshEnv)
        attachRemoteStop(job)
        return job
    }

    private func attachRemoteStop(_ job: ProcessJob) {
        let target = settings.sshTarget, opts = sshOptions, env = sshEnv
        job.remoteStop = {
            let p = Process()
            p.executableURL = DroneLink.ssh
            p.arguments = opts + [target, "kill -INT $(cat /tmp/brics_job.pid) 2>/dev/null; true"]
            p.environment = ProcessInfo.processInfo.environment.merging(env) { _, new in new }
            p.standardInput = FileHandle.nullDevice
            try? p.run()
        }
    }

    /// Runs a Python flight/bench script on the drone. Its PID is stored so Stop can send SIGINT:
    /// every script treats Ctrl+C as "land now", never as "cut motors".
    @discardableResult
    func runScript(_ title: String, script: String, args: [String]) -> ProcessJob {
        let quoted = args.map { "'\($0.replacingOccurrences(of: "'", with: ""))'" }.joined(separator: " ")
        let remote = "\(Self.rosEnv); cd ~; echo $$ > /tmp/brics_job.pid; exec python3 -u \(script) \(quoted)"
        let job = run(title, remote: remote)
        attachRemoteStop(job)
        return job
    }

    /// Runs the final Case 1 mission on the drone: one click, no second Start. The script checks the drone
    /// (pre-flight), counts down 3 s (ABORT cancels), then arms, takes off and flies the mission.
    /// Runs the final Case 1 mission through tools/run_mission.sh: any older mission script still running on the
    /// ground is stopped first (never one that is flying), then the new one starts with `settings`
    /// (`--set KEY=VALUE` from the Mission settings sheet). Each argument is single-quoted for the remote shell.
    @discardableResult
    func launchMission(settings extra: [String] = []) -> ProcessJob {
        let quoted = extra.map { "'\($0.replacingOccurrences(of: "'", with: ""))'" }.joined(separator: " ")
        let job = run("Case 1 mission (drone)", remote: "\(Self.rosEnv); cd ~/brics_toolkit && if [ ! -f tools/run_mission.sh ] || [ ! -f common/mission_settings.py ]; then echo 'OLD MISSION CODE ON THE DRONE - press Deploy toolkit to drone (Flight Tests page), then Run mission again. Nothing was flown.'; exit 3; fi; echo $$ > /tmp/brics_job.pid; exec bash tools/run_mission.sh \(quoted)")
        attachRemoteStop(job)
        return job
    }

    /// Emergency: ask the TECHNIC software to land right now (independent of any script).
    func landNow() {
        run("LAND NOW", remote: "\(Self.rosEnv); rosservice call /land '{}'")
    }

    /// Copies the flight scripts to ~/ on the drone (where the run buttons expect them).
    func syncScripts(toolkit: URL) {
        let tools = ["hover_test.py", "motor_ramp_test.py", "aruco_roam_test.py", "aruco_scan.py", "thermal_probe.py"]
            .map { toolkit.appending(path: "tools/\($0)").path(percentEncoded: false) }
        console.run(title: "Copy flight scripts to drone", executable: URL(filePath: "/usr/bin/scp"),
                    arguments: sshOptions + tools + ["\(settings.sshTarget):~/"], environment: sshEnv)
    }

    func deployToolkit(toolkit: URL) {
        console.run(title: "Deploy toolkit to drone", executable: URL(filePath: "/bin/bash"),
                    arguments: [toolkit.appending(path: "setup/deploy_to_drone.sh").path(percentEncoded: false)],
                    workingDirectory: toolkit, environment: sshEnv.merging(["DRONE": settings.droneHost, "DUSER": settings.sshUser]) { _, new in new })
    }

    func fetchResults(toolkit: URL) {
        let dest = toolkit.appending(path: "runs").path(percentEncoded: false)
        console.run(title: "Copy flight logs from drone", executable: URL(filePath: "/bin/bash"),
                    arguments: ["-c", "mkdir -p '\(dest)/flight_logs' && scp \(sshOptions.joined(separator: " ")) -r '\(settings.sshTarget):~/flight_logs/*' '\(dest)/flight_logs/' ; scp \(sshOptions.joined(separator: " ")) -r '\(settings.sshTarget):~/brics_toolkit/runs/*' '\(dest)/' 2>/dev/null; echo done"],
                    environment: sshEnv)
    }

    func syncClock() {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "UTC")
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        run("Sync drone clock", remote: "echo '\(settings.sshPassword.replacingOccurrences(of: "'", with: ""))' | sudo -S date -u -s '\(f.string(from: .now))'")
    }

    /// One-time: create an SSH key if needed and install it on the drone using the default TECHNIC password.
    func pair(password: String) {
        let key = FileManager.default.homeDirectoryForCurrentUser.appending(path: ".ssh/id_ed25519").path(percentEncoded: false)
        let script = """
        set timeout 25
        if {![file exists "\(key)"]} { exec ssh-keygen -t ed25519 -N "" -f "\(key)" }
        spawn ssh-copy-id -o StrictHostKeyChecking=accept-new -i "\(key).pub" \(settings.sshTarget)
        expect {
          -re "assword:" { send "\(password)\\r"; exp_continue }
          eof
        }
        """
        console.run(title: "Pair with drone (SSH key)", executable: URL(filePath: "/usr/bin/expect"), arguments: ["-c", script])
    }

    func testConnection() {
        run("Test drone connection", remote: "echo connected to $(hostname); uptime; \(Self.rosEnv); rosservice call /get_telemetry \"frame_id: 'aruco_map'\" | head -12")
    }
}
