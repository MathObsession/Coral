import SwiftUI

@main
struct CoralApp: App {
    @StateObject private var store = CoralStore()
    var body: some Scene {
        mainWindow
        #if os(macOS)
        Settings { SettingsView().environmentObject(store).frame(width: 520, height: 520) }
        #endif
    }
    var mainWindow: some Scene {
        WindowGroup {
            RootView().environmentObject(store)
                .font(.system(.body, design: .rounded).weight(.medium))
                .foregroundStyle(CoralTheme.ink).tint(CoralTheme.orange)
                #if os(macOS)
                .frame(minWidth: 1000, minHeight: 700)
                #endif
        }
        #if os(macOS)
        .defaultSize(width: 1320, height: 860)
        #endif
    }
}

enum Destination: String, CaseIterable, Identifiable {
    case home = "Home", workspace = "Hermes workspace", files = "Files", terminal = "Terminal & SSH"
    case schedules = "Scheduled tasks", usage = "Usage", extended = "Extended mode", profiles = "Profiles", settings = "Settings"
    var id: String { rawValue }
    var icon: String {
        switch self {
        case .home: "square.grid.2x2.fill"
        case .workspace: "bubble.left.and.bubble.right.fill"
        case .files: "folder.fill"
        case .terminal: "terminal.fill"
        case .schedules: "calendar"
        case .usage: "chart.bar.fill"
        case .extended: "timer"
        case .profiles: "person.crop.circle.fill"
        case .settings: "gearshape.fill"
        }
    }
}

struct RootView: View {
    @EnvironmentObject var store: CoralStore
    @State private var selected: Destination = .home
    @Environment(\.scenePhase) var scenePhase
    var body: some View {
        Group {
            if !store.signedIn { SignInView() }
            else {
                #if os(macOS)
                NavigationSplitView {
                    VStack(alignment: .leading, spacing: 24) {
                        HStack(spacing: 12) { Mascot(size: 44); VStack(alignment: .leading) { Text("Coral").font(.title2.bold()); Text("YOUR AI WORKSPACE").font(.system(size: 10, weight: .heavy)).foregroundStyle(CoralTheme.orange) } }.padding(.horizontal, 18).padding(.top, 22)
                        List(Destination.allCases, selection: $selected) { destination in
                            Label(destination.rawValue, systemImage: destination.icon).tag(destination).padding(.vertical, 8)
                        }.listStyle(.sidebar)
                        VStack(alignment: .leading, spacing: 10) {
                            Text("A little focus. A lot of possibility.").font(.subheadline.bold())
                            if let usage = store.usage { Text("\(TimeFormat.duration(usage.remainingSeconds)) available today").font(.caption).foregroundStyle(CoralTheme.muted) }
                        }.coralCard(CoralTheme.cream).padding(12)
                        profilePicker.padding(.horizontal, 16).padding(.bottom, 16)
                    }.background(.white).navigationSplitViewColumnWidth(250)
                } detail: {
                    NavigationStack { destination(selected).navigationTitle(selected.rawValue).toolbar { ToolbarItem { profilePicker } } }
                }
                #else
                TabView {
                    NavigationStack { HomeView().navigationTitle("Coral") }.tabItem { Label("Home", systemImage: Destination.home.icon) }
                    NavigationStack { WorkspaceView().navigationTitle("Hermes") }.tabItem { Label("Hermes", systemImage: Destination.workspace.icon) }
                    NavigationStack { SchedulesView().navigationTitle("Schedules") }.tabItem { Label("Schedules", systemImage: "calendar") }
                    NavigationStack {
                        List {
                            Section { profilePicker }
                            ForEach([Destination.files, .terminal, .usage, .extended, .profiles, .settings]) { item in
                                NavigationLink { destination(item).navigationTitle(item.rawValue) } label: { Label(item.rawValue, systemImage: item.icon).padding(.vertical, 9) }
                            }
                        }.navigationTitle("Your workspace")
                    }.tabItem { Label("More", systemImage: "ellipsis.circle.fill") }
                }
                #endif
            }
        }.background(CoralTheme.canvas)
            .task { await store.poll() }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active { Task { try? await store.refresh() } }
            }
            .onChange(of: selected) { _, _ in store.interaction("navigation") }
            .alert("Coral needs your attention", isPresented: Binding(get: { store.error != nil }, set: { value in
                if !value { Task { @MainActor in store.error = nil } }
            })) {
                Button("OK") { store.error = nil }
            } message: { Text(store.error ?? "") }
    }
    private var profilePicker: some View {
        Picker("Profile", selection: Binding(get: { store.selectedId }, set: { store.select($0) })) {
            ForEach(store.profiles) { profile in Text(profile.login).tag(profile.id) }
        }.disabled(store.busy)
    }
    @ViewBuilder func destination(_ destination: Destination) -> some View {
        switch destination {
        case .home: HomeView()
        case .workspace: WorkspaceView()
        case .files: FilesView()
        case .terminal: TerminalView()
        case .schedules: SchedulesView()
        case .usage: UsageView()
        case .extended: ExtendedView()
        case .profiles: ProfilesView()
        case .settings: SettingsView()
        }
    }
}

struct SignInView: View {
    @EnvironmentObject var store: CoralStore
    @State private var settings = false
    var body: some View {
        ScrollView {
            VStack(spacing: 26) {
                Mascot(size: 160)
                VStack(spacing: 12) {
                    Text("Meet Coral.").font(.system(size: 42, weight: .heavy, design: .rounded))
                    Text("Your ideas, with room to grow.").font(.title3.bold())
                    Text("A personal home for Hermes, your files, and your next great project. Pick up where you left off, on Mac or iPhone.")
                        .foregroundStyle(CoralTheme.muted).multilineTextAlignment(.center)
                }
                Button { store.signIn() } label: { Label("Continue with GitHub", systemImage: "person.crop.circle.badge.checkmark") }.buttonStyle(TactileButtonStyle())
                    .disabled(store.busy)
                if store.busy { ProgressView("Connecting…") }
                HStack(spacing: 22) { Label("4 hours / day", systemImage: "clock"); Label("Automatic sleep", systemImage: "moon.zzz") }.font(.caption.bold()).foregroundStyle(CoralTheme.muted)
                Button("Configure backend") { settings = true }.buttonStyle(.plain).foregroundStyle(CoralTheme.blue)
            }.padding(32).frame(maxWidth: 480).coralCard().padding(24).frame(maxWidth: .infinity)
        }.frame(maxWidth: .infinity, maxHeight: .infinity).background(CoralTheme.canvas)
            .sheet(isPresented: $settings) { NavigationStack { SettingsView().toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { settings = false } } } } }
    }
}
