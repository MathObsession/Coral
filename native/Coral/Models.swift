import Foundation

struct Profile: Codable, Identifiable, Hashable {
    let id: String
    var login: String
    var repository: String
    var codespace: String
    var state: String
    var hermes: Int
    var error: String
    var ready: Bool { state == "available" }
    var busy: Bool { state == "starting" || state == "stopping" }
}

struct Session: Codable, Identifiable {
    let id: String
    let mode: String
    let started: Double
    let ended: Double?
    let reason: String
    let deadline: Double
}

struct Usage: Codable {
    let allowanceSeconds: Double
    let usedSeconds: Double
    let remainingSeconds: Double
    let serverTime: Double
    let sessionSeconds: Double
    let inactivitySeconds: Double
    let extendedUntil: Double?
    let session: Session?
    let history: [Session]
    let daily: [DailyUsage]
}

struct DailyUsage: Codable { let day: String; let seconds: Double }

struct AgentTask: Codable, Identifiable {
    let id: String
    let scheduleId: String?
    let kind: String
    let prompt: String
    let status: String
    let output: String
    let error: String
    let created: Double
    let deadline: Double
    let finished: Double?
    var active: Bool { status == "queued" || status == "running" }
}

struct ScheduledTask: Codable, Identifiable {
    let id: String
    let title: String
    let prompt: String
    let recurrence: String
    let nextRun: Double
    let intervalSeconds: Int
    let durationLimit: Int
    let paused: Int
    var body: [String: Any] {
        ["title": title, "prompt": prompt, "recurrence": recurrence, "next_run": nextRun,
         "interval_seconds": intervalSeconds, "duration_limit": durationLimit, "paused": paused == 1]
    }
}

struct WorkspaceFile: Codable, Identifiable {
    let name: String
    let path: String
    let directory: Bool
    let size: Int
    var id: String { path }
}

struct InboxNotification: Codable, Identifiable {
    let id: String
    let taskId: String
    let title: String
    let created: Double
    let read: Int
}

struct ProfilesResponse: Decodable { let profiles: [Profile] }
struct TasksResponse: Decodable { let tasks: [AgentTask] }
struct SchedulesResponse: Decodable { let schedules: [ScheduledTask] }
struct FilesResponse: Decodable { let files: [WorkspaceFile] }
struct FileResponse: Decodable { let content: String; let path: String }
struct NotificationsResponse: Decodable { let notifications: [InboxNotification] }
struct TokenResponse: Decodable { let token: String }
struct URLResponse: Decodable { let url: String }
struct SSHResponse: Decodable { let codespace: String; let account: String; let command: String; let configCommand: String }

struct HermesProviderOption: Decodable, Identifiable {
    let id: String
    let name: String
    let keyEnv: String
    let interactive: Bool
}

struct HermesProvidersResponse: Decodable {
    let providers: [HermesProviderOption]
    let selected: String
    let model: String
}

enum TimeFormat {
    static func duration(_ seconds: Double) -> String {
        let n = max(0, Int(seconds))
        return n >= 3600 ? "\(n / 3600)h \((n % 3600) / 60)m" : "\(n / 60)m \(n % 60)s"
    }
    static func countdown(_ seconds: Double) -> String {
        let n = max(0, Int(seconds))
        return String(format: "%02d:%02d", n / 60, n % 60)
    }
}
