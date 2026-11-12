import AppKit
import SwiftUI


enum Theme {
    // neutrals
    static let canvas = Color(hex: 0x0A0B0D)
    static let panel = Color(hex: 0x121418)
    static let panelRaised = Color(hex: 0x181B20)
    static let well = Color(hex: 0x0D0F12)
    static let hairline = Color.white.opacity(0.075)
    static let hairlineStrong = Color.white.opacity(0.14)
    static let textPrimary = Color(hex: 0xEDEFF2)
    static let textSecondary = Color(hex: 0x9097A3)
    static let textTertiary = Color(hex: 0x5C636E)

    // the one accent
    static let accent = Color(hex: 0xFF6A1F)
    // status
    static let ok = Color(hex: 0x32D74B)
    static let caution = Color(hex: 0xFFD60A)
    static let critical = Color(hex: 0xFF453A)
    // data lines (cool, low saturation - never competes with the accent)
    static let signal = Color(hex: 0x8FB4E8)

    // legacy names used across views -> mapped onto the restrained palette
    static let fire = accent
    static let ember = critical
    static let sky = signal
    static let mint = ok
    static let gold = caution
    static let violet = Color(hex: 0xB4B9C2)
    static let teal = signal

    static let radius: CGFloat = 14
    static let cardRadius: CGFloat = 14
    static let spacing: CGFloat = 16

    static func color(forObject name: String) -> Color {
        switch name.lowercased() {
        case "fire", "hotspot", "tree_fire": critical   // heat: thermal network (tree_fire = heat band around a tree)
        case "flame": accent                      // the flame lamp, seen by the camera model
        case "car", "truck": signal
        case "tree": ok
        default: textSecondary
        }
    }

    /// "tree_fire" -> "Tree fire"
    static func label(forObject name: String) -> String {
        let s = name.replacingOccurrences(of: "_", with: " ").lowercased()
        return s.prefix(1).uppercased() + s.dropFirst()
    }

    static func symbol(forObject name: String) -> String {
        switch name.lowercased() {
        case "fire", "hotspot", "tree_fire": "thermometer.high"
        case "flame": "flame.fill"
        case "smoke": "smoke.fill"
        case "car", "truck": "car.fill"
        case "tree": "tree.fill"
        default: "scope"
        }
    }

    static func color(for verdict: Verdict) -> Color {
        switch verdict {
        case .pass: ok
        case .fail: critical
        case .pending: textTertiary
        case .manual: caution
        }
    }

    static func color(forPhase phase: String) -> Color {
        switch phase.uppercased() {
        case "INSPECT": accent
        case "DONE": ok
        case "LAND", "RETURN", "ABORT": caution
        case "OFFLINE", "INIT": textTertiary
        default: textPrimary
        }
    }

    static let mono = mono(12)
    /// Numbers: SF Pro with tabular digits, so values don't jitter while they update.
    static func mono(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font { .system(size: size, weight: weight).monospacedDigit() }
    /// Commands, file names and console output.
    static func code(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font { .system(size: size, weight: weight, design: .monospaced) }
}

extension Color {
    init(hex: UInt32, opacity: Double = 1) {
        self.init(.sRGB, red: Double((hex >> 16) & 0xFF) / 255, green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255, opacity: opacity)
    }
}

// MARK: - Surfaces

/// Battery colour and symbol by level, shared by every place that shows it.
enum BatteryLevel {
    static func tint(_ percent: Double?) -> Color {
        guard let percent else { return Theme.textPrimary }
        return percent < 20 ? Theme.critical : percent < 35 ? Theme.caution : Theme.ok
    }
    static func symbol(_ percent: Double?) -> String {
        guard let percent else { return "battery.0percent" }
        return percent < 13 ? "battery.0percent" : percent < 38 ? "battery.25percent" : percent < 63 ? "battery.50percent"
            : percent < 88 ? "battery.75percent" : "battery.100percent"
    }
}

/// Compact battery read-out: icon, percent, pack voltage on hover.
struct BatteryBadge: View {
    @Environment(AppModel.self) private var model
    var large = false

    var body: some View {
        let b = model.battery
        if let p = b.percent {
            HStack(spacing: large ? 6 : 5) {
                Image(systemName: BatteryLevel.symbol(p))
                    .font(.system(size: large ? 15 : 12, weight: .medium))
                    .foregroundStyle(BatteryLevel.tint(p))
                Text(String(format: "%.0f%%", p))
                    .font(Theme.mono(large ? 13 : 11.5, .semibold))
                    .foregroundStyle(p < 35 ? BatteryLevel.tint(p) : Theme.textPrimary)
            }
            .help(b.voltage.map { String(format: "Drone battery: %.1f V (%.2f V per cell)", $0, $0 / 6) } ?? "Drone battery")
            .accessibilityLabel(String(format: "Drone battery %.0f percent", p))
        }
    }
}

struct GlassCard<Content: View>: View {
    var padding: CGFloat = 18
    var tint: Color?
    @ViewBuilder var content: Content

    var body: some View {
        content
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .background(Theme.panel, in: .rect(cornerRadius: Theme.radius))
            .overlay(RoundedRectangle(cornerRadius: Theme.radius).strokeBorder(Theme.hairline))
    }
}

struct Eyebrow: View {
    let text: String
    var body: some View {
        Text(text)
            .font(.system(size: 11.5, weight: .medium))
            .foregroundStyle(Theme.textSecondary)
    }
}

struct CardHeader: View {
    let title: String
    var symbol: String?
    var tint: Color = Theme.textTertiary
    var trailing: AnyView?

    var body: some View {
        HStack(spacing: 7) {
            Text(title)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Theme.textPrimary)
                .lineLimit(1)
            Spacer(minLength: 8)
            trailing
        }
        .frame(minHeight: 22)
    }
}

/// Instrument readout: label, big monospaced value + unit, optional footnote.
struct StatTile: View {
    let title: String
    let value: String
    var unit: String?
    var symbol: String
    var tint: Color = Theme.textPrimary
    var footnote: String?
    var emphasis = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Eyebrow(text: title)
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text(value)
                    .font(.system(size: 24, weight: .semibold).monospacedDigit())
                    .foregroundStyle(emphasis ? tint : Theme.textPrimary)
                    .monospacedDigit()
                    .lineLimit(1)
                    .minimumScaleFactor(0.55)
                if let unit {
                    Text(unit).font(.system(size: 12, weight: .medium)).foregroundStyle(Theme.textSecondary)
                }
            }
            if let footnote {
                Text(footnote).font(.system(size: 11)).foregroundStyle(Theme.textTertiary).lineLimit(1)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.panel, in: .rect(cornerRadius: Theme.radius))
        .overlay(RoundedRectangle(cornerRadius: Theme.radius).strokeBorder(Theme.hairline))
        .overlay(alignment: .leading) {
            if emphasis { Capsule().fill(tint).frame(width: 2.5).padding(.vertical, 14) }
        }
        .accessibilityElement(children: .combine)
    }
}


struct StatusPill: View {
    let text: String
    var color: Color
    var symbol: String?
    var pulsing = false

    var body: some View {
        HStack(spacing: 6) {
            if let symbol {
                Image(systemName: symbol).font(.system(size: 9, weight: .bold))
            } else {
                LiveDot(color: color, live: pulsing)
            }
            Text(text)
                .font(.system(size: 11, weight: .medium))
                .lineLimit(1)
        }
        .foregroundStyle(color)
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(color.opacity(0.12), in: .capsule)
    }
}

/// A status dot with an expanding ring while live. The ring runs in Core Animation, so it costs no app CPU.
struct LiveDot: View {
    let color: Color
    var live = false
    var size: CGFloat = 6
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        Circle()
            .fill(color)
            .frame(width: size, height: size)
            .background {
                if live && !reduceMotion { PulseRing(color: NSColor(color)) }
            }
    }
}

private struct PulseRing: NSViewRepresentable {
    let color: NSColor

    func makeNSView(context: Context) -> RingView { RingView() }
    func updateNSView(_ view: RingView, context: Context) { view.ring.strokeColor = color.cgColor }

    final class RingView: NSView {
        let ring = CAShapeLayer()

        override init(frame: NSRect) {
            super.init(frame: frame)
            wantsLayer = true
            ring.fillColor = nil
            ring.lineWidth = 1
            layer?.addSublayer(ring)
            let scale = CABasicAnimation(keyPath: "transform.scale")
            scale.fromValue = 1
            scale.toValue = 2.6
            let fade = CABasicAnimation(keyPath: "opacity")
            fade.fromValue = 0.7
            fade.toValue = 0
            let pulse = CAAnimationGroup()
            pulse.animations = [scale, fade]
            pulse.duration = 1.6
            pulse.timingFunction = CAMediaTimingFunction(name: .easeOut)
            pulse.repeatCount = .infinity
            pulse.isRemovedOnCompletion = false
            ring.add(pulse, forKey: "pulse")
        }

        required init?(coder: NSCoder) { nil }

        override func layout() {
            super.layout()
            ring.frame = bounds
            ring.path = CGPath(ellipseIn: bounds.insetBy(dx: 0.5, dy: 0.5), transform: nil)
        }

        override func hitTest(_ point: NSPoint) -> NSView? { nil }
    }
}

// MARK: - Page scaffold

struct PageHeader: View {
    let section: AppSection
    var trailing: AnyView?

    var body: some View {
        HStack(alignment: .lastTextBaseline, spacing: 14) {
            Text(section.title)
                .font(.system(size: 22, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            Spacer()
            trailing
        }
        .padding(.bottom, 6)
    }
}

struct Page<Content: View>: View {
    let section: AppSection
    var trailing: AnyView?
    @ViewBuilder var content: Content

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.spacing) {
                PageHeader(section: section, trailing: trailing)
                content
            }
            .padding(.horizontal, 28)
            .padding(.top, 18)
            .padding(.bottom, 28)
            .frame(maxWidth: 1640)
            .frame(maxWidth: .infinity)
        }
        .scrollEdgeEffectStyle(.soft, for: .top)
        .background(Theme.canvas)
    }
}

extension View {
    func eraseToAnyView() -> AnyView { AnyView(self) }
}
