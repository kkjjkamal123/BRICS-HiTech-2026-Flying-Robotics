import AppKit
import SwiftUI

enum ThemeName: String, CaseIterable, Identifiable {
    case ember, arctic, aurora, orchid, crimson, graphite

    var id: String { rawValue }
    var title: String { rawValue.capitalized }

    var accent: Color {
        switch self {
        case .ember: Color(hex: 0xFF6A1F)
        case .arctic: Color(hex: 0x3FA9FF)
        case .aurora: Color(hex: 0x2FD39A)
        case .orchid: Color(hex: 0xB07CFF)
        case .crimson: Color(hex: 0xFF3B5C)
        case .graphite: Color(hex: 0xD9DDE3)
        }
    }

    var signal: Color {
        switch self {
        case .arctic: Color(hex: 0x9ADBFF)
        case .aurora: Color(hex: 0x8FE3D0)
        case .orchid: Color(hex: 0xC9B6FF)
        default: Color(hex: 0x8FB4E8)
        }
    }

    /// Colours of the moving light behind the glass.
    var glow: [NSColor] {
        switch self {
        case .ember: [NSColor(hex: 0xFF6A1F), NSColor(hex: 0xC2185B), NSColor(hex: 0xFFB020)]
        case .arctic: [NSColor(hex: 0x1E6BFF), NSColor(hex: 0x00C2D1), NSColor(hex: 0x6A4CFF)]
        case .aurora: [NSColor(hex: 0x00B37A), NSColor(hex: 0x1E8CFF), NSColor(hex: 0x7DFFB0)]
        case .orchid: [NSColor(hex: 0x8A3FFC), NSColor(hex: 0xFF4FA3), NSColor(hex: 0x3F6BFF)]
        case .crimson: [NSColor(hex: 0xE0123A), NSColor(hex: 0xFF7A00), NSColor(hex: 0x8B0FFF)]
        case .graphite: [NSColor(hex: 0x5A6472), NSColor(hex: 0x2E3440), NSColor(hex: 0x8892A0)]
        }
    }
}

enum SurfaceStyle: String, CaseIterable, Identifiable {
    case solid, glass, aurora

    var id: String { rawValue }
    var title: String { rawValue.capitalized }
    var detail: String {
        switch self {
        case .solid: "Opaque panels, highest contrast."
        case .glass: "Liquid Glass over the desktop."
        case .aurora: "Liquid Glass over moving light."
        }
    }
}

enum MissionLayout: String, CaseIterable, Identifiable {
    case split, video, map

    var id: String { rawValue }
    var title: String {
        switch self {
        case .split: "Split"
        case .video: "Video"
        case .map: "Map"
        }
    }
    var symbol: String {
        switch self {
        case .split: "rectangle.split.2x1"
        case .video: "video"
        case .map: "map"
        }
    }
}

/// Look-and-feel choices. Views read them through `Theme`, so a change redraws only what uses them.
@Observable
final class Appearance: @unchecked Sendable {
    nonisolated(unsafe) static let shared = Appearance()

    var theme: ThemeName { didSet { save(theme.rawValue, "theme") } }
    var surface: SurfaceStyle { didSet { save(surface.rawValue, "surface") } }
    var missionLayout: MissionLayout { didSet { save(missionLayout.rawValue, "missionLayout") } }
    var animatedBackground: Bool { didSet { save(animatedBackground, "animatedBackground") } }
    var pageAnimations: Bool { didSet { save(pageAnimations, "pageAnimations") } }

    var glass: Bool { surface != .solid }

    private init() {
        let d = UserDefaults.standard
        theme = ThemeName(rawValue: d.string(forKey: "theme") ?? "") ?? .ember
        surface = SurfaceStyle(rawValue: d.string(forKey: "surface") ?? "") ?? .solid
        missionLayout = MissionLayout(rawValue: d.string(forKey: "missionLayout") ?? "") ?? .split
        animatedBackground = d.object(forKey: "animatedBackground") as? Bool ?? true
        pageAnimations = d.object(forKey: "pageAnimations") as? Bool ?? true
    }

    private func save(_ value: Any, _ key: String) { UserDefaults.standard.set(value, forKey: key) }
}

extension NSColor {
    convenience init(hex: UInt32) {
        self.init(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
                  blue: CGFloat(hex & 0xFF) / 255, alpha: 1)
    }
}

// MARK: - Window backdrop

/// Behind the content: nothing for Solid, the blurred desktop for Glass, slow drifting light for Aurora.
struct WindowBackdrop: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        let a = Appearance.shared
        switch a.surface {
        case .solid:
            Theme.canvas
        case .glass:
            DesktopBlur()
                .overlay(Color.black.opacity(0.45))
        case .aurora:
            AuroraLayer(colors: a.theme.glow, moving: a.animatedBackground && !reduceMotion)
                .id(a.theme)
                .transition(.opacity)
        }
    }
}

private struct DesktopBlur: NSViewRepresentable {
    func makeNSView(context: Context) -> NSVisualEffectView {
        let v = NSVisualEffectView()
        v.blendingMode = .behindWindow
        v.material = .hudWindow
        v.state = .active
        return v
    }
    func updateNSView(_ view: NSVisualEffectView, context: Context) {}
}

/// Soft radial lights. The drift is a Core Animation loop, so the app itself does no per-frame work.
private struct AuroraLayer: NSViewRepresentable {
    let colors: [NSColor]
    let moving: Bool

    func makeNSView(context: Context) -> AuroraView { AuroraView(colors: colors) }
    func updateNSView(_ view: AuroraView, context: Context) { view.setMoving(moving) }

    final class AuroraView: NSView {
        private var blobs: [CAGradientLayer] = []
        private var moving = false

        init(colors: [NSColor]) {
            super.init(frame: .zero)
            wantsLayer = true
            layer?.backgroundColor = NSColor(hex: 0x07080A).cgColor
            for (i, c) in colors.enumerated() {
                let g = CAGradientLayer()
                g.type = .radial
                g.colors = [c.withAlphaComponent(i == 0 ? 0.42 : 0.32).cgColor, c.withAlphaComponent(0).cgColor]
                g.startPoint = CGPoint(x: 0.5, y: 0.5)
                g.endPoint = CGPoint(x: 1, y: 1)
                layer?.addSublayer(g)
                blobs.append(g)
            }
        }

        required init?(coder: NSCoder) { nil }

        override func hitTest(_ point: NSPoint) -> NSView? { nil }

        // Anchor points as fractions of the window, and how far each light wanders.
        private let anchors: [(CGPoint, CGVector, CFTimeInterval)] = [
            (CGPoint(x: 0.18, y: 0.82), CGVector(dx: 0.22, dy: -0.18), 23),
            (CGPoint(x: 0.85, y: 0.25), CGVector(dx: -0.25, dy: 0.2), 29),
            (CGPoint(x: 0.6, y: 0.95), CGVector(dx: -0.15, dy: -0.3), 37),
        ]

        override func layout() {
            super.layout()
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            let side = max(bounds.width, bounds.height) * 0.95
            for (i, g) in blobs.enumerated() {
                let (p, _, _) = anchors[i % anchors.count]
                g.bounds = CGRect(x: 0, y: 0, width: side, height: side)
                g.position = CGPoint(x: bounds.width * p.x, y: bounds.height * p.y)
            }
            CATransaction.commit()
            restart()
        }

        func setMoving(_ on: Bool) {
            guard on != moving else { return }
            moving = on
            restart()
        }

        private func restart() {
            for (i, g) in blobs.enumerated() {
                g.removeAnimation(forKey: "drift")
                guard moving else { continue }
                let (_, d, t) = anchors[i % anchors.count]
                let drift = CABasicAnimation(keyPath: "position")
                drift.byValue = NSValue(point: NSPoint(x: bounds.width * d.dx, y: bounds.height * d.dy))
                drift.duration = t
                drift.autoreverses = true
                drift.repeatCount = .infinity
                drift.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
                g.add(drift, forKey: "drift")
            }
        }
    }
}

// MARK: - Motion

/// Fades and lifts a page's blocks in one after another when the page opens.
struct Rise: ViewModifier {
    let index: Int
    @State private var shown = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        content
            .opacity(shown ? 1 : 0)
            .offset(y: shown ? 0 : 14)
            .onAppear {
                guard !shown else { return }
                guard Appearance.shared.pageAnimations, !reduceMotion else { shown = true; return }
                withAnimation(.smooth(duration: 0.5).delay(min(Double(index), 8) * 0.05)) { shown = true }
            }
    }
}

// MARK: - Pickers

/// Toolbar menu: theme, surface and layout without opening Settings.
struct AppearanceMenu: View {
    var body: some View {
        let a = Appearance.shared
        Menu {
            Picker("Theme", selection: binding(\.theme)) {
                ForEach(ThemeName.allCases) { Text($0.title).tag($0) }
            }
            Picker("Surface", selection: binding(\.surface)) {
                ForEach(SurfaceStyle.allCases) { Text($0.title).tag($0) }
            }
            Divider()
            SettingsLink { Text("Appearance Settings…") }
        } label: {
            Label("Appearance", systemImage: "paintpalette")
        }
        .help("Theme: \(a.theme.title) · \(a.surface.title)")
    }

    private func binding<T>(_ key: ReferenceWritableKeyPath<Appearance, T>) -> Binding<T> {
        Binding(get: { Appearance.shared[keyPath: key] },
                set: { v in withAnimation(.smooth(duration: 0.45)) { Appearance.shared[keyPath: key] = v } })
    }
}

struct AppearanceSettings: View {
    var body: some View {
        let a = Appearance.shared
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                group("Theme") {
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 10), count: 3), spacing: 10) {
                        ForEach(ThemeName.allCases) { t in
                            Tile(selected: a.theme == t, action: { set(\.theme, t) }) {
                                ThemeSwatch(theme: t)
                            } caption: {
                                Text(t.title)
                            }
                        }
                    }
                }
                group("Surface") {
                    HStack(spacing: 10) {
                        ForEach(SurfaceStyle.allCases) { s in
                            Tile(selected: a.surface == s, action: { set(\.surface, s) }) {
                                SurfacePreview(style: s, theme: a.theme)
                            } caption: {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(s.title)
                                    Text(s.detail).font(.system(size: 10.5)).foregroundStyle(Theme.textTertiary)
                                        .lineLimit(2, reservesSpace: true)
                                }
                            }
                        }
                    }
                }
                group("Mission Control layout") {
                    HStack(spacing: 10) {
                        ForEach(MissionLayout.allCases) { l in
                            Tile(selected: a.missionLayout == l, action: { set(\.missionLayout, l) }) {
                                LayoutPreview(layout: l)
                            } caption: {
                                Label(l.title, systemImage: l.symbol)
                            }
                        }
                    }
                }
                group("Motion") {
                    VStack(alignment: .leading, spacing: 8) {
                        Toggle("Moving light behind Aurora glass", isOn: Binding(get: { a.animatedBackground }, set: { a.animatedBackground = $0 }))
                        Toggle("Animate pages as they open", isOn: Binding(get: { a.pageAnimations }, set: { a.pageAnimations = $0 }))
                        Text("Both follow Reduce Motion in System Settings. The moving light runs in Core Animation and costs no app CPU.")
                            .font(.system(size: 11)).foregroundStyle(Theme.textTertiary)
                    }
                }
            }
            .padding(24)
        }
    }

    private func set<T>(_ key: ReferenceWritableKeyPath<Appearance, T>, _ value: T) {
        withAnimation(.smooth(duration: 0.45)) { Appearance.shared[keyPath: key] = value }
    }

    private func group<C: View>(_ title: String, @ViewBuilder _ content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(.system(size: 13, weight: .semibold))
            content()
        }
    }
}

private struct Tile<Preview: View, Caption: View>: View {
    let selected: Bool
    let action: () -> Void
    @ViewBuilder var preview: Preview
    @ViewBuilder var caption: Caption
    @State private var hover = false

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 8) {
                preview
                    .frame(height: 72)
                    .frame(maxWidth: .infinity)
                    .clipShape(.rect(cornerRadius: 8))
                caption
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(Theme.textPrimary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(8)
            .background(Color.white.opacity(hover ? 0.06 : 0.03), in: .rect(cornerRadius: 12))
            .overlay {
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(selected ? Theme.accent : Theme.hairline, lineWidth: selected ? 2 : 1)
            }
            .scaleEffect(hover ? 1.02 : 1)
            .animation(.spring(duration: 0.3, bounce: 0.35), value: hover)
            .animation(.smooth(duration: 0.3), value: selected)
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
    }
}

private struct ThemeSwatch: View {
    let theme: ThemeName

    var body: some View {
        let g = theme.glow.map { Color(nsColor: $0) }
        ZStack(alignment: .bottomLeading) {
            Color(hex: 0x07080A)
            RadialGradient(colors: [g[0].opacity(0.8), .clear], center: .topLeading, startRadius: 0, endRadius: 90)
            RadialGradient(colors: [g[1].opacity(0.7), .clear], center: .bottomTrailing, startRadius: 0, endRadius: 90)
            HStack(spacing: 5) {
                Circle().fill(theme.accent).frame(width: 12, height: 12)
                Capsule().fill(theme.signal.opacity(0.8)).frame(width: 34, height: 5)
            }
            .padding(9)
        }
    }
}

private struct SurfacePreview: View {
    let style: SurfaceStyle
    let theme: ThemeName

    var body: some View {
        ZStack {
            switch style {
            case .solid: Color(hex: 0x0A0B0D)
            case .glass: LinearGradient(colors: [Color(hex: 0x3A4250), Color(hex: 0x1A1E24)], startPoint: .topLeading, endPoint: .bottomTrailing)
            case .aurora: ThemeSwatch(theme: theme)
            }
            HStack(spacing: 6) {
                ForEach(0..<2, id: \.self) { _ in
                    RoundedRectangle(cornerRadius: 6)
                        .fill(style == .solid ? Color(hex: 0x181B20) : Color.white.opacity(0.12))
                        .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(.white.opacity(style == .solid ? 0.08 : 0.25), lineWidth: 0.75))
                }
            }
            .padding(12)
        }
    }
}

private struct LayoutPreview: View {
    let layout: MissionLayout

    var body: some View {
        let a = Theme.accent.opacity(0.55), b = Color.white.opacity(0.14)
        ZStack {
            Color(hex: 0x0A0B0D)
            Group {
                switch layout {
                case .split:
                    VStack(spacing: 4) {
                        HStack(spacing: 4) { RoundedRectangle(cornerRadius: 3).fill(a); RoundedRectangle(cornerRadius: 3).fill(b).frame(width: 34) }
                        RoundedRectangle(cornerRadius: 3).fill(b).frame(height: 10)
                    }
                case .video:
                    VStack(spacing: 4) {
                        RoundedRectangle(cornerRadius: 3).fill(a).overlay(Image(systemName: "video").font(.system(size: 14)).foregroundStyle(.white.opacity(0.7)))
                        HStack(spacing: 4) { RoundedRectangle(cornerRadius: 3).fill(b); RoundedRectangle(cornerRadius: 3).fill(b).frame(width: 30) }.frame(height: 14)
                    }
                case .map:
                    VStack(spacing: 4) {
                        RoundedRectangle(cornerRadius: 3).fill(a).overlay(Image(systemName: "map").font(.system(size: 14)).foregroundStyle(.white.opacity(0.7)))
                        HStack(spacing: 4) { RoundedRectangle(cornerRadius: 3).fill(b); RoundedRectangle(cornerRadius: 3).fill(b).frame(width: 30) }.frame(height: 14)
                    }
                }
            }
            .padding(10)
        }
    }
}
