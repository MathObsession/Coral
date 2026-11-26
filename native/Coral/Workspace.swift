import SwiftUI

struct WorkspaceView: View {
    @EnvironmentObject var store: CoralStore
    @State private var prompt = ""
    @State private var showModel = false
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Mascot(size: 40)
                VStack(alignment: .leading) { Text("Hermes").font(.headline); Text(store.profile?.hermes == 1 ? "Ready for your next task" : "Agent is stopped").font(.caption).foregroundStyle(CoralTheme.muted) }
                Spacer()
                Button { showModel = true } label: { Label("Model", systemImage: "slider.horizontal.3") }
                    .buttonStyle(TactileButtonStyle(color: .white))
                Button(store.profile?.hermes == 1 ? "Stop Hermes" : "Start Hermes") { store.command("hermes", body: ["enabled": store.profile?.hermes != 1]) }
                    .buttonStyle(TactileButtonStyle(color: .white)).disabled(store.busy || store.profile?.ready != true)
            }.padding(20).background(.white)
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 24) {
                    if store.tasks.filter({ $0.kind == "hermes" }).isEmpty {
                        EmptyCard(symbol: "bubble.left.and.bubble.right", title: "What shall we build?", detail: "Ask Hermes to explore your repository, work on a feature, or help untangle an idea.")
                    }
                    ForEach(store.tasks.filter { $0.kind == "hermes" }.reversed()) { task in TaskCard(task: task) }
                }.padding(24).frame(maxWidth: 960).frame(maxWidth: .infinity)
            }
            VStack(spacing: 12) {
                TextField("Message Hermes or ask to write code…", text: $prompt, axis: .vertical).lineLimit(2...6)
                    .textFieldStyle(.plain).padding(16).background(CoralTheme.canvas, in: RoundedRectangle(cornerRadius: 16))
                    .onChange(of: prompt) { _, _ in store.interaction("chat") }
                HStack {
                    Text(store.profile?.repository ?? "Designated workspace").font(.caption.bold()).foregroundStyle(CoralTheme.muted).lineLimit(1)
                    Spacer()
                    Button { send() } label: { Label("Send", systemImage: "arrow.up") }.buttonStyle(TactileButtonStyle(color: CoralTheme.green))
                        .keyboardShortcut(.return, modifiers: .command)
                        .disabled(prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || store.busy || store.profile?.ready != true || store.profile?.hermes != 1 || store.tasks.contains(where: \.active))
                }
            }.padding(20).background(.white).overlay(alignment: .top) { Rectangle().fill(CoralTheme.border).frame(height: 2) }
        }.background(CoralTheme.canvas).sheet(isPresented: $showModel) {
            NavigationStack { ModelProvidersView() }
                #if os(macOS)
                .frame(minWidth: 570, minHeight: 440)
                #endif
        }
    }
    func send() {
        let submitted = prompt
        store.run(submitted) { if prompt == submitted { prompt = "" } }
    }
}

struct ModelProvidersView: View {
    @EnvironmentObject var store: CoralStore
    @Environment(\.dismiss) private var dismiss
    @State private var catalog: HermesProvidersResponse?
    @State private var selection = ""
    @State private var model = ""
    @State private var endpoint = ""
    @State private var endpointName = ""
    @State private var key = ""
    @State private var saving = false
    @State private var status: String?
    @State private var problem: String?

    private var newEndpoint: Bool { selection == "new-custom" }
    private var option: HermesProviderOption? { catalog?.providers.first { $0.id == selection } }

    var body: some View {
        Form {
            if store.profile?.ready != true {
                Text("Start the Codespace to change its Hermes model settings.")
            } else if let catalog {
                Section("Provider") {
                    Picker("Provider", selection: Binding(get: { selection }, set: choose)) {
                        Text("Choose a provider").tag("")
                        ForEach(catalog.providers) { Text($0.name).tag($0.id) }
                        Text("Add OpenAI-compatible endpoint…").tag("new-custom")
                    }
                    if newEndpoint {
                        TextField("Endpoint name", text: $endpointName)
                        TextField("Base URL (for example https://example.com/v1)", text: $endpoint)
                    }
                    if !selection.isEmpty { TextField("Model ID", text: $model) }
                    if newEndpoint || (option?.interactive == false && option?.keyEnv.isEmpty == false) {
                        SecureField("API key (optional)", text: $key)
                        Text("Coral saves the key inside this Codespace. For a key already configured in Hermes, leave the field blank.")
                            .font(.caption).foregroundStyle(CoralTheme.muted)
                    }
                    Button("Save model", action: save)
                        .disabled(saving || selection.isEmpty || model.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
                                  (newEndpoint && (endpoint.isEmpty || endpointName.isEmpty)))
                }.disabled(saving)
                Section("Hermes setup") {
                    Text("Use Hermes’ setup wizard for browser sign-in and advanced provider options.")
                        .font(.caption).foregroundStyle(CoralTheme.muted)
                    #if os(macOS)
                    Button("Open Hermes setup in \(store.terminalApp)", action: openSetup)
                    #else
                    if let profile = store.profile {
                        Text("gh codespace ssh --codespace \(profile.codespace) -- -tt '$HOME/.local/bin/hermes model'")
                            .font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                    }
                    #endif
                }
            } else if problem == nil {
                ProgressView("Loading Hermes providers…")
            } else {
                Button("Retry") { Task { await load() } }
            }
            if let status { Text(status).foregroundStyle(CoralTheme.muted) }
            if let problem { Label(problem, systemImage: "exclamationmark.circle").foregroundStyle(CoralTheme.red) }
        }
        .formStyle(.grouped).navigationTitle("Hermes model provider")
        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        .task(id: store.profile?.ready) {
            if store.profile?.ready == true { await load() }
        }
    }

    private func choose(_ id: String) {
        selection = id
        model = id == catalog?.selected ? catalog?.model ?? "" : ""
        key = ""
        status = nil
        problem = nil
    }

    private func load() async {
        problem = nil
        do {
            let result: HermesProvidersResponse = try await store.api.request(store.root + "/hermes/providers")
            catalog = result
            choose(result.providers.contains { $0.id == result.selected } ? result.selected : "")
        } catch {
            problem = error.localizedDescription
        }
    }

    private func save() {
        saving = true
        status = nil
        problem = nil
        let path = store.root + "/hermes/provider"
        let body = ["provider": selection, "model": model, "name": endpointName, "base_url": endpoint, "api_key": key]
        Task {
            defer { saving = false }
            do {
                _ = try await store.api.raw(path, method: "PUT", body: body)
                key = ""
                await load()
                status = "Model saved in this Codespace. Send a task to test the provider."
            } catch {
                problem = error.localizedDescription
            }
        }
    }

    #if os(macOS)
    private func openSetup() {
        guard let profile = store.profile else { return }
        Task {
            do { try await SSHConsole().openTerminal(profile, app: store.terminalApp, setupHermes: true) }
            catch { problem = error.localizedDescription }
        }
    }
    #endif
}

struct TaskCard: View {
    @EnvironmentObject var store: CoralStore
    let task: AgentTask
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack { Label(task.scheduleId == nil ? "You" : "Scheduled task", systemImage: task.scheduleId == nil ? "person.crop.circle" : "calendar").font(.caption.bold()); Spacer(); Text(Date(timeIntervalSince1970: task.created), style: .time).font(.caption).foregroundStyle(CoralTheme.muted) }
            Text(task.prompt).textSelection(.enabled).font(.body.bold()).padding(16).frame(maxWidth: .infinity, alignment: .leading).background(CoralTheme.blue.opacity(0.09), in: RoundedRectangle(cornerRadius: 16))
            HStack { Mascot(size: 30); Text(task.kind == "terminal" ? "Command output" : "Hermes").font(.headline); Spacer(); StatusBadge(state: task.status) }
            if task.output.isEmpty && task.active { ProgressView("Working in your workspace…") }
            if !task.output.isEmpty { Text(task.output).font(task.kind == "terminal" ? .system(size: 13, design: .monospaced) : .body).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
            if !task.error.isEmpty { Label(task.error, systemImage: "exclamationmark.triangle.fill").font(.subheadline).foregroundStyle(CoralTheme.red) }
            if task.active { Button("Cancel task") { store.cancel(task) }.buttonStyle(TactileButtonStyle(color: .white)).disabled(store.busy) }
        }.coralCard()
    }
}
