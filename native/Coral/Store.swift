import SwiftUI
import UserNotifications

@MainActor
final class CoralStore: ObservableObject {
    @Published var profiles: [Profile] = []
    @Published var selectedId: String = UserDefaults.standard.string(forKey: "profile") ?? ""
    @Published var usage: Usage?
    @Published var tasks: [AgentTask] = []
    @Published var schedules: [ScheduledTask] = []
    @Published var notifications: [InboxNotification] = []
    @Published var signedIn: Bool
    @Published var busy = false
    @Published var error: String?
    @Published var lastRefresh: Date?
    @Published var backendURL: String
    @Published var terminalApp = UserDefaults.standard.string(forKey: "terminalApp") ?? "Terminal"
    let api: API
    let auth = GitHubSignIn()
    private var notifying = Set<String>()
    private var refreshing = false
    private var lastActivity = Date.distantPast
    var editorDrafts: [String: (path: String, content: String, original: String)] = [:]
    var profile: Profile? { profiles.first { $0.id == selectedId } }
    var root: String { "/profiles/" + selectedId }

    init() {
        let url = UserDefaults.standard.string(forKey: "backendURL") ?? (Bundle.main.object(forInfoDictionaryKey: "CoralBackendURL") as? String ?? "http://127.0.0.1:8000")
        backendURL = url
        api = API(baseURL: url)
        signedIn = api.token != nil
    }

    func perform(_ action: @escaping () async throws -> Void) {
        guard !busy else { return }
        busy = true
        Task {
            defer { busy = false }
            do { try await action(); try await refresh() }
            catch { self.error = error.localizedDescription; signedIn = api.token != nil }
        }
    }

    func refresh() async throws {
        guard !refreshing else { return }
        refreshing = true
        defer { refreshing = false }
        guard api.token != nil else { signedIn = false; return }
        let response: ProfilesResponse = try await api.request("/profiles")
        profiles = response.profiles
        if !profiles.contains(where: { $0.id == selectedId }) { selectedId = profiles.first?.id ?? "" }
        guard !selectedId.isEmpty else { return }
        let refreshingId = selectedId
        let refreshingRoot = "/profiles/" + refreshingId
        UserDefaults.standard.set(selectedId, forKey: "profile")
        // Only reads happen in this loop. Polling never submits an activity event.
        let currentUsage: Usage = try await api.request(refreshingRoot + "/usage")
        let currentTasks: TasksResponse = try await api.request(refreshingRoot + "/tasks")
        let currentSchedules: SchedulesResponse = try await api.request(refreshingRoot + "/schedules")
        let inbox: NotificationsResponse = try await api.request("/notifications")
        guard selectedId == refreshingId else { return }
        usage = currentUsage; tasks = currentTasks.tasks; schedules = currentSchedules.schedules
        notifications = inbox.notifications
        lastRefresh = Date(); signedIn = true
        if UserDefaults.standard.bool(forKey: "notifications") {
            for item in inbox.notifications where item.read == 0 && !notifying.contains(item.id) {
                notifying.insert(item.id)
                let content = UNMutableNotificationContent()
                content.title = "Coral"; content.body = item.title
                try? await UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: item.id, content: content, trigger: nil))
            }
        }
    }

    func poll() async {
        while !Task.isCancelled {
            do { try await refresh() }
            catch { if api.token == nil { signedIn = false }; self.error = error.localizedDescription }
            try? await Task.sleep(for: .seconds(5))
        }
    }

    func signIn(link: Bool = false) {
        perform { try await self.auth.signIn(api: self.api, link: link); self.signedIn = true }
    }
    func localLogin() {
        perform {
            let response: TokenResponse = try await self.api.request("/auth/local", method: "POST")
            self.api.token = response.token; self.signedIn = true
        }
    }
    func logout() {
        perform {
            _ = try await self.api.raw("/auth/logout", method: "POST")
            self.api.token = nil; self.signedIn = false; self.profiles = []; self.usage = nil
        }
    }
    func saveBackend() {
        api.baseURL = backendURL.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        api.token = Keychain.read(api.baseURL)
        signedIn = api.token != nil
        UserDefaults.standard.set(api.baseURL, forKey: "backendURL")
        profiles = []; usage = nil; tasks = []; schedules = []; notifications = []
    }
    func select(_ id: String) {
        selectedId = id; usage = nil; tasks = []; schedules = []
        perform { try await self.refresh() }
    }
    func command(_ action: String, body: [String: Any]? = nil) {
        perform { _ = try await self.api.raw(self.root + "/" + action, method: "POST", body: body) }
    }
    func interaction(_ kind: String) {
        guard signedIn, profile?.ready == true, Date().timeIntervalSince(lastActivity) >= 15 else { return }
        lastActivity = Date()
        Task { _ = try? await api.raw(root + "/activity", method: "POST", body: ["kind": kind]) }
    }
    func run(_ prompt: String, kind: String = "hermes", onAccepted: @escaping () -> Void = {}) {
        let id = UUID().uuidString
        perform {
            _ = try await self.api.raw(self.root + "/tasks", method: "POST", body: ["prompt": prompt, "kind": kind, "duration_limit": 900], key: id)
            onAccepted()
        }
    }
    func cancel(_ task: AgentTask) { command("tasks/" + task.id + "/cancel") }
    func enableNotifications() {
        perform {
            let granted = try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])
            UserDefaults.standard.set(granted, forKey: "notifications")
        }
    }
}
