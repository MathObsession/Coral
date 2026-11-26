import asyncio
import base64
import json
import os
import re
import shlex
from pathlib import Path


class GitHubError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class GitHub:
    def __init__(self, security, public_url=""):
        self.security = security
        self.public_url = public_url.rstrip("/")

    async def gh(self, profile, *args, stdin=None, timeout=90):
        env = {key: os.environ[key] for key in ("HOME", "PATH", "LANG", "TERM") if key in os.environ}
        env["GH_TOKEN"] = self.security.open(profile["token"])
        env["GH_PROMPT_DISABLED"] = "1"
        process = await asyncio.create_subprocess_exec("gh", *args, env=env, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(process.communicate(stdin), timeout)
        except (asyncio.CancelledError, TimeoutError) as error:
            if process.returncode is None:
                process.kill()
                await process.wait()
            if isinstance(error, asyncio.CancelledError):
                raise
            raise GitHubError("GitHub did not respond in time. Try the operation again.") from None
        if process.returncode:
            # GitHub may echo a token in errors; never retain raw stderr.
            match = re.search(rb"\bHTTP (\d{3})\b", err)
            status = int(match[1]) if match else None
            if status in (401, 403):
                raise GitHubError("GitHub denied the operation. Reconnect GitHub and check Codespaces access and billing for this repository.", status)
            if status == 404:
                raise GitHubError("GitHub could not find this repository or Codespace for the connected account.", status)
            error = f" (HTTP {status})" if status else ""
            raise GitHubError(f"GitHub could not complete the Codespace operation{error}. Check its state and your account's Codespaces allowance.", status)
        return out.decode()

    async def api(self, profile, endpoint, method="GET", body=None):
        args = ["api", endpoint, "--method", method, "-H", "Accept: application/vnd.github+json", "-H", "X-GitHub-Api-Version: 2022-11-28"]
        if body is not None:
            args += ["--input", "-"]
        output = await self.gh(profile, *args, stdin=json.dumps(body).encode() if body is not None else None)
        return json.loads(output) if output.strip() else {}

    async def inspect(self, profile):
        if not re.fullmatch(r"[A-Za-z0-9-]+", profile["codespace"]):
            raise GitHubError("Invalid Codespace name")
        return await self.api(profile, f'user/codespaces/{profile["codespace"]}')

    async def bind(self, profile, repository, codespace="", reference=""):
        if codespace:
            result = await self.inspect({**profile, "codespace": codespace})
        else:
            repo = await self.api(profile, f"repos/{repository}")
            label = "coral-" + profile["id"] + ("-ws" if reference else "")
            def matches(space):
                return (space.get("display_name") == label and
                        space.get("repository", {}).get("full_name", "").lower() == repository.lower())

            existing = await self.api(profile, "user/codespaces?per_page=100")
            prior = [s for s in existing.get("codespaces", []) if matches(s)]
            if prior:
                result = prior[0]
            else:
                if repo.get("size") == 0:
                    # Tiny repositories can also report size zero. Check for a commit before rejecting.
                    try:
                        commits = await self.api(profile, f"repos/{repository}/commits?per_page=1")
                    except GitHubError as error:
                        if error.status != 409:
                            raise
                        commits = []
                    if not commits:
                        raise GitHubError("This GitHub repository has no commits. Add a README or another file on GitHub, then connect it again.", 409)
                try:
                    result = await self.api(profile, "user/codespaces", "POST", {
                        "repository_id": repo["id"], "ref": reference or repo["default_branch"],
                        "display_name": label, "idle_timeout_minutes": 10, "retention_period_minutes": 43200,
                    })
                except BaseException:
                    # Recover an ambiguous POST response before allowing another create.
                    try:
                        listing = await self.api(profile, "user/codespaces?per_page=100")
                        for space in listing.get("codespaces", []):
                            if matches(space):
                                await self.stop({**profile, "codespace": space["name"]})
                    finally:
                        raise
        name = result["name"]
        owner = result.get("owner", {}).get("id")
        billing = result.get("billable_owner", result.get("billing_owner", {}))
        if owner != profile["github_id"] or (billing and billing.get("id") != profile["github_id"]):
            if not codespace:
                await self.stop({**profile, "codespace": name})
            raise GitHubError("Codespace must be owned and billed to this profile's GitHub account. Check organization billing policy.")
        connected_repository = result["repository"]["full_name"]
        if repository and connected_repository.lower() != repository.lower():
            raise GitHubError("The Codespace repository does not match your selection.")
        return name, connected_repository

    async def start(self, profile):
        await self.api(profile, f'user/codespaces/{profile["codespace"]}/start', "POST")

    async def idle_timeout(self, profile, minutes):
        await self.api(profile, f'user/codespaces/{profile["codespace"]}', "PATCH", {"idle_timeout_minutes": minutes})

    async def stop(self, profile):
        await self.gh(profile, "codespace", "stop", "--codespace", profile["codespace"], timeout=30)

    async def provision(self, profile):
        root = Path(__file__).resolve().parents[2]
        commands = ["umask 077; mkdir -p ~/.local/share/coral", "cd ~/.local/share/coral"]
        for filename in ("runtime.py", "install.sh", "providers.py", "agent_tools.py", "agent_tools.yaml"):
            encoded = base64.b64encode((root / "codespace" / filename).read_bytes()).decode()
            commands.append(f"printf '%s' {shlex.quote(encoded)} | base64 -d > {filename}")
        commands.append("bash install.sh > hermes-install.log 2>&1")
        try:
            await self.gh(profile, "codespace", "ssh", "--codespace", profile["codespace"], "--", "-T", " && ".join(commands), timeout=420)
        except GitHubError as error:
            raise GitHubError("Coral could not prepare Hermes over SSH. Check ~/.local/share/coral/hermes-install.log in the Codespace.", error.status) from None
        result = await self.remote(profile, {"operation": "health"})
        if not result.get("installed"):
            raise GitHubError("Hermes installation was not successful. Inspect the Codespace through SSH.")
        if not result.get("workspace_ready"):
            raise GitHubError("The repository folder is missing in the Codespace. Check its CORAL_WORKSPACE setting.")

    async def remote(self, profile, request):
        # Fixed command; user input is JSON on stdin and never interpolated into SSH arguments.
        repository = profile.get("repository", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise GitHubError("A valid designated repository is required for workspace access.")
        folder = "/workspaces/" + repository.split("/")[-1]
        command = 'CORAL_WORKSPACE="${CORAL_WORKSPACE:-' + folder + '}" python3 ~/.local/share/coral/runtime.py'
        if self.public_url and request["operation"] == "run" and request["kind"] == "hermes":
            request = {**request, "agent_url": self.public_url, "agent_token": self.security.issue_agent_token(request["id"])}
        output = await self.gh(profile, "codespace", "ssh", "--codespace", profile["codespace"], "--", "-T", command, stdin=json.dumps(request).encode(), timeout=30)
        try:
            return json.loads(output)
        except ValueError:
            raise GitHubError("Invalid response from the Codespace bridge.")


class LocalGitHub:
    """Explicit development adapter: real local file/command execution, no simulated AI output."""
    def __init__(self, workspace):
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.states = {}
        self.processes = {}

    async def bind(self, profile, repository, codespace="", reference=""):
        name = codespace or "local-" + profile["id"]
        self.states[name] = "Shutdown"
        return name, repository or "local/workspace"

    async def inspect(self, profile):
        return {"state": self.states.get(profile["codespace"], "Shutdown")}

    async def start(self, profile):
        self.states[profile["codespace"]] = "Available"

    async def idle_timeout(self, profile, minutes):
        pass

    async def stop(self, profile):
        self.states[profile["codespace"]] = "Shutdown"
        for task_id in list(self.processes):
            await self.remote(profile, {"operation": "cancel", "id": task_id})

    async def provision(self, profile):
        pass

    async def remote(self, profile, request):
        import importlib.util
        spec = importlib.util.spec_from_file_location("runtime", Path(__file__).resolve().parents[2] / "codespace/runtime.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.ROOT = self.workspace
        operation = request["operation"]
        if operation == "run":
            if request["kind"] == "hermes":
                return {"status": "failed", "error": "Local mode has no Hermes model. Use a configured Codespace for AI tasks.", "output": ""}
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(self.workspace), "TERM": "xterm-256color"}
            process = await asyncio.create_subprocess_exec("bash", "-c", request["prompt"], cwd=self.workspace, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, start_new_session=True)
            self.processes[request["id"]] = (process, asyncio.create_task(process.communicate()))
            return {"status": "running"}
        if operation == "poll":
            process, output = self.processes[request["id"]]
            if not output.done():
                return {"status": "running", "output": ""}
            return {"status": "succeeded" if process.returncode == 0 else "failed", "output": output.result()[0].decode(errors="replace"), "error": ""}
        if operation == "cancel":
            if request["id"] in self.processes:
                process, output = self.processes[request["id"]]
                if process.returncode is None:
                    import signal
                    os.killpg(process.pid, signal.SIGKILL)
                    await output
            return {"cancelled": True}
        if operation == "health":
            return {"installed": False, "workspace": str(self.workspace)}
        if operation == "hermes":
            return {"enabled": request["enabled"]}
        return module.dispatch(request)
