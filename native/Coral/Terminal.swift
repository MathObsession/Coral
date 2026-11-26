import SwiftUI
#if os(macOS)
import AppKit

@MainActor
final class SSHConsole: ObservableObject {
    @Published var output = "SSH uses your Mac’s own GitHub CLI credentials. Sign in locally with gh auth login first.\n"
    @Published var running = false
    private var process: Process?
    private var input: Pipe?
    private var pipe: Pipe?

    static func quote(_ value: String) -> String { "'" + value.replacingOccurrences(of: "'", with: "'\\''") + "'" }
    static func command(_ profile: Profile, setupHermes: Bool = false) throws -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-"))
        guard !profile.codespace.isEmpty, profile.codespace.unicodeScalars.allSatisfy({ allowed.contains($0) }),
              profile.login.unicodeScalars.allSatisfy({ allowed.contains($0) }) else { throw APIError.message("Invalid Codespace or GitHub account name.") }
        let ssh = "gh auth switch --hostname github.com --user \(quote(profile.login)) && gh codespace ssh --codespace \(quote(profile.codespace)) -- -tt"
        return setupHermes ? ssh + " " + quote("$HOME/.local/bin/hermes setup model") : ssh
    }
    func connect(_ profile: Profile) throws {
        disconnect()
        let command = try Self.command(profile)
        let child = Process(), stdin = Pipe(), stdout = Pipe()
        child.executableURL = URL(fileURLWithPath: "/usr/bin/script")
        child.arguments = ["-q", "/dev/null", "/bin/zsh", "-lc", command]
        var environment = ProcessInfo.processInfo.environment
        environment["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        environment["TERM"] = "xterm-256color"
        child.environment = environment
        child.standardInput = stdin; child.standardOutput = stdout; child.standardError = stdout
        stdout.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty { return }
            let value = String(decoding: data, as: UTF8.self).replacingOccurrences(of: "\u{001B}\\[[0-?]*[ -/]*[@-~]", with: "", options: .regularExpression)
            Task { @MainActor in self?.output.append(value); if let self, self.output.count > 200_000 { self.output = String(self.output.suffix(150_000)) } }
        }
        child.terminationHandler = { [weak self] child in Task { @MainActor in self?.running = false; self?.output += "\nSSH session ended (\(child.terminationStatus)).\n" } }
        try child.run()
        process = child; input = stdin; pipe = stdout; running = true
        output += "\nConnecting to \(profile.codespace) as \(profile.login)…\n"
    }
    func send(_ text: String) { try? input?.fileHandleForWriting.write(contentsOf: Data(text.utf8)) }
    func disconnect() {
        send("\u{0003}"); send("exit\n")
        if process?.isRunning == true { process?.terminate() }
        pipe?.fileHandleForReading.readabilityHandler = nil
        process = nil; input = nil; pipe = nil; running = false
    }
    func openTerminal(_ profile: Profile, app: String, setupHermes: Bool = false) async throws {
        let command = try Self.command(profile, setupHermes: setupHermes)
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("Coral-\(UUID().uuidString).command")
        try ("#!/bin/zsh\nexport PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin\n" + command + "\n").write(to: file, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: file.path)
        let bundleId = app == "iTerm" ? "com.googlecode.iterm2" : "com.apple.Terminal"
        guard let application = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundleId) else { throw APIError.message("Install \(app), or choose Terminal in Settings.") }
        let config = NSWorkspace.OpenConfiguration()
        try await NSWorkspace.shared.open([file], withApplicationAt: application, configuration: config)
    }
}
#endif

struct TerminalView: View {
    @EnvironmentObject var store: CoralStore
    @State private var command = ""
    @State private var sshInfo: SSHResponse?
    #if os(macOS)
    @StateObject private var ssh = SSHConsole()
    @State private var mode = "Commands"
    #endif
    private var canExecute: Bool {
        guard !command.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, store.profile?.ready == true else { return false }
        #if os(macOS)
        if mode == "SSH" { return ssh.running }
        #endif
        return !store.busy && !store.tasks.contains(where: \.active)
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Label("Direct mode", systemImage: "terminal.fill").font(.title2.bold())
                Spacer()
                #if os(macOS)
                Picker("Connection", selection: $mode) { Text("Commands").tag("Commands"); Text("Native SSH").tag("SSH") }.pickerStyle(.segmented).frame(width: 240)
                #endif
            }
            if let info = sshInfo {
                VStack(alignment: .leading, spacing: 10) {
                    Text("SSH · \(info.account)").font(.headline)
                    Text(info.command).font(.system(size: 13, design: .monospaced)).textSelection(.enabled)
                    #if os(macOS)
                    HStack {
                        Button("Open in \(store.terminalApp)") { store.perform { if let profile = store.profile { try await ssh.openTerminal(profile, app: store.terminalApp) } } }.buttonStyle(TactileButtonStyle(color: .white))
                        Button(ssh.running ? "Disconnect SSH" : "Connect native SSH") {
                            if ssh.running { ssh.disconnect() }
                            else { do { if let profile = store.profile { try ssh.connect(profile); mode = "SSH" } } catch { store.error = error.localizedDescription } }
                            store.interaction("terminal")
                        }.buttonStyle(TactileButtonStyle(color: CoralTheme.green)).disabled(store.profile?.ready != true)
                    }
                    Button("Set up Hermes model") {
                        guard let profile = store.profile else { return }
                        store.perform { try await ssh.openTerminal(profile, app: store.terminalApp, setupHermes: true) }
                    }.disabled(store.busy || store.profile?.ready != true)
                    #else
                    Text("Use this official GitHub command on a computer with gh installed. On iPhone, execute commands below through your authenticated Coral connection.").font(.caption).foregroundStyle(CoralTheme.muted)
                    #endif
                }.coralCard()
            }
            ScrollViewReader { reader in
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        #if os(macOS)
                        if mode == "SSH" { Text(ssh.output).textSelection(.enabled).id("end") }
                        else { commandHistory }
                        #else
                        commandHistory
                        #endif
                    }.font(.system(size: 13, weight: .medium, design: .monospaced)).padding(20).frame(maxWidth: .infinity, alignment: .leading)
                }.frame(maxWidth: .infinity, maxHeight: .infinity).background(Color(hex: 0x1E1E24), in: RoundedRectangle(cornerRadius: 22)).foregroundStyle(Color(hex: 0xE0E0E0))
                #if os(macOS)
                .onChange(of: ssh.output) { _, _ in reader.scrollTo("end", anchor: .bottom) }
                #endif
            }
            HStack {
                Text("$").font(.system(.headline, design: .monospaced)).foregroundStyle(CoralTheme.green)
                TextField("Enter a workspace command", text: $command).textFieldStyle(.roundedBorder).onSubmit { execute() }.onChange(of: command) { _, _ in store.interaction("terminal") }
                Button("Run") { execute() }.buttonStyle(TactileButtonStyle(color: CoralTheme.green)).disabled(!canExecute)
                #if os(macOS)
                if mode == "SSH" { Button("Ctrl+C") { ssh.send("\u{0003}"); store.interaction("terminal") } }
                #endif
            }
            Text("Commands run as your Codespace user in the designated workspace. Your daily allowance and session timeout apply.").font(.caption).foregroundStyle(CoralTheme.muted)
        }.padding(24).background(CoralTheme.canvas)
            .onChange(of: store.selectedId) { _, _ in
                command = ""
                #if os(macOS)
                ssh.disconnect(); mode = "Commands"
                #endif
            }
            .task(id: store.profile?.codespace) {
                sshInfo = nil
                guard store.profile?.codespace.isEmpty == false else { return }
                do { sshInfo = try await store.api.request(store.root + "/ssh") } catch { sshInfo = nil }
            }
            .onDisappear {
                #if os(macOS)
                ssh.disconnect()
                #endif
            }
    }
    var commandHistory: some View {
        VStack(alignment: .leading, spacing: 18) {
            if store.tasks.filter({ $0.kind == "terminal" }).isEmpty { Text("Coral workspace terminal\n\nStart your Codespace, then enter a command below. Output is recorded in your task history.").foregroundStyle(CoralTheme.green) }
            ForEach(store.tasks.filter { $0.kind == "terminal" }.reversed()) { task in
                VStack(alignment: .leading, spacing: 10) {
                    Text("$ " + task.prompt).foregroundStyle(CoralTheme.green)
                    Text(task.output.isEmpty ? task.status : task.output).textSelection(.enabled)
                    if !task.error.isEmpty { Text(task.error).foregroundStyle(CoralTheme.red) }
                    if task.active { Button("Cancel") { store.cancel(task) } }
                }
            }
        }
    }
    func execute() {
        guard canExecute else { return }
        #if os(macOS)
        if mode == "SSH" { ssh.send(command + "\n"); store.interaction("terminal"); command = ""; return }
        #endif
        let submitted = command
        store.run(submitted, kind: "terminal") { if command == submitted { command = "" } }
    }
}
