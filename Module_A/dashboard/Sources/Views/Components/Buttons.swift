import SwiftUI

// Custom button styles: precise hover / press / disabled states with short springs.
// Primary = solid accent. Secondary = hairline. Quiet = text-only. Danger = critical.

struct PrimaryButtonStyle: ButtonStyle {
    var color: Color = Theme.accent
    var large = false

    func makeBody(configuration: Configuration) -> some View {
        PrimaryBody(configuration: configuration, color: color, large: large)
    }

    private struct PrimaryBody: View {
        let configuration: Configuration
        let color: Color
        let large: Bool
        @Environment(\.isEnabled) private var enabled
        @State private var hover = false

        var body: some View {
            configuration.label
                .font(.system(size: large ? 13.5 : 12.5, weight: .semibold))
                .foregroundStyle(.white.opacity(enabled ? 1 : 0.55))
                .padding(.horizontal, large ? 16 : 12)
                .frame(height: large ? 34 : 28)
                .background {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(enabled ? color : Theme.panelRaised)
                        .brightness(configuration.isPressed ? -0.08 : hover ? 0.06 : 0)
                }
                .overlay {
                    RoundedRectangle(cornerRadius: 8)
                        .strokeBorder(LinearGradient(colors: [.white.opacity(0.28), .white.opacity(0.04)], startPoint: .top, endPoint: .bottom), lineWidth: 1)
                }
                .scaleEffect(configuration.isPressed ? 0.97 : 1)
                .animation(.snappy(duration: 0.16), value: configuration.isPressed)
                .animation(.easeOut(duration: 0.15), value: hover)
                .onHover { hover = $0 }
                .contentShape(.rect)
        }
    }
}

struct SecondaryButtonStyle: ButtonStyle {
    var large = false

    func makeBody(configuration: Configuration) -> some View {
        SecondaryBody(configuration: configuration, large: large)
    }

    private struct SecondaryBody: View {
        let configuration: Configuration
        let large: Bool
        @Environment(\.isEnabled) private var enabled
        @State private var hover = false

        var body: some View {
            configuration.label
                .font(.system(size: large ? 13.5 : 12.5, weight: .medium))
                .foregroundStyle(enabled ? Theme.textPrimary : Theme.textTertiary)
                .padding(.horizontal, large ? 14 : 11)
                .frame(height: large ? 34 : 28)
                .background(Color.white.opacity(configuration.isPressed ? 0.09 : hover && enabled ? 0.06 : 0.025), in: .rect(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(hover && enabled ? Theme.hairlineStrong : Theme.hairline))
                .scaleEffect(configuration.isPressed ? 0.97 : 1)
                .animation(.snappy(duration: 0.16), value: configuration.isPressed)
                .animation(.easeOut(duration: 0.15), value: hover)
                .onHover { hover = $0 }
                .contentShape(.rect)
        }
    }
}

struct QuietButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        QuietBody(configuration: configuration)
    }

    private struct QuietBody: View {
        let configuration: Configuration
        @State private var hover = false

        var body: some View {
            configuration.label
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(hover ? Theme.textPrimary : Theme.textSecondary)
                .padding(.horizontal, 8)
                .frame(height: 24)
                .background(Color.white.opacity(hover ? 0.06 : 0), in: .rect(cornerRadius: 6))
                .opacity(configuration.isPressed ? 0.7 : 1)
                .animation(.easeOut(duration: 0.12), value: hover)
                .onHover { hover = $0 }
                .contentShape(.rect)
        }
    }
}

extension ButtonStyle where Self == PrimaryButtonStyle {
    static var primary: PrimaryButtonStyle { PrimaryButtonStyle() }
    static var primaryLarge: PrimaryButtonStyle { PrimaryButtonStyle(large: true) }
    static func primary(_ color: Color, large: Bool = false) -> PrimaryButtonStyle { PrimaryButtonStyle(color: color, large: large) }
}

extension ButtonStyle where Self == SecondaryButtonStyle {
    static var secondary: SecondaryButtonStyle { SecondaryButtonStyle() }
    static var secondaryLarge: SecondaryButtonStyle { SecondaryButtonStyle(large: true) }
}

extension ButtonStyle where Self == QuietButtonStyle {
    static var quiet: QuietButtonStyle { QuietButtonStyle() }
}

/// Press-and-hold safety button: a ring fills while held; the action fires only after `duration`.
struct HoldToConfirmButton: View {
    let title: String
    let symbol: String
    var color: Color = Theme.critical
    var duration: Double = 0.8
    let action: () -> Void

    @State private var progress: CGFloat = 0
    @State private var holding = false
    @State private var fired = false
    @State private var hover = false
    @Environment(\.isEnabled) private var enabled

    private var ring: some View {
        ZStack {
            Circle().stroke(Color.white.opacity(0.25), lineWidth: 2)
            Circle()
                .trim(from: 0, to: progress)
                .stroke(Color.white, style: StrokeStyle(lineWidth: 2, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Image(systemName: fired ? "checkmark" : symbol)
                .font(.system(size: 9, weight: .black))
                .contentTransition(.symbolEffect(.replace))
        }
        .frame(width: 18, height: 18)
    }

    private var fill: some View {
        let base: Color = enabled ? color : Theme.panelRaised
        let brightness: Double = holding ? -0.06 : (hover ? 0.05 : 0)
        return RoundedRectangle(cornerRadius: 9).fill(base).brightness(brightness)
    }

    private var label: some View {
        HStack(spacing: 8) {
            ring
            Text(holding ? "HOLD…" : title)
                .font(.system(size: 12.5, weight: .bold))
                .contentTransition(.interpolate)
        }
        .foregroundStyle(Color.white)
        .padding(.horizontal, 16)
        .frame(height: 38)
    }

    var body: some View {
        label
        .background { fill }
        .overlay(RoundedRectangle(cornerRadius: 9).strokeBorder(Color.white.opacity(0.22)))
        .scaleEffect(holding ? 0.97 : 1)
        .animation(.snappy(duration: 0.18), value: holding)
        .onHover { hover = $0 }
        .gesture(
            DragGesture(minimumDistance: 0)
                .onChanged { _ in
                    guard enabled, !holding, !fired else { return }
                    holding = true
                    withAnimation(.linear(duration: duration)) { progress = 1 }
                    DispatchQueue.main.asyncAfter(deadline: .now() + duration) {
                        if holding && !fired {
                            fired = true
                            action()
                            DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) { reset() }
                        }
                    }
                }
                .onEnded { _ in if !fired { reset() } else { holding = false } }
        )
        .help("Press and hold to \(title.lowercased())")
        .accessibilityAddTraits(.isButton)
        .accessibilityAction { action() }
    }

    private func reset() {
        holding = false
        fired = false
        withAnimation(.snappy(duration: 0.25)) { progress = 0 }
    }
}
