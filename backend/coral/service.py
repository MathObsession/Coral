import asyncio
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

log = logging.getLogger("coral")


def identifier():
    return str(uuid.uuid4())


def day_of(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()


class Service:
    def __init__(self, db, config, github, clock=time.time):
        self.db, self.config, self.github, self.clock = db, config, github, clock
        self.operations = defaultdict(asyncio.Lock)
        self.pending = set()
        self.wake = asyncio.Event()

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.pending.add(task)
        task.add_done_callback(self.pending.discard)
        return task

    def profile(self, user_id, profile_id):
        profile = self.db.one("SELECT * FROM profiles WHERE id=? AND user_id=?", (profile_id, user_id))
        if not profile:
            raise HTTPException(404, "Profile not found.")
        return profile

    def charge(self, now=None):
        now = self.clock() if now is None else now
        with self.db.transaction() as tx:
            for session in tx.execute("SELECT * FROM sessions WHERE ended IS NULL").fetchall():
                cursor = session["accounted"]
                while cursor < now:
                    day = day_of(cursor)
                    midnight = (datetime.fromtimestamp(cursor, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp()
                    end = min(now, midnight)
                    amount = end - cursor
                    tx.execute("INSERT INTO usage VALUES(?,?,?) ON CONFLICT(user_id,day) DO UPDATE SET seconds=seconds+excluded.seconds", (session["user_id"], day, amount))
                    tx.execute("INSERT INTO profile_usage VALUES(?,?,?) ON CONFLICT(profile_id,day) DO UPDATE SET seconds=seconds+excluded.seconds", (session["profile_id"], day, amount))
                    cursor = end
                tx.execute("UPDATE sessions SET accounted=? WHERE id=?", (max(now, session["accounted"]), session["id"]))

    def remaining(self, user_id):
        row = self.db.one("SELECT seconds FROM usage WHERE user_id=? AND day=?", (user_id, day_of(self.clock())))
        return max(0, self.config.allowance - (row["seconds"] if row else 0))

    def usage(self, user_id, profile_id):
        self.profile(user_id, profile_id)
        self.charge()
        now = self.clock()
        session = self.db.one("SELECT * FROM sessions WHERE profile_id=? AND ended IS NULL", (profile_id,))
        left = self.remaining(user_id)
        day_usage = self.db.one("SELECT seconds FROM usage WHERE user_id=? AND day=?", (user_id, day_of(now)))
        extended = session and session["extended_until"] and session["extended_until"] > now
        history = self.db.rows("SELECT * FROM sessions WHERE profile_id=? ORDER BY started DESC LIMIT 100", (profile_id,))
        daily = self.db.rows("SELECT * FROM profile_usage WHERE profile_id=? ORDER BY day DESC LIMIT 30", (profile_id,))
        return {"allowance_seconds": self.config.allowance, "used_seconds": day_usage["seconds"] if day_usage else 0,
                "remaining_seconds": left, "server_time": now, "session": session,
                "session_seconds": max(0, now - session["started"]) if session else 0,
                "inactivity_seconds": max(0, (session["extended_until"] if extended else session["last_activity"] + self.config.idle_seconds) - now) if session else 0,
                "extended_until": session["extended_until"] if extended else None, "history": history, "daily": daily}

    def reserve_session(self, profile, mode="interactive"):
        self.charge()
        now = self.clock()
        remaining = self.remaining(profile["user_id"])
        if remaining <= self.config.stop_reserve:
            raise HTTPException(403, "Today's four-hour allowance is exhausted. It resets at 00:00 UTC.")
        with self.db.transaction() as tx:
            live = tx.execute("SELECT * FROM sessions WHERE user_id=? AND ended IS NULL", (profile["user_id"],)).fetchone()
            if live:
                if live["profile_id"] != profile["id"] or live["mode"] != mode:
                    raise HTTPException(409, "Stop the active session before using another profile or running scheduled work.")
                return dict(live), False
            session_id = identifier()
            tx.execute("INSERT INTO sessions(id,user_id,profile_id,mode,started,accounted,last_activity,deadline) VALUES(?,?,?,?,?,?,?,?)",
                       (session_id, profile["user_id"], profile["id"], mode, now, now, now, now + remaining - self.config.stop_reserve))
            tx.execute("UPDATE profiles SET state='starting',error='' WHERE id=?", (profile["id"],))
        return self.db.one("SELECT * FROM sessions WHERE id=?", (session_id,)), True

    async def configure(self, user_id, profile_id, repository, codespace):
        async with self.operations[profile_id]:
            profile = self.profile(user_id, profile_id)
            if profile["codespace"]:
                raise HTTPException(409, "This profile already has a Codespace. Stop and disconnect it before changing repositories.")
            session, _ = self.reserve_session(profile)
            self.db.execute("UPDATE profiles SET repository=? WHERE id=?", (repository, profile_id))
            try:
                name = await self.github.bind(profile, repository, codespace)
                self.db.execute("UPDATE profiles SET repository=?,codespace=? WHERE id=?", (repository, name, profile_id))
                profile = self.profile(user_id, profile_id)
                await self.activate(profile, session)
            except BaseException:
                await self.stop(user_id, profile_id, "configuration_failed")
                raise
        return self.public_profile(self.profile(user_id, profile_id))

    async def activate(self, profile, session):
        try:
            await self.github.idle_timeout(profile, 10)
            state = await self.github.inspect(profile)
            if state.get("state") != "Available":
                await self.github.start(profile)
            for _ in range(90):
                current = self.db.one("SELECT * FROM sessions WHERE id=?", (session["id"],))
                if current["ended"] or self.clock() >= current["deadline"]:
                    await self.github.stop(profile)
                    return
                state = await self.github.inspect(profile)
                if state.get("state") == "Available":
                    break
                await asyncio.sleep(2)
            else:
                raise RuntimeError("Codespace did not become available within three minutes.")
            await self.github.provision(profile)
            current = self.db.one("SELECT * FROM sessions WHERE id=?", (session["id"],))
            if current["ended"] or self.clock() >= current["deadline"]:
                await self.stop(profile["user_id"], profile["id"], "startup_deadline")
                return
            await self.github.remote(profile, {"operation": "hermes", "enabled": True})
            self.db.execute("UPDATE profiles SET state='available',hermes=1,error='' WHERE id=? AND state='starting'", (profile["id"],))
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.db.execute("UPDATE profiles SET error=? WHERE id=?", (str(error), profile["id"]))
            await self.stop(profile["user_id"], profile["id"], "startup_failed")

    async def start(self, user_id, profile_id):
        async with self.operations[profile_id]:
            profile = self.profile(user_id, profile_id)
            if not profile["codespace"]:
                raise HTTPException(400, "Connect a repository and Codespace in Profiles first.")
            session, created = self.reserve_session(profile)
            if created:
                self.spawn(self.activate(profile, session))
        return self.public_profile(self.profile(user_id, profile_id))

    async def stop(self, user_id, profile_id, reason="user_stopped"):
        profile = self.profile(user_id, profile_id)
        self.db.execute("UPDATE profiles SET state='stopping' WHERE id=?", (profile_id,))
        for task in self.db.rows("SELECT * FROM tasks WHERE profile_id=? AND status IN ('queued','running')", (profile_id,)):
            try:
                if profile["codespace"]:
                    await self.github.remote(profile, {"operation": "cancel", "id": task["id"]})
            except Exception:
                pass
            self.finish(task, "cancelled", error=reason)
        try:
            if profile["codespace"]:
                await self.github.stop(profile)
                state = await self.github.inspect(profile)
                if state.get("state") not in ("Shutdown", "Deleted", "Archived", "Failed"):
                    return # Leave authoritative session active and retry until shutdown is confirmed.
        except Exception as error:
            self.db.execute("UPDATE profiles SET error=? WHERE id=?", (str(error), profile_id))
            return
        self.charge()
        self.db.execute("UPDATE sessions SET ended=?,reason=?,extended_until=NULL WHERE profile_id=? AND ended IS NULL", (self.clock(), reason, profile_id))
        self.db.execute("UPDATE profiles SET state=?,hermes=0 WHERE id=?", ("stopped" if profile["codespace"] else "unconfigured", profile_id))

    def activity(self, user_id, profile_id):
        self.profile(user_id, profile_id)
        self.db.execute("UPDATE sessions SET last_activity=? WHERE profile_id=? AND mode='interactive' AND ended IS NULL", (self.clock(), profile_id))

    def extend(self, user_id, profile_id, seconds):
        profile = self.profile(user_id, profile_id)
        session = self.db.one("SELECT * FROM sessions WHERE profile_id=? AND ended IS NULL AND mode='interactive'", (profile_id,))
        if not session or profile["state"] != "available":
            raise HTTPException(409, "Start an interactive session first.")
        self.charge()
        until = min(self.clock() + seconds, session["deadline"])
        if seconds == 0:
            until = None
            self.activity(user_id, profile_id)
        self.db.execute("UPDATE sessions SET extended_until=? WHERE id=?", (until, session["id"]))
        return self.usage(user_id, profile_id)

    def enqueue(self, user_id, profile_id, prompt, kind="hermes", duration=900, key=None, schedule=None):
        profile = self.profile(user_id, profile_id)
        self.charge()
        if key:
            prior = self.db.one("SELECT task_id FROM requests WHERE user_id=? AND key=?", (user_id, key))
            if prior:
                return self.db.one("SELECT * FROM tasks WHERE id=?", (prior["task_id"],))
        if not schedule and profile["state"] != "available":
            raise HTTPException(409, "Start your Codespace and wait until it is ready.")
        if kind == "hermes" and not schedule and not profile["hermes"]:
            raise HTTPException(409, "Start Hermes first.")
        session = self.db.one("SELECT * FROM sessions WHERE profile_id=? AND ended IS NULL", (profile_id,))
        if not session:
            raise HTTPException(409, "No active session.")
        if self.remaining(user_id) <= self.config.stop_reserve:
            raise HTTPException(403, "Daily allowance exhausted.")
        now = self.clock()
        task_id = identifier()
        try:
            with self.db.transaction() as tx:
                tx.execute("INSERT INTO tasks(id,profile_id,schedule_id,occurrence,kind,prompt,status,created,deadline) VALUES(?,?,?,?,?,?,?,?,?)", (task_id, profile_id, schedule["id"] if schedule else None, schedule["next_run"] if schedule else None, kind, prompt, "queued", now, min(now + duration, session["deadline"])))
                if key:
                    tx.execute("INSERT INTO requests VALUES(?,?,?)", (user_id, key, task_id))
                if schedule:
                    self.advance_schedule(tx, schedule, now)
        except Exception as error:
            import sqlite3
            if isinstance(error, sqlite3.IntegrityError):
                raise HTTPException(409, "A task is already running or this scheduled occurrence was already executed.")
            raise
        if not schedule:
            self.activity(user_id, profile_id)
        task = self.db.one("SELECT * FROM tasks WHERE id=?", (task_id,))
        self.spawn(self.launch(profile, task))
        return task

    async def launch(self, profile, task):
        try:
            for _ in range(200):
                current = self.db.one("SELECT status FROM tasks WHERE id=?", (task["id"],))
                if current["status"] != "queued":
                    return
                p = self.profile(profile["user_id"], profile["id"])
                if p["state"] == "available":
                    break
                if p["state"] not in ("starting",) or self.clock() >= task["deadline"]:
                    raise RuntimeError("Session unavailable or task startup limit reached.")
                await asyncio.sleep(2)
            else:
                raise RuntimeError("Session startup timed out.")
            result = await self.github.remote(profile, {"operation": "run", "id": task["id"], "kind": task["kind"], "prompt": task["prompt"], "deadline": task["deadline"]})
            if result.get("status") == "failed":
                self.finish(task, "failed", result.get("output", ""), result.get("error", ""))
            else:
                self.db.execute("UPDATE tasks SET status='running' WHERE id=? AND status='queued'", (task["id"],))
        except Exception as error:
            self.finish(task, "failed", error=str(error))

    def finish(self, task, status, output="", error=""):
        with self.db.transaction() as tx:
            cursor = tx.execute("UPDATE tasks SET status=?,output=CASE WHEN ?='' THEN output ELSE ? END,error=?,finished=? WHERE id=? AND status IN ('queued','running')", (status, output, output, error, self.clock(), task["id"]))
            if cursor.rowcount:
                profile = tx.execute("SELECT user_id FROM profiles WHERE id=?", (task["profile_id"],)).fetchone()
                tx.execute("INSERT INTO notifications VALUES(?,?,?,?,?,0)", (identifier(), profile["user_id"], task["id"], f"{'Scheduled task' if task['schedule_id'] else 'Task'} {status}", self.clock()))

    async def cancel(self, user_id, profile_id, task_id):
        profile = self.profile(user_id, profile_id)
        task = self.db.one("SELECT * FROM tasks WHERE id=? AND profile_id=?", (task_id, profile_id))
        if not task:
            raise HTTPException(404, "Task not found.")
        if task["status"] in ("queued", "running"):
            self.finish(task, "cancelled", error="Cancelled by user")
            try:
                await self.github.remote(profile, {"operation": "cancel", "id": task_id})
            except Exception:
                await self.stop(user_id, profile_id, "cancellation_connection_failed")
        return self.db.one("SELECT * FROM tasks WHERE id=?", (task_id,))

    @staticmethod
    def advance_schedule(tx, schedule, now):
        if schedule["recurrence"] == "once":
            tx.execute("UPDATE schedules SET paused=1 WHERE id=?", (schedule["id"],))
        else:
            interval = schedule["interval_seconds"]
            next_run = schedule["next_run"] + (int(max(0, now - schedule["next_run"]) / interval) + 1) * interval
            tx.execute("UPDATE schedules SET next_run=? WHERE id=?", (next_run, schedule["id"]))

    async def tick(self):
        self.charge()
        now = self.clock()
        for session in self.db.rows("SELECT * FROM sessions WHERE ended IS NULL"):
            profile = self.profile(session["user_id"], session["profile_id"])
            extended = session["extended_until"] and session["extended_until"] > now
            reason = None
            if profile["state"] == "stopping":
                reason = "shutdown_retry"
            elif now >= session["deadline"] or self.remaining(session["user_id"]) <= self.config.stop_reserve:
                reason = "daily_allowance"
            elif session["mode"] == "interactive" and not extended and now - session["last_activity"] >= self.config.idle_seconds:
                reason = "inactivity"
            if reason:
                await self.stop(session["user_id"], session["profile_id"], reason)
                continue
            if session["extended_until"] and not extended and profile["state"] == "available":
                try:
                    await self.github.idle_timeout(profile, 10)
                    self.db.execute("UPDATE sessions SET extended_until=NULL WHERE id=?", (session["id"],))
                except Exception:
                    self.db.execute("UPDATE profiles SET error='Cannot restore GitHub idle timeout yet. Coral still enforces the normal inactivity deadline.' WHERE id=?", (profile["id"],))
            if profile["state"] == "available":
                try:
                    state = await self.github.inspect(profile)
                    if state.get("state") in ("Shutdown", "Deleted", "Archived", "Failed"):
                        await self.stop(session["user_id"], session["profile_id"], "externally_stopped")
                        continue
                except Exception:
                    self.db.execute("UPDATE profiles SET error='Cannot reach GitHub. Automatic shutdown will be retried.' WHERE id=?", (profile["id"],))
            for task in self.db.rows("SELECT * FROM tasks WHERE profile_id=? AND status IN ('queued','running')", (profile["id"],)):
                if now >= task["deadline"]:
                    await self.cancel(session["user_id"], profile["id"], task["id"])
                    self.db.execute("UPDATE tasks SET status='failed',error='Task duration limit reached.' WHERE id=?", (task["id"],))
                elif task["status"] == "running":
                    try:
                        result = await self.github.remote(profile, {"operation": "poll", "id": task["id"]})
                        self.db.execute("UPDATE tasks SET output=? WHERE id=? AND status='running'", (result.get("output", ""), task["id"]))
                        if result["status"] != "running":
                            self.finish(task, result["status"], result.get("output", ""), result.get("error", ""))
                    except Exception:
                        # Deadline is never extended by connection failures.
                        self.db.execute("UPDATE profiles SET error='Task connection interrupted. Retrying until the task deadline.' WHERE id=?", (profile["id"],))
            if session["mode"] == "scheduled" and not self.db.one("SELECT id FROM tasks WHERE profile_id=? AND status IN ('queued','running')", (profile["id"],)):
                await self.stop(session["user_id"], profile["id"], "scheduled_complete")
        for schedule in self.db.rows("SELECT s.*,p.user_id FROM schedules s JOIN profiles p ON s.profile_id=p.id WHERE paused=0 AND next_run<=?", (now,)):
            profile = self.profile(schedule["user_id"], schedule["profile_id"])
            if not profile["codespace"] or self.db.one("SELECT id FROM sessions WHERE user_id=? AND ended IS NULL", (profile["user_id"],)):
                continue
            if self.remaining(profile["user_id"]) <= self.config.stop_reserve:
                task_id = identifier()
                with self.db.transaction() as tx:
                    tx.execute("INSERT OR IGNORE INTO tasks(id,profile_id,schedule_id,occurrence,kind,prompt,status,error,created,deadline,finished) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (task_id, profile["id"], schedule["id"], schedule["next_run"], "hermes", schedule["prompt"], "skipped", "Daily allowance exhausted", now, now, now))
                    self.advance_schedule(tx, schedule, now)
                    tx.execute("INSERT INTO notifications VALUES(?,?,?,?,?,0)", (identifier(), profile["user_id"], task_id, "Scheduled task skipped: daily allowance exhausted", now))
                continue
            session, _ = self.reserve_session(profile, "scheduled")
            self.enqueue(profile["user_id"], profile["id"], schedule["prompt"], duration=schedule["duration_limit"], schedule=schedule)
            self.spawn(self.activate(profile, session))

    async def recover(self):
        # A crash never resumes commands blindly. Retain elapsed accounting, stop the VM, publish failures.
        self.charge()
        for task in self.db.rows("SELECT * FROM tasks WHERE status IN ('queued','running')"):
            self.finish(task, "failed", error="Backend restarted. Execution was not replayed.")
        for session in self.db.rows("SELECT * FROM sessions WHERE ended IS NULL"):
            await self.stop(session["user_id"], session["profile_id"], "backend_recovered")

    async def loop(self):
        while True:
            try:
                self.db.execute("INSERT INTO metadata VALUES('worker_heartbeat',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (self.clock(),))
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Control-plane tick failed; will retry")
            self.wake.clear()
            try:
                await asyncio.wait_for(self.wake.wait(), self.config.tick_seconds)
            except asyncio.TimeoutError:
                pass

    @staticmethod
    def public_profile(profile):
        return {k: v for k, v in profile.items() if k not in ("token", "user_id", "github_id")}
