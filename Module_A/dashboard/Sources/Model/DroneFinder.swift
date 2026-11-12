import Foundation

/// Finds the drone on the Wi-Fi this Mac is on, when its address has changed (the venue Wi-Fi hands out a new
/// one after a reboot or reconnect: .195, .198, .199, .203, .213 ... on 11 Nov).
/// Signature: the drone's web_video_server (port 8080) lists the topic /main_camera on its index page.
enum DroneFinder {
    /// Local IPv4 networks (address, netmask) of this Mac's Wi-Fi / Ethernet, VPN tunnels and loopback left out.
    static func localNetworks() -> [(ip: UInt32, mask: UInt32)] {
        var out: [(UInt32, UInt32)] = []
        var list: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&list) == 0, let first = list else { return out }
        defer { freeifaddrs(list) }
        for p in sequence(first: first, next: { $0.pointee.ifa_next }) {
            let ifa = p.pointee
            let name = String(cString: ifa.ifa_name)
            guard let a = ifa.ifa_addr, let m = ifa.ifa_netmask, a.pointee.sa_family == UInt8(AF_INET),
                  name.hasPrefix("en") || name.hasPrefix("bridge") else { continue }
            let ip = a.withMemoryRebound(to: sockaddr_in.self, capacity: 1) { UInt32(bigEndian: $0.pointee.sin_addr.s_addr) }
            let mask = m.withMemoryRebound(to: sockaddr_in.self, capacity: 1) { UInt32(bigEndian: $0.pointee.sin_addr.s_addr) }
            if ip >> 24 == 169 { continue }                                  // self-assigned, no DHCP
            out.append((ip, mask))
        }
        return out
    }

    static func dotted(_ v: UInt32) -> String { "\(v >> 24).\((v >> 16) & 255).\((v >> 8) & 255).\(v & 255)" }

    /// Addresses to try: every host of each local network, at most a /22 (1022 hosts), the given hint first.
    static func candidates(hint: [String]) -> [String] {
        var hosts: [String] = []
        for (ip, mask) in localNetworks() {
            let m = max(mask, 0xFFFF_FC00)                                     // never scan more than a /22
            let net = ip & m, bcast = net | ~m
            guard bcast > net + 1 else { continue }
            for h in (net + 1)..<bcast where h != ip { hosts.append(dotted(h)) }
        }
        // each address once: the saved address is also in the recent list, and two interfaces can share a subnet
        var seen = Set<String>(), out: [String] = []
        for h in hint.filter({ hosts.contains($0) }) + hosts where seen.insert(h).inserted { out.append(h) }
        return out
    }

    /// True when http://host:port/ is the drone's video server.
    static func isDrone(host: String, port: Int, timeout: Double = 1.5) async -> Bool {
        guard await PortProbe.isOpen(host: host, port: port, timeout: timeout),
              let url = URL(string: "http://\(host):\(port)/") else { return false }
        var req = URLRequest(url: url, timeoutInterval: timeout + 1.5)
        req.cachePolicy = .reloadIgnoringLocalCacheData
        guard let (data, _) = try? await URLSession.shared.data(for: req) else { return false }
        return String(decoding: data.prefix(200_000), as: UTF8.self).contains("main_camera")
    }

    /// Every drone found on the local networks. `progress(done, total)` is called on the main actor.
    static func search(videoPort: Int, hint: [String],
                       progress: @MainActor @escaping (Int, Int) -> Void) async -> [String] {
        let hosts = candidates(hint: hint)
        let total = hosts.count
        var found: [String] = []
        var done = 0
        await withTaskGroup(of: (String, Bool).self) { group in
            var next = 0
            func addOne() {
                guard next < hosts.count else { return }
                let h = hosts[next]; next += 1
                group.addTask { (h, await isDrone(host: h, port: videoPort)) }
            }
            for _ in 0..<min(64, hosts.count) { addOne() }                   // 64 at a time: a /24 takes ~5 s
            for await (h, ok) in group {
                done += 1
                if ok { found.append(h) }
                let d = done
                await progress(d, total)
                addOne()
            }
        }
        let order = Dictionary(hosts.enumerated().map { ($1, $0) }, uniquingKeysWith: { first, _ in first })
        return found.sorted { (order[$0] ?? 0) < (order[$1] ?? 0) }
    }
}
