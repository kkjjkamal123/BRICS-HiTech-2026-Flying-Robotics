import Foundation
import Network
import os

/// "Is something listening on host:port?" - a plain TCP connect with a short timeout.
/// Used to tell apart "wrong address / drone not on this network" from "drone is there, mission just not running".
enum PortProbe {
    static func isOpen(host: String, port: Int, timeout: Double = 2.5) async -> Bool {
        guard !host.isEmpty, let p = NWEndpoint.Port(rawValue: UInt16(clamping: port)) else { return false }
        let connection = NWConnection(host: NWEndpoint.Host(host), port: p, using: .tcp)
        let queue = DispatchQueue(label: "brics.portprobe")
        let finished = OSAllocatedUnfairLock(initialState: false)
        return await withCheckedContinuation { (continuation: CheckedContinuation<Bool, Never>) in
            let finish: @Sendable (Bool) -> Void = { open in
                let first = finished.withLock { done -> Bool in
                    if done { return false }
                    done = true
                    return true
                }
                guard first else { return }
                connection.stateUpdateHandler = nil
                connection.cancel()
                continuation.resume(returning: open)
            }
            connection.stateUpdateHandler = { state in
                switch state {
                case .ready: finish(true)
                case .failed, .cancelled: finish(false)
                default: break          // .waiting keeps retrying until the timeout below
                }
            }
            queue.asyncAfter(deadline: .now() + timeout) { finish(false) }
            connection.start(queue: queue)
        }
    }
}
