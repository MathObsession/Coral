import SwiftUI

struct ProfilesView: View {
    @EnvironmentObject var store: CoralStore
    @State private var repository = ""
    @State private var codespace = ""
    private var trimmedRepository: String { repository.trimmingCharacters(in: .whitespacesAndNewlines) }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text("Every project has a home.").font(.largeTitle.bold())
                Text("Connect the GitHub account that should own and pay for your Codespace. Each profile keeps its own repository, files, and history.").foregroundStyle(CoralTheme.muted)
                ForEach(store.profiles) { profile in
                    HStack { Image(systemName: "person.crop.circle.fill").font(.title).foregroundStyle(CoralTheme.orange); VStack(alignment: .leading) { Text(profile.login).font(.headline); Text(profile.repository.isEmpty ? "Choose a repository" : profile.repository).font(.caption).foregroundStyle(CoralTheme.muted) }; Spacer(); Button(profile.id == store.selectedId ? "Selected" : "Switch") { store.select(profile.id) }.disabled(profile.id == store.selectedId || store.busy) }.coralCard()
                }
                VStack(alignment: .leading, spacing: 18) {
                    Text("Connect this profile’s workspace").font(.title3.bold())
                    if let profile = store.profile, !profile.codespace.isEmpty {
                        HStack { Text(profile.repository).font(.headline); Spacer(); StatusBadge(state: profile.state) }
                        Text(profile.codespace).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                        Button("Stop and disconnect workspace") { store.command("disconnect") }
                            .buttonStyle(TactileButtonStyle(color: .white)).disabled(store.busy || profile.busy)
                    } else {
                        TextField("Repository (owner/name)", text: $repository).textFieldStyle(.roundedBorder)
                        TextField("Existing Codespace name (optional)", text: $codespace).textFieldStyle(.roundedBorder)
                        Text("Leave the Codespace name empty to create one. GitHub clones the repository and Coral installs Hermes. Setup consumes part of your daily allowance.").font(.caption).foregroundStyle(CoralTheme.muted)
                        Button("Connect & initialize Hermes") {
                            store.command("connect", body: ["repository": trimmedRepository, "codespace": codespace.trimmingCharacters(in: .whitespacesAndNewlines)])
                        }.buttonStyle(TactileButtonStyle(color: CoralTheme.green))
                            .disabled(trimmedRepository.split(separator: "/").count != 2 || store.busy || store.profile == nil || store.profile?.busy == true)
                    }
                    if store.busy || store.profile?.state == "starting" { ProgressView("Preparing your workspace…") }
                    if let error = store.profile?.error, !error.isEmpty {
                        Label(error, systemImage: "exclamationmark.circle.fill").font(.caption).foregroundStyle(CoralTheme.red)
                    }
                }.coralCard()
                Button("Add another GitHub account") { store.signIn(link: true) }.buttonStyle(TactileButtonStyle()).disabled(store.busy)
            }.padding(24).frame(maxWidth: 850).frame(maxWidth: .infinity)
        }.background(CoralTheme.canvas)
    }
}

struct SettingsView: View {
    @EnvironmentObject var store: CoralStore
    @State private var backend = ""
    var body: some View {
        Form {
            Section("Connection") {
                TextField("Backend URL", text: $backend)
                    #if os(iOS)
                    .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                    #endif
                Button("Save backend") { store.backendURL = backend; store.saveBackend() }
                Text("Use the always-on Coral backend’s HTTPS address. GitHub Pages hosts the website only.").font(.caption).foregroundStyle(CoralTheme.muted)
            }
            #if os(macOS)
            Section("SSH") {
                Picker("Preferred terminal", selection: $store.terminalApp) { Text("Terminal").tag("Terminal"); Text("iTerm").tag("iTerm") }.onChange(of: store.terminalApp) { _, value in UserDefaults.standard.set(value, forKey: "terminalApp") }
                Text("SSH uses the GitHub CLI account installed on this Mac. Coral selects the matching account with gh auth switch. Use your preferred terminal for full-screen tools.").font(.caption).foregroundStyle(CoralTheme.muted)
            }
            #endif
            Section("Task results") {
                Button("Enable notifications on this device") { store.enableNotifications() }
                Text("Results are kept in your backend inbox. Device notifications appear when Coral receives them while open or when reopened.").font(.caption).foregroundStyle(CoralTheme.muted)
            }
            Section("Account") { if store.signedIn { Button("Sign out of Coral") { store.logout() } } else { Button("Sign in with GitHub") { store.signIn() } } }
            if backend.contains("127.0.0.1") || backend.contains("localhost") {
                Section("Local development") {
                    Button("Open local workspace") { store.backendURL = backend; store.saveBackend(); store.localLogin() }
                    Text("Requires CORAL_DEMO=1 on a localhost backend. Local mode runs real file and shell operations, and does not simulate Hermes responses.").font(.caption).foregroundStyle(CoralTheme.muted)
                }
            }
            Section { HStack { Mascot(size: 36); VStack(alignment: .leading) { Text("Coral 1.0").font(.headline); Text("A personal home for your AI workspace.").font(.caption).foregroundStyle(CoralTheme.muted) } } }
        }.formStyle(.grouped).onAppear { backend = store.backendURL }.navigationTitle("Settings")
    }
}
