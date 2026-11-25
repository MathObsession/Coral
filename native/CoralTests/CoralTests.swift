import XCTest
@testable import Coral

final class CoralTests: XCTestCase {
    func testDecodesActualUsageContract() throws {
        let data = Data("""
        {"allowance_seconds":14400,"used_seconds":1800,"remaining_seconds":12600,"server_time":1700000000,"session_seconds":1800,"inactivity_seconds":540,"extended_until":null,"session":null,"history":[],"daily":[]}
        """.utf8)
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let usage = try decoder.decode(Usage.self, from: data)
        XCTAssertEqual(usage.remainingSeconds, 12600)
        XCTAssertNil(usage.extendedUntil)
    }
    func testDecodesScheduleAndTaskRelationships() throws {
        let data = Data("""
        {"id":"one","profile_id":"p","schedule_id":"s","kind":"hermes","prompt":"Check repo","status":"running","output":"Checking","error":"","created":1,"deadline":300,"finished":null}
        """.utf8)
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let task = try decoder.decode(AgentTask.self, from: data)
        XCTAssertEqual(task.scheduleId, "s")
        XCTAssertTrue(task.active)
    }
    func testCountersNeverShowNegativeTime() {
        XCTAssertEqual(TimeFormat.countdown(-12), "00:00")
        XCTAssertEqual(TimeFormat.duration(14400), "4h 0m")
        XCTAssertEqual(TimeFormat.countdown(600), "10:00")
    }
    #if os(macOS)
    @MainActor func testSSHRejectsInjectedNames() {
        let profile = Profile(id: "p", login: "dev", repository: "dev/repo", codespace: "name;touch /tmp/bad", state: "available", hermes: 1, error: "")
        XCTAssertThrowsError(try SSHConsole.command(profile))
    }
    #endif
}
