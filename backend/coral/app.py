import asyncio
import fcntl
import os
import re
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode
import httpx
from cryptography.fernet import InvalidToken
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from .admin import install_admin
from .config import Config
from .db import Database
from .github import GitHub, GitHubError, LocalGitHub
from .security import Security, challenge, digest
from .service import Service, identifier


class OAuthPrepare(BaseModel):
    challenge: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    client: Literal["native", "web"] = "native"
    link_account: bool = False


class OAuthExchange(BaseModel):
    code: str = Field(min_length=20, max_length=128)
    verifier: str = Field(min_length=43, max_length=128)


class ProfileConnect(BaseModel):
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    codespace: str = Field(default="", pattern=r"^[A-Za-z0-9-]*$")


class Extension(BaseModel):
    seconds: int = Field(ge=0, le=7200)


class Activity(BaseModel):
    kind: Literal["chat", "terminal", "file", "navigation", "session"]


class Run(BaseModel):
    prompt: str = Field(min_length=1, max_length=32000)
    kind: Literal["hermes", "terminal"] = "hermes"
    duration_limit: int = Field(default=900, ge=10, le=7200)


class FileWrite(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    content: str = Field(max_length=1048576)


class HermesToggle(BaseModel):
    enabled: bool


class Schedule(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=32000)
    recurrence: Literal["once", "daily", "weekly", "recurring"]
    next_run: float = Field(gt=0)
    interval_seconds: int = Field(default=86400, ge=300, le=31536000)
    duration_limit: int = Field(default=900, ge=10, le=7200)
    paused: bool = False


def create_app(config=None, driver=None, database=None, worker=True):
    config = config or Config()
    config.validate()
    db = database or Database(config.database, config.database_url)
    security = Security(db, config)
    github = driver or (LocalGitHub(Path(config.database).parent / "workspace") if config.demo else GitHub(security))
    service = Service(db, config, github)

    @asynccontextmanager
    async def lifespan(app):
        lock = None
        loop = None
        if worker:
            lock_path = Path(config.database).with_suffix(".worker.lock")
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock = lock_path.open("w")
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Coral requires one control-plane worker per database. Start uvicorn with --workers 1.")
            await service.recover()
            loop = asyncio.create_task(service.loop())
        try:
            yield
        finally:
            if loop:
                loop.cancel()
                await asyncio.gather(loop, return_exceptions=True)
            for task in list(service.pending):
                task.cancel()
            await asyncio.gather(*service.pending, return_exceptions=True)
            if worker:
                for session in db.rows("SELECT * FROM sessions WHERE ended IS NULL"):
                    await service.stop(session["user_id"], session["profile_id"], "backend_shutdown")
            if lock:
                lock.close()

    app = FastAPI(title="Coral", version="1.0.0", lifespan=lifespan, docs_url="/docs" if config.demo else None, redoc_url=None)
    app.state.service, app.state.db, app.state.security = service, db, security
    app.add_middleware(CORSMiddleware, allow_origins=[config.web_url.rstrip("/").split("/", 3)[0] + "//" + config.web_url.split("/")[2]], allow_credentials=False, allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type", "Idempotency-Key"])
    install_admin(app, config, security)
    rates = defaultdict(deque)

    @app.middleware("http")
    async def request_guard(request, call_next):
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        if len(rates) > 10000:
            for key in list(rates):
                if not rates[key] or rates[key][-1] < now - 60:
                    del rates[key]
        admin_login = request.method == "POST" and request.url.path == "/admin/login"
        queue = rates[ip, admin_login]
        while queue and queue[0] < now - 60:
            queue.popleft()
        if len(queue) >= (8 if admin_login else 240):
            return JSONResponse({"detail": "Too many requests. Try again shortly."}, 429)
        queue.append(now)
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 2 * 1024 * 1024:
                return JSONResponse({"detail": "Request too large."}, 413)
            chunks.append(chunk)
        request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(GitHubError)
    async def github_error(request, error):
        return JSONResponse({"detail": str(error)}, 502)

    def user(authorization: str = Header(default="")):
        return security.authenticate(authorization)

    def oauth_credentials():
        try:
            credentials = security.github_oauth_credentials()
        except InvalidToken:
            raise HTTPException(503, "The saved GitHub OAuth credentials are unreadable. Ask the Coral administrator to save them again.") from None
        if not credentials:
            raise HTTPException(503, "GitHub sign-in is awaiting setup. Ask the Coral administrator to configure the GitHub OAuth app.")
        return credentials

    @app.get("/health")
    async def health():
        return {"status": "ok", "name": "Coral", "mode": "local" if config.demo else "production",
                "storage": db.engine, "hosting": config.hosting_mode}

    @app.post("/internal/tick")
    async def external_tick(x_coral_scheduler_token: str = Header(default="")):
        if not config.scheduler_token:
            raise HTTPException(404, "Not found")
        if not secrets.compare_digest(config.scheduler_token, x_coral_scheduler_token):
            raise HTTPException(401, "Invalid scheduler credential.")
        service.wake.set()
        return {"accepted": True}

    @app.post("/auth/local")
    async def local_login(request: Request):
        if not config.demo or not request.client or request.client.host not in ("127.0.0.1", "::1", "testclient"):
            raise HTTPException(404, "Not found")
        existing = db.one("SELECT * FROM users WHERE github_id=0")
        if not existing:
            user_id, profile_id = identifier(), identifier()
            with db.transaction() as tx:
                tx.execute("INSERT INTO users VALUES(?,?,0)", (user_id, "Local workspace"))
                tx.execute("INSERT INTO profiles(id,user_id,login,github_id,token) VALUES(?,?,?,0,?)", (profile_id, user_id, "Local workspace", security.seal("development")))
        else:
            user_id = existing["id"]
        return {"token": security.issue(user_id), "local": True}

    @app.post("/auth/prepare")
    async def prepare(body: OAuthPrepare, authorization: str = Header(default="")):
        client_id, _ = oauth_credentials()
        user_id = security.authenticate(authorization) if body.link_account else None
        state = secrets.token_urlsafe(32) + "." + digest(client_id)
        db.execute("DELETE FROM oauth WHERE expires<?", (time.time(),))
        db.execute("INSERT INTO oauth (state,challenge,client,user_id,expires) VALUES (?,?,?,?,?)",
                   (state, body.challenge, body.client, user_id, time.time() + 600))
        scope = os.getenv("GITHUB_OAUTH_SCOPES", "codespace")
        url = "https://github.com/login/oauth/authorize?" + urlencode({"client_id": client_id, "redirect_uri": config.oauth_callback_url, "scope": scope, "state": state, "allow_signup": "false"})
        return {"url": url}

    @app.get("/auth/callback")
    async def callback(state: str, code: str = "", error: str = ""):
        with db.transaction() as tx:
            attempt = tx.execute("SELECT * FROM oauth WHERE state=? AND expires>?", (state, time.time())).fetchone()
            if not attempt:
                raise HTTPException(400, "Sign-in request expired or was already used.")
            attempt = dict(attempt)
            tx.execute("DELETE FROM oauth WHERE state=?", (state,))
        target = "coral://auth" if attempt["client"] == "native" else config.web_url.rstrip("/") + "/"
        if error or not code:
            return RedirectResponse(target + "?" + urlencode({"error": "GitHub sign-in was cancelled."}), 302)
        client_id, client_secret = oauth_credentials()
        _, _, client_fingerprint = state.partition(".")
        if client_fingerprint and client_fingerprint != digest(client_id):
            return RedirectResponse(target + "?" + urlencode({"error": "The GitHub OAuth app changed. Start sign-in again."}), 302)
        async with httpx.AsyncClient(timeout=30) as client:
            result = await client.post("https://github.com/login/oauth/access_token", headers={"Accept": "application/json"}, data={"client_id": client_id, "client_secret": client_secret, "code": code, "redirect_uri": config.oauth_callback_url})
            token = result.json().get("access_token")
            if not token:
                raise HTTPException(401, "GitHub could not complete sign-in.")
            identity = await client.get("https://api.github.com/user", headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"})
            identity.raise_for_status()
            identity = identity.json()
        github_id, login = identity["id"], identity["login"]
        existing = db.one("SELECT user_id FROM profiles WHERE github_id=? ORDER BY rowid LIMIT 1", (github_id,))
        user_id = attempt["user_id"] or (existing["user_id"] if existing else identifier())
        with db.transaction() as tx:
            tx.execute("INSERT OR IGNORE INTO users VALUES(?,?,?)", (user_id, login, github_id))
            profile = tx.execute("SELECT id FROM profiles WHERE user_id=? AND github_id=?", (user_id, github_id)).fetchone()
            if profile:
                tx.execute("UPDATE profiles SET token=?,login=? WHERE id=?", (security.seal(token), login, profile["id"]))
            else:
                tx.execute("INSERT INTO profiles(id,user_id,login,github_id,token) VALUES(?,?,?,?,?)", (identifier(), user_id, login, github_id, security.seal(token)))
            exchange = secrets.token_urlsafe(32)
            tx.execute("INSERT INTO exchanges VALUES(?,?,?,?)", (exchange, user_id, attempt["challenge"], time.time() + 60))
        # Native receives a single-use, verifier-bound code, never a GitHub or Coral bearer token.
        return RedirectResponse(target + ("?code=" if attempt["client"] == "native" else "#code=") + exchange, 302)

    @app.post("/auth/exchange")
    async def exchange(body: OAuthExchange):
        with db.transaction() as tx:
            record = tx.execute("SELECT * FROM exchanges WHERE code=? AND expires>?", (body.code, time.time())).fetchone()
            if not record or not secrets.compare_digest(record["challenge"], challenge(body.verifier)):
                raise HTTPException(401, "Invalid or expired sign-in code.")
            user_id = record["user_id"]
            tx.execute("DELETE FROM exchanges WHERE code=?", (body.code,))
        return {"token": security.issue(user_id)}

    @app.post("/auth/logout")
    async def logout(user_id=Depends(user), authorization: str = Header(default="")):
        db.execute("DELETE FROM auth_tokens WHERE hash=?", (digest(authorization.removeprefix("Bearer ")),))
        return {"signed_out": True}

    @app.get("/profiles")
    async def profiles(user_id=Depends(user)):
        return {"profiles": [service.public_profile(p) for p in db.rows("SELECT * FROM profiles WHERE user_id=? ORDER BY rowid", (user_id,))]}

    @app.post("/profiles/{profile_id}/connect")
    async def connect(profile_id: str, body: ProfileConnect, user_id=Depends(user)):
        return await service.configure(user_id, profile_id, body.repository, body.codespace)

    @app.post("/profiles/{profile_id}/disconnect")
    async def disconnect(profile_id: str, user_id=Depends(user)):
        service.profile(user_id, profile_id)
        await service.stop(user_id, profile_id, "disconnected")
        if db.one("SELECT id FROM sessions WHERE profile_id=? AND ended IS NULL", (profile_id,)):
            raise HTTPException(409, "Shutdown is still pending. Retry after it is confirmed.")
        db.execute("UPDATE profiles SET codespace='',repository='',state='unconfigured',hermes=0 WHERE id=?", (profile_id,))
        db.execute("UPDATE schedules SET paused=1 WHERE profile_id=?", (profile_id,))
        return {"disconnected": True}

    @app.get("/profiles/{profile_id}/usage")
    async def usage(profile_id: str, user_id=Depends(user)):
        return service.usage(user_id, profile_id)

    @app.post("/profiles/{profile_id}/start")
    async def start(profile_id: str, user_id=Depends(user)):
        return await service.start(user_id, profile_id)

    @app.post("/profiles/{profile_id}/stop")
    async def stop(profile_id: str, user_id=Depends(user)):
        await service.stop(user_id, profile_id)
        return service.public_profile(service.profile(user_id, profile_id))

    @app.post("/profiles/{profile_id}/activity")
    async def activity(profile_id: str, body: Activity, user_id=Depends(user)):
        service.activity(user_id, profile_id)
        return {"recorded": True}

    @app.post("/profiles/{profile_id}/extended")
    async def extended(profile_id: str, body: Extension, user_id=Depends(user)):
        profile = service.profile(user_id, profile_id)
        session = db.one("SELECT id FROM sessions WHERE profile_id=? AND ended IS NULL AND mode='interactive'", (profile_id,))
        if not session or profile["state"] != "available":
            raise HTTPException(409, "Start an interactive session first.")
        # Let Coral own expiration; GitHub's native idle timer must not pre-empt a valid extension.
        minutes = 10 if body.seconds == 0 else max(10, (body.seconds + 59) // 60 + 2)
        await github.idle_timeout(profile, minutes)
        return service.extend(user_id, profile_id, body.seconds)

    async def remote(user_id, profile_id, body):
        profile = service.profile(user_id, profile_id)
        service.charge()
        if profile["state"] != "available" or service.remaining(user_id) <= config.stop_reserve:
            raise HTTPException(409, "Codespace is stopped or your allowance is exhausted.")
        result = await github.remote(profile, body)
        if result.get("error"):
            raise HTTPException(400, result["error"])
        return result

    @app.post("/profiles/{profile_id}/hermes")
    async def hermes(profile_id: str, body: HermesToggle, user_id=Depends(user)):
        result = await remote(user_id, profile_id, {"operation": "hermes", "enabled": body.enabled})
        db.execute("UPDATE profiles SET hermes=? WHERE id=?", (int(body.enabled), profile_id))
        if not body.enabled:
            for task in db.rows("SELECT * FROM tasks WHERE profile_id=? AND kind='hermes' AND status IN ('queued','running')", (profile_id,)):
                await service.cancel(user_id, profile_id, task["id"])
        service.activity(user_id, profile_id)
        return result

    @app.get("/profiles/{profile_id}/ssh")
    async def ssh(profile_id: str, user_id=Depends(user)):
        profile = service.profile(user_id, profile_id)
        if not profile["codespace"]:
            raise HTTPException(409, "Connect a Codespace first.")
        return {"codespace": profile["codespace"], "account": profile["login"], "command": f'gh codespace ssh --codespace {profile["codespace"]}', "config_command": f'gh codespace ssh --codespace {profile["codespace"]} --config'}

    @app.get("/profiles/{profile_id}/files")
    async def files(profile_id: str, path: str = "", user_id=Depends(user)):
        return await remote(user_id, profile_id, {"operation": "files", "path": path})

    @app.get("/profiles/{profile_id}/file")
    async def file(profile_id: str, path: str, user_id=Depends(user)):
        return await remote(user_id, profile_id, {"operation": "read", "path": path})

    @app.put("/profiles/{profile_id}/file")
    async def write(profile_id: str, body: FileWrite, user_id=Depends(user)):
        result = await remote(user_id, profile_id, {"operation": "write", "path": body.path, "content": body.content})
        service.activity(user_id, profile_id)
        return result

    @app.get("/profiles/{profile_id}/tasks")
    async def tasks(profile_id: str, user_id=Depends(user)):
        service.profile(user_id, profile_id)
        return {"tasks": db.rows("SELECT * FROM tasks WHERE profile_id=? ORDER BY created DESC LIMIT 100", (profile_id,))}

    @app.post("/profiles/{profile_id}/tasks", status_code=202)
    async def run(profile_id: str, body: Run, user_id=Depends(user), idempotency_key: str = Header(default="")):
        if len(idempotency_key) > 128:
            raise HTTPException(400, "Invalid request key")
        return service.enqueue(user_id, profile_id, body.prompt, body.kind, body.duration_limit, idempotency_key or None)

    @app.post("/profiles/{profile_id}/tasks/{task_id}/cancel")
    async def cancel(profile_id: str, task_id: str, user_id=Depends(user)):
        return await service.cancel(user_id, profile_id, task_id)

    @app.get("/profiles/{profile_id}/tasks/{task_id}/events")
    async def events(profile_id: str, task_id: str, request: Request, user_id=Depends(user)):
        service.profile(user_id, profile_id)
        async def stream():
            last = None
            while not await request.is_disconnected():
                task = db.one("SELECT * FROM tasks WHERE id=? AND profile_id=?", (task_id, profile_id))
                if not task:
                    break
                if task != last:
                    import json
                    yield "event: progress\ndata: " + json.dumps(task) + "\n\n"
                    last = task
                else:
                    yield ": waiting\n\n"
                if task["status"] not in ("queued", "running"):
                    break
                await asyncio.sleep(1)
        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/profiles/{profile_id}/schedules")
    async def schedules(profile_id: str, user_id=Depends(user)):
        service.profile(user_id, profile_id)
        return {"schedules": db.rows("SELECT * FROM schedules WHERE profile_id=? ORDER BY next_run", (profile_id,))}

    def save_schedule(user_id, profile_id, body, schedule_id=None):
        service.profile(user_id, profile_id)
        if schedule_id and not db.one("SELECT id FROM schedules WHERE id=? AND profile_id=?", (schedule_id, profile_id)):
            raise HTTPException(404, "Schedule not found.")
        interval = {"daily": 86400, "weekly": 604800}.get(body.recurrence, body.interval_seconds)
        schedule_id = schedule_id or identifier()
        db.execute("INSERT INTO schedules VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,prompt=excluded.prompt,recurrence=excluded.recurrence,next_run=excluded.next_run,interval_seconds=excluded.interval_seconds,duration_limit=excluded.duration_limit,paused=excluded.paused", (schedule_id, profile_id, body.title, body.prompt, body.recurrence, body.next_run, interval, body.duration_limit, int(body.paused)))
        service.wake.set()
        return db.one("SELECT * FROM schedules WHERE id=?", (schedule_id,))

    @app.post("/profiles/{profile_id}/schedules", status_code=201)
    async def add_schedule(profile_id: str, body: Schedule, user_id=Depends(user)):
        return save_schedule(user_id, profile_id, body)

    @app.put("/profiles/{profile_id}/schedules/{schedule_id}")
    async def edit_schedule(profile_id: str, schedule_id: str, body: Schedule, user_id=Depends(user)):
        return save_schedule(user_id, profile_id, body, schedule_id)

    @app.delete("/profiles/{profile_id}/schedules/{schedule_id}")
    async def delete_schedule(profile_id: str, schedule_id: str, user_id=Depends(user)):
        service.profile(user_id, profile_id)
        db.execute("DELETE FROM schedules WHERE id=? AND profile_id=?", (schedule_id, profile_id))
        return {"deleted": True}

    @app.get("/notifications")
    async def notifications(user_id=Depends(user)):
        return {"notifications": db.rows("SELECT * FROM notifications WHERE user_id=? ORDER BY created DESC LIMIT 100", (user_id,))}

    @app.post("/notifications/{notification_id}/read")
    async def read_notification(notification_id: str, user_id=Depends(user)):
        db.execute("UPDATE notifications SET read=1 WHERE id=? AND user_id=?", (notification_id, user_id))
        return {"read": True}

    return app


def production_app():
    return create_app()
