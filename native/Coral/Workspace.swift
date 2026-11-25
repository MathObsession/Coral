import SwiftUI

struct WorkspaceView: View {
    @EnvironmentObject var store: CoralStore
    @State private var prompt = ""
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Mascot(size: 40)
                VStack(alignment: .leading) { Text("Hermes").font(.headline); Text(store.profile?.hermes == 1 ? "Ready for your next task" : "Agent is stopped").font(.caption).foregroundStyle(CoralTheme.muted) }
                Spacer()
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
        }.background(CoralTheme.canvas)
    }
    func send() { store.run(prompt); prompt = "" }
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
