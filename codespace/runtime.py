#!/usr/bin/env python3
"""Private SSH-only bridge. No listening ports, credentials, or public shell API."""
import base64
import fcntl
import json
import os
import re
import signal
import selectors
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("CORAL_WORKSPACE", "/workspaces/" + os.environ.get("GITHUB_REPOSITORY", "workspace").split("/")[-1])).resolve()
STATE = Path.home() / ".local/state/coral"
STOP_REQUESTED = False


def path_for(value):
    path = (ROOT / value).resolve()
    protected = (".git", ".env", ".ssh", ".coral", ".hermes")
    parts = Path(value).parts + (path.relative_to(ROOT).parts if path.is_relative_to(ROOT) else ())
    if not path.is_relative_to(ROOT) or any(p in protected or (p.startswith(".env.") and p != ".env.example") or p.endswith((".pem", ".key", ".p12")) for p in parts):
        raise ValueError("Path is outside the designated workspace or is a protected secret.")
    return path


def task_path(task_id):
    if not re.fullmatch(r"[a-f0-9-]{36}", task_id):
        raise ValueError("Invalid task ID")
    return STATE / task_id


def cancel(task_id):
    directory = task_path(task_id)
    if (directory / "pid").exists():
        pid = int((directory / "pid").read_text())
        # Verify this is our worker before signaling its process group; protects against PID reuse.
        try:
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes()
            if b"runtime.py" in cmd and task_id.encode() in cmd:
                os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, FileNotFoundError):
            pass
    return {"cancelled": True}


def worker(request):
    directory = task_path(request["id"])
    deadline = request["deadline"]
    command = ["bash", "-c", request["prompt"]] if request["kind"] == "terminal" else [str(Path.home() / ".local/bin/hermes"), "chat", "--oneshot", "--query", request["prompt"]]
    with (directory / "output").open("wb", buffering=0) as output:
        try:
            process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError:
            (directory / "result").write_text(json.dumps({"status": "failed", "error": "Could not launch the command. Check the workspace path and Hermes installation."}))
            return
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        total = 0
        eof = False
        try:
            while process.poll() is None or not eof:
                if STOP_REQUESTED:
                    raise KeyboardInterrupt()
                if time.time() >= deadline:
                    raise TimeoutError("Task duration or daily allowance reached.")
                for key, _ in selector.select(timeout=0.1):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        eof = True
                        selector.unregister(key.fileobj)
                    else:
                        total += len(data)
                        if total > 512_000:
                            raise ValueError("Task output exceeded the 512 KB safety limit.")
                        output.write(data)
            result = {"status": "succeeded" if process.returncode == 0 else "failed", "error": "" if process.returncode == 0 else f"Command exited {process.returncode}"}
        except BaseException as error:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            result = {"status": "cancelled" if isinstance(error, KeyboardInterrupt) else "failed", "error": str(error)}
        finally:
            selector.close()
        (directory / "result").write_text(json.dumps(result))


def provider_request(request):
    coral_dir = Path(__file__).resolve().parent
    launcher = Path.home() / ".local/bin/hermes"
    bootstrap = (
        "import sys, runpy; sys.path.insert(0, sys.argv[1]); "
        "sys._hermes_pin_default_home = True; import hermes_bootstrap; "
        "runpy.run_path(sys.argv[2], run_name='__main__')"
    )
    try:
        with (STATE / "provider.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            command = subprocess.run([str(launcher), "--print-runtime-command"], capture_output=True, check=True, timeout=5)
            interpreter = json.loads(command.stdout)[0]
            result = subprocess.run([interpreter, "-I", "-c", bootstrap, str(coral_dir / "hermes-agent"),
                                     str(coral_dir / "providers.py")], input=json.dumps(request).encode(),
                                    capture_output=True, check=True, timeout=20)
            return json.loads(result.stdout)
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return {"error": "Could not open Hermes provider settings. Resume the Codespace to refresh its bridge."}


def dispatch(request):
    operation = request["operation"]
    if operation in ("provider_options", "set_provider"):
        return provider_request(request)
    if operation == "health":
        hermes = Path.home() / ".local/bin/hermes"
        return {"installed": hermes.is_file() and os.access(hermes, os.X_OK), "workspace": str(ROOT),
                "workspace_ready": ROOT.is_dir(), "enabled": not (STATE / "disabled").exists()}
    if operation == "hermes":
        if request["enabled"]:
            (STATE / "disabled").unlink(missing_ok=True)
        else:
            (STATE / "disabled").touch()
            for directory in STATE.iterdir():
                if directory.is_dir() and not (directory / "result").exists():
                    cancel(directory.name)
        return {"enabled": bool(request["enabled"])}
    if operation == "files":
        directory = path_for(request.get("path", ""))
        entries = []
        for item in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            try:
                path_for(str(item.relative_to(ROOT)))
            except ValueError:
                continue
            entries.append({"name": item.name, "path": str(item.relative_to(ROOT)), "directory": item.is_dir(), "size": item.stat().st_size})
        return {"files": entries[:1000]}
    if operation == "read":
        path = path_for(request["path"])
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("Editor supports UTF-8 files up to 1 MB.")
        return {"content": path.read_text(), "path": request["path"]}
    if operation == "write":
        path = path_for(request["path"])
        if len(request["content"].encode()) > 1024 * 1024:
            raise ValueError("File exceeds 1 MB.")
        path.parent.mkdir(parents=True, exist_ok=True)
        # O_NOFOLLOW protects the final component against symlink replacement.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
        with os.fdopen(fd, "w") as file:
            file.write(request["content"])
        return {"saved": True}
    if operation == "run":
        if request["kind"] == "hermes" and (STATE / "disabled").exists():
            raise ValueError("Start Hermes before sending a task.")
        directory = task_path(request["id"])
        directory.mkdir(exist_ok=True)
        with (directory / "lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not (directory / "pid").exists():
                encoded = base64.b64encode(json.dumps(request).encode()).decode()
                child = subprocess.Popen([sys.executable, __file__, "worker", request["id"], encoded], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                (directory / "pid").write_text(str(child.pid))
        return {"status": "running"}
    if operation == "poll":
        directory = task_path(request["id"])
        result = json.loads((directory / "result").read_text()) if (directory / "result").exists() else {"status": "running", "error": ""}
        output = directory / "output"
        if output.exists():
            with output.open("rb") as file:
                file.seek(max(0, output.stat().st_size - 512_000))
                result["output"] = file.read().decode(errors="replace")
        return result
    if operation == "cancel":
        return cancel(request["id"])
    raise ValueError("Unsupported operation")


if __name__ == "__main__":
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    def request_stop(*_):
        global STOP_REQUESTED
        STOP_REQUESTED = True
    signal.signal(signal.SIGTERM, request_stop)
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        worker(json.loads(base64.b64decode(sys.argv[3])))
    else:
        try:
            print(json.dumps(dispatch(json.loads(sys.stdin.read()))))
        except Exception as error:
            print(json.dumps({"error": str(error)}))
            sys.exit(1)
