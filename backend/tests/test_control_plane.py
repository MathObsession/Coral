import asyncio
import base64
import importlib.util
import json
from pathlib import Path
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient
from coral.app import create_app
from coral.config import Config
from coral.db import Database
from coral.github import GitHub, GitHubError, LocalGitHub
from coral.security import Security, challenge
from coral.service import Service, identifier


class Clock:
    def __init__(self, now=1700000000): self.now = now
    def __call__(self): return self.now
    def advance(self, seconds): self.now += seconds


class Driver(LocalGitHub):
    def __init__(self, path):
        super().__init__(path)
        self.starts = self.stops = self.runs = 0
        self.fail_stop = False
        self.task_state = "succeeded"
    async def start(self, profile): self.starts += 1; await super().start(profile)
    async def stop(self, profile):
        self.stops += 1
        if self.fail_stop: raise RuntimeError("Network offline")
        await super().stop(profile)
    async def remote(self, profile, request):
        if request["operation"] == "run": self.runs += 1; return {"status": "running"}
        if request["operation"] == "poll": return {"status": self.task_state, "output": "Real task result", "error": ""}
        return await super().remote(profile, request)


@pytest.fixture
def rig(tmp_path):
    config = Config(database=":memory:", demo=True, encryption_key=Fernet.generate_key().decode())
    db = Database(":memory:")
    clock = Clock()
    driver = Driver(tmp_path)
    service = Service(db, config, driver, clock)
    security = Security(db, config)
    db.execute("INSERT INTO users VALUES('u','dev',1)")
    db.execute("INSERT INTO profiles(id,user_id,login,github_id,token,repository,codespace,state) VALUES('p','u','dev',1,?,'dev/repo','space','stopped')", (security.seal("secret-token"),))
    return service, db, driver, clock


async def started(service):
    await service.start("u", "p")
    await asyncio.gather(*service.pending)


@pytest.mark.parametrize("empty", [True, False])
def test_codespace_requires_a_commit_in_a_zero_size_repository(monkeypatch, empty):
    github = GitHub(None)
    profile = {"id": "profile", "github_id": 42}
    repository = "dev/repo"
    creates = []

    async def api(_profile, endpoint, method="GET", body=None):
        if endpoint == "repos/dev/repo":
            return {"id": 123, "size": 0, "default_branch": "main"}
        if endpoint == "user/codespaces?per_page=100":
            return {"codespaces": []}
        if endpoint == "repos/dev/repo/commits?per_page=1":
            if empty:
                raise GitHubError("GitHub request failed", 409)
            return [{"sha": "initial-commit"}]
        assert (endpoint, method) == ("user/codespaces", "POST")
        creates.append(body)
        return {"name": "my-codespace", "owner": {"id": 42}, "repository": {"full_name": repository}}

    monkeypatch.setattr(github, "api", api)
    if empty:
        with pytest.raises(GitHubError, match="repository has no commits"):
            asyncio.run(github.bind(profile, repository))
        assert not creates
    else:
        assert asyncio.run(github.bind(profile, repository)) == "my-codespace"
        assert [request["ref"] for request in creates] == ["main"]


def test_duplicate_starts_reserve_one_session(rig):
    service, db, driver, clock = rig
    async def case():
        await asyncio.gather(service.start("u", "p"), service.start("u", "p"))
        await asyncio.gather(*service.pending)
    asyncio.run(case())
    assert driver.starts == 1
    assert len(db.rows("SELECT * FROM sessions WHERE ended IS NULL")) == 1


def test_connect_waits_for_new_codespace_without_starting_it_again(rig, monkeypatch):
    service, db, driver, _ = rig
    service.config.demo = False
    db.execute("UPDATE profiles SET codespace='',state='unconfigured' WHERE id='p'")
    states = iter(("Provisioning", "Available"))

    async def inspect(profile):
        return {"state": next(states)}

    monkeypatch.setattr(driver, "inspect", inspect)

    async def case():
        profile = await service.configure("u", "p", "dev/repo", "")
        assert profile["state"] == "starting"
        await asyncio.gather(*service.pending)

    asyncio.run(case())
    assert driver.starts == 0
    assert service.profile("u", "p")["state"] == "available"


def test_polling_never_resets_inactivity_and_exact_timeout(rig):
    service, db, driver, clock = rig
    async def case():
        await started(service)
        clock.advance(599)
        for _ in range(5): service.usage("u", "p")
        await service.tick()
        assert driver.stops == 0
        clock.advance(1)
        await service.tick()
    asyncio.run(case())
    assert db.one("SELECT reason FROM sessions")["reason"] == "inactivity"
    assert service.remaining("u") == 13800


def test_explicit_activity_resets_server_timer(rig):
    service, db, driver, clock = rig
    async def case():
        await started(service)
        clock.advance(590); service.activity("u", "p")
        clock.advance(20); await service.tick()
    asyncio.run(case())
    assert driver.stops == 0
    assert service.usage("u", "p")["inactivity_seconds"] == 580


def test_extension_expires_and_never_changes_daily_limit(rig):
    service, db, driver, clock = rig
    async def case():
        await started(service)
        service.extend("u", "p", 1200)
        clock.advance(1199); await service.tick()
        assert driver.stops == 0
        clock.advance(1); await service.tick()
    asyncio.run(case())
    assert driver.stops == 1
    assert service.remaining("u") == 13200


def test_exhausted_allowance_cannot_start(rig):
    service, db, driver, clock = rig
    db.execute("INSERT INTO usage VALUES('u',?,14400)", ("2023-11-14",))
    with pytest.raises(HTTPException) as error: asyncio.run(service.start("u", "p"))
    assert error.value.status_code == 403
    assert driver.starts == 0


def test_allowance_enforced_in_extended_mode(rig):
    service, db, driver, clock = rig
    db.execute("INSERT INTO usage VALUES('u','2023-11-14',14000)")
    async def case():
        await started(service)
        service.extend("u", "p", 7200)
        assert service.usage("u", "p")["extended_until"] == clock.now + 370
        clock.advance(370); await service.tick()
    asyncio.run(case())
    assert db.one("SELECT reason FROM sessions")["reason"] == "daily_allowance"


def test_accounting_splits_utc_midnight(rig):
    service, db, driver, clock = rig
    clock.now = 1700006390 # 2023-11-14 23:59:50 UTC
    async def case():
        await started(service)
        clock.advance(25); service.charge()
    asyncio.run(case())
    assert db.one("SELECT seconds FROM usage WHERE day='2023-11-14'")["seconds"] == 10
    assert db.one("SELECT seconds FROM usage WHERE day='2023-11-15'")["seconds"] == 15


def test_stop_failure_keeps_usage_running_and_retries(rig):
    service, db, driver, clock = rig
    async def case():
        await started(service)
        driver.fail_stop = True
        clock.advance(600); await service.tick()
        assert db.one("SELECT ended FROM sessions")["ended"] is None
        assert service.profile("u", "p")["state"] == "stopping"
        clock.advance(30); driver.fail_stop = False; await service.tick()
    asyncio.run(case())
    assert driver.stops == 2
    assert service.remaining("u") == 13770
    assert db.one("SELECT reason FROM sessions")["reason"] == "inactivity"
    assert service.profile("u", "p")["error"] == ""


def add_schedule(db, clock, recurrence="once"):
    db.execute("INSERT INTO schedules VALUES('s','p','Check repo','Review repository',?,?,86400,900,0)", (recurrence, clock.now))


def test_scheduler_starts_closed_workspace_and_stops_after_result(rig):
    service, db, driver, clock = rig
    add_schedule(db, clock)
    async def case():
        await service.tick()
        await asyncio.gather(*service.pending)
        clock.advance(12)
        await service.tick()
    asyncio.run(case())
    assert driver.starts == driver.runs == driver.stops == 1
    assert db.one("SELECT status,output FROM tasks")["status"] == "succeeded"
    assert db.one("SELECT title FROM notifications")["title"] == "Scheduled task succeeded"
    assert db.one("SELECT paused FROM schedules")["paused"] == 1
    assert service.remaining("u") == 14388


def test_scheduler_does_not_duplicate_occurrence(rig):
    service, db, driver, clock = rig
    add_schedule(db, clock)
    async def case():
        await asyncio.gather(service.tick(), service.tick())
        await asyncio.gather(*service.pending)
        await service.tick(); await service.tick()
    asyncio.run(case())
    assert len(db.rows("SELECT * FROM tasks")) == 1
    assert driver.runs == 1


def test_scheduler_skips_exhausted_allowance(rig):
    service, db, driver, clock = rig
    add_schedule(db, clock)
    db.execute("INSERT INTO usage VALUES('u','2023-11-14',14400)")
    asyncio.run(service.tick())
    assert driver.starts == 0
    assert db.one("SELECT status FROM tasks")["status"] == "skipped"


def test_scheduler_waits_for_interactive_session(rig):
    service, db, driver, clock = rig
    add_schedule(db, clock)
    async def case(): await started(service); await service.tick()
    asyncio.run(case())
    assert driver.runs == 0
    assert db.one("SELECT paused FROM schedules")["paused"] == 0


def test_daily_recurrence_skips_missed_backlog(rig):
    service, db, driver, clock = rig
    add_schedule(db, clock, "daily")
    old = clock.now
    clock.advance(3 * 86400 + 2)
    async def case(): await service.tick(); await asyncio.gather(*service.pending)
    asyncio.run(case())
    assert db.one("SELECT next_run FROM schedules")["next_run"] == old + 4 * 86400
    assert driver.runs == 1


def test_task_timeout_stops_scheduled_session(rig):
    service, db, driver, clock = rig
    add_schedule(db, clock); driver.task_state = "running"
    async def case():
        await service.tick(); await asyncio.gather(*service.pending)
        clock.advance(900); await service.tick()
    asyncio.run(case())
    assert db.one("SELECT status FROM tasks")["status"] == "failed"
    assert driver.stops == 1


def test_crash_recovery_never_replays_task(rig):
    service, db, driver, clock = rig
    async def case():
        await started(service)
        service.enqueue("u", "p", "test")
        await asyncio.gather(*service.pending)
        clock.advance(42); await service.recover()
    asyncio.run(case())
    assert db.one("SELECT status FROM tasks")["status"] == "failed"
    assert driver.runs == driver.stops == 1
    assert service.remaining("u") == 14358


def test_request_idempotency_returns_original_task(rig):
    service, db, driver, clock = rig
    async def case():
        await started(service)
        first = service.enqueue("u", "p", "test", key="same")
        second = service.enqueue("u", "p", "test", key="same")
        assert first["id"] == second["id"]
        await asyncio.gather(*service.pending)
    asyncio.run(case())
    assert driver.runs == 1


def test_user_cannot_access_another_profile(rig):
    service, db, driver, clock = rig
    with pytest.raises(HTTPException) as error: service.profile("other-user", "p")
    assert error.value.status_code == 404


def test_multiple_profiles_share_single_live_session_and_allowance(rig):
    service, db, driver, clock = rig
    db.execute("INSERT INTO profiles(id,user_id,login,github_id,token,codespace,state) VALUES('p2','u','other',2,'encrypted','space2','stopped')")
    async def case():
        await started(service)
        with pytest.raises(HTTPException) as error: await service.start("u", "p2")
        assert error.value.status_code == 409
        clock.advance(60); service.charge()
    asyncio.run(case())
    assert service.usage("u", "p2")["used_seconds"] == 60


def test_bearer_tokens_hashed_and_github_tokens_encrypted(rig):
    service, db, driver, clock = rig
    security = Security(db, service.config)
    token = security.issue("u")
    assert token not in db.one("SELECT hash FROM auth_tokens")["hash"]
    stored = db.one("SELECT token FROM profiles")["token"]
    assert "secret-token" not in stored
    assert security.open(stored) == "secret-token"


def test_remote_file_paths_reject_escape_and_secret_symlinks(tmp_path):
    spec = importlib.util.spec_from_file_location("runtime_test", Path(__file__).resolve().parents[2] / "codespace/runtime.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.ROOT = tmp_path
    for path in ["../outside", "/etc/passwd", ".env", ".git/config", "nested/.ssh/key"]:
        with pytest.raises(ValueError): module.path_for(path)
    (tmp_path / "link").symlink_to("/etc/passwd")
    with pytest.raises(ValueError): module.path_for("link")
    assert module.dispatch({"operation": "write", "path": "src/test.txt", "content": "Saved"})["saved"]
    assert module.dispatch({"operation": "read", "path": "src/test.txt"})["content"] == "Saved"


def test_http_auth_validation_and_local_login(tmp_path):
    app = create_app(Config(database=str(tmp_path / "db"), demo=True), worker=False)
    with TestClient(app) as client:
        assert client.get("/profiles").status_code == 401
        token = client.post("/auth/local").json()["token"]
        headers = {"Authorization": "Bearer " + token}
        profile = client.get("/profiles", headers=headers).json()["profiles"][0]
        assert "token" not in profile
        path = "/profiles/" + profile["id"]
        assert client.post(path + "/connect", headers=headers, json={"repository": ";injected"}).status_code == 422
        assert client.post(path + "/extended", headers=headers, json={"seconds": 7201}).status_code == 422
        assert client.get("/profiles/other/usage", headers=headers).status_code == 404
        assert client.post("/auth/logout", headers=headers).status_code == 200
        assert client.get("/profiles", headers=headers).status_code == 401


def test_one_use_oauth_code_is_verifier_bound(tmp_path):
    app = create_app(Config(database=str(tmp_path / "db"), demo=True), worker=False)
    with TestClient(app) as client:
        client.post("/auth/local")
        db = app.state.db
        user_id = db.one("SELECT id FROM users")["id"]
        verifier = "v" * 43
        db.execute("INSERT INTO exchanges VALUES(?,?,?,?)", ("code" * 10, user_id, challenge(verifier), __import__("time").time() + 60))
        assert client.post("/auth/exchange", json={"code": "code" * 10, "verifier": "x" * 43}).status_code == 401
        assert client.post("/auth/exchange", json={"code": "code" * 10, "verifier": verifier}).status_code == 200
        assert client.post("/auth/exchange", json={"code": "code" * 10, "verifier": verifier}).status_code == 401


def test_production_requires_encryption_key_and_https():
    with pytest.raises(RuntimeError): create_app(Config(demo=False, encryption_key="", client_id="", client_secret=""), worker=False)
    with pytest.raises(RuntimeError): create_app(Config(demo=False, encryption_key=Fernet.generate_key().decode(), client_id="id", client_secret="secret"), worker=False)


def test_real_local_shell_and_file_roundtrip(tmp_path):
    app = create_app(Config(database=str(tmp_path / "db"), demo=True), worker=False)
    with TestClient(app) as client:
        token = client.post("/auth/local").json()["token"]
        headers = {"Authorization": "Bearer " + token}
        profile = client.get("/profiles", headers=headers).json()["profiles"][0]
        path = "/profiles/" + profile["id"]
        assert client.post(path + "/connect", headers=headers, json={"repository": "dev/repo"}).status_code == 200
        assert client.put(path + "/file", headers=headers, json={"path": "hello.txt", "content": "Coral"}).status_code == 200
        assert client.get(path + "/file?path=hello.txt", headers=headers).json()["content"] == "Coral"
        result = client.post(path + "/tasks", headers=headers, json={"kind": "terminal", "prompt": "cat hello.txt"})
        assert result.status_code == 202
        client.portal.call(asyncio.sleep, 0.1)
        client.portal.call(app.state.service.tick)
        task = client.get(path + "/tasks", headers=headers).json()["tasks"][0]
        assert task["status"] == "succeeded"
        assert task["output"] == "Coral"


def test_extended_api_updates_github_idle_timeout_and_returns_to_normal(tmp_path):
    class TimedDriver(LocalGitHub):
        def __init__(self, path): super().__init__(path); self.timeouts = []
        async def idle_timeout(self, profile, minutes): self.timeouts.append(minutes)
    driver = TimedDriver(tmp_path / "workspace")
    app = create_app(Config(database=str(tmp_path / "db"), demo=True), driver=driver, worker=False)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer " + client.post("/auth/local").json()["token"]}
        profile_id = client.get("/profiles", headers=headers).json()["profiles"][0]["id"]
        path = "/profiles/" + profile_id
        client.post(path + "/connect", headers=headers, json={"repository": "dev/repo"})
        response = client.post(path + "/extended", headers=headers, json={"seconds": 1800})
        assert response.status_code == 200
        assert response.json()["extended_until"] is not None
        assert driver.timeouts[-1] == 32
        response = client.post(path + "/extended", headers=headers, json={"seconds": 0})
        assert response.status_code == 200
        assert driver.timeouts[-1] == 10
        assert response.json()["extended_until"] is None


def test_request_stream_rejects_oversized_body(tmp_path):
    app = create_app(Config(database=str(tmp_path / "db"), demo=True), worker=False)
    with TestClient(app) as client:
        response = client.post("/auth/local", content=b"x" * (2 * 1024 * 1024 + 1))
        assert response.status_code == 413


def test_failed_shutdown_reports_elapsed_time_without_hiding_overrun(rig):
    service, db, driver, clock = rig
    clock.now = 1699920000
    async def case():
        await started(service)
        driver.fail_stop = True
        clock.advance(14460)
        await service.tick()
    asyncio.run(case())
    usage = service.usage("u", "p")
    assert usage["used_seconds"] == 14460
    assert usage["remaining_seconds"] == 0
    assert service.profile("u", "p")["state"] == "stopping"
