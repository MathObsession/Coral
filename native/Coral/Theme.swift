import SwiftUI

enum CoralTheme {
    static let canvas = Color(hex: 0xFBF9F8)
    static let ink = Color(hex: 0x4B4B4B)
    static let muted = Color(hex: 0x777777)
    static let border = Color(hex: 0xE5E5E5)
    static let orange = Color(hex: 0xFF9600)
    static let green = Color(hex: 0x58CC02)
    static let blue = Color(hex: 0x1CB0F6)
    static let red = Color(hex: 0xFF4B4B)
    static let cream = Color(hex: 0xFFF7EB)
}

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB, red: Double((hex >> 16) & 255) / 255, green: Double((hex >> 8) & 255) / 255, blue: Double(hex & 255) / 255, opacity: 1)
    }
}

struct TactileButtonStyle: ButtonStyle {
    var color = CoralTheme.orange
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(.system(size: 14, weight: .bold, design: .rounded))
            .padding(.horizontal, 18).padding(.vertical, 12)
            .foregroundStyle(color == .white ? CoralTheme.ink : .white)
            .background(color, in: RoundedRectangle(cornerRadius: 16))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(color == .white ? CoralTheme.border : color.opacity(0.8), lineWidth: 2))
            .compositingGroup()
            .shadow(color: color == .white ? CoralTheme.border : color.opacity(0.6), radius: 0, y: configuration.isPressed ? 0 : 4)
            .offset(y: configuration.isPressed ? 4 : 0)
    }
}

struct CardModifier: ViewModifier {
    var tint = Color.white
    func body(content: Content) -> some View {
        content.padding(22).frame(maxWidth: .infinity, alignment: .leading)
            .background(tint, in: RoundedRectangle(cornerRadius: 24))
            .overlay(RoundedRectangle(cornerRadius: 24).stroke(CoralTheme.border, lineWidth: 2))
            .compositingGroup()
            .shadow(color: CoralTheme.border, radius: 0, y: 4)
    }
}
extension View { func coralCard(_ tint: Color = .white) -> some View { modifier(CardModifier(tint: tint)) } }

struct Mascot: View {
    var size: CGFloat = 64
    var body: some View {
        Image("Mascot").resizable().scaledToFill().frame(width: size, height: size)
            .clipShape(RoundedRectangle(cornerRadius: size * 0.3))
            .overlay(RoundedRectangle(cornerRadius: size * 0.3).stroke(Color(hex: 0xFFD9A0), lineWidth: 2))
            .accessibilityLabel("Coral's orange and cream fox mascot")
    }
}

struct StatusBadge: View {
    let state: String
    var color: Color { state == "available" || state == "succeeded" ? CoralTheme.green : state == "failed" ? CoralTheme.red : CoralTheme.orange }
    var body: some View {
        HStack(spacing: 6) { Circle().fill(color).frame(width: 7, height: 7); Text(state.replacingOccurrences(of: "_", with: " ").capitalized) }
            .font(.system(size: 12, weight: .bold, design: .rounded))
            .padding(.horizontal, 11).padding(.vertical, 7)
            .background(color.opacity(0.1), in: Capsule()).foregroundStyle(CoralTheme.ink)
    }
}

struct EmptyCard: View {
    let symbol: String
    let title: String
    let detail: String
    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: symbol).font(.system(size: 32, weight: .semibold)).foregroundStyle(CoralTheme.orange)
            Text(title).font(.title3.bold())
            Text(detail).foregroundStyle(CoralTheme.muted).multilineTextAlignment(.center)
        }.frame(maxWidth: .infinity).coralCard()
    }
}
