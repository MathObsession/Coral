# Coral

Coral is a native Mac and iPhone workspace for a personal, cloud-hosted Hermes agent. It includes SwiftUI apps, an authenticated backend, a GitHub Pages dashboard, a persistent scheduler, Codespace lifecycle controls, files, command execution, and official GitHub Codespaces SSH support.

The supplied design assets are preserved. The apps and dashboard use the existing fox, cream surfaces, orange, green, and blue accents, rounded cards, and physical button bevels. Native typography uses the system rounded font as the offline fallback for Plus Jakarta Sans.

## What is included

| Component | Location | Runs where |
| --- | --- | --- |
| Shared SwiftUI source, macOS/iOS targets, native tests | `native/Coral.xcodeproj` | Xcode / Mac / iPhone |
| GitHub OAuth, encrypted tokens, sessions, allowance, scheduler | `backend/coral` | Always-on backend |
| Static web dashboard | `website/` | GitHub Pages |
| Private Hermes/file/command bridge | `codespace/runtime.py` | SSH into a Codespace |
| Hermes installer and SSH server configuration | `codespace/`, `.devcontainer/` | GitHub Codespaces |
| Deployment blueprint | `render.yaml` | Render Starter with persistent disk |
| Alternative backend and independent shutdown watchdog | `docs/coral*.service`, `docs/coral-watchdog.timer` | Linux/systemd |

**Deployment needs your GitHub OAuth credentials, a backend HTTPS address, a GitHub account with Codespaces billing enabled, and a Hermes model provider configured in the Codespace.** These are not embedded in the clients. This repository has not been deployed or connected to a live GitHub account in the development session. See [verification notes](docs/VERIFICATION.md) for the checks that actually ran.

## Run locally

Requires Python 3.12+, Node 22+ for web checks, GitHub CLI for a real Codespace, and Xcode for native apps.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
bash scripts/run-local.sh
```

In another terminal:

```bash
python3 -m http.server 8080 --bind 127.0.0.1 --directory website
```

Open `http://127.0.0.1:8080`. In Settings, select **Open local workspace**. In Profiles, enter `local/workspace` and connect. The local backend uses `.coral/workspace` and enforces the same session rules. You can create a file, save it, and execute `cat filename`. Local mode performs real operations; it does not synthesize Hermes responses. AI tasks return a configuration error until you use a real Codespace.

For the native app, open `native/Coral.xcodeproj` in Xcode. Select **Coral-macOS → My Mac** or **Coral-iOS → an iPhone simulator**, then Run. Use Settings → Open local workspace. On a physical iPhone, configure your deployed HTTPS backend; its `localhost` refers to the phone.

Local sign-in is only available with `CORAL_DEMO=1` and a loopback client. Never deploy local mode. The local script stores its encryption key in the ignored `.coral/local-key` so restarts retain decryptable credentials.

## Deploy the backend

1. Create your GitHub repository and push Coral. GitHub operations use `gh`:

   ```bash
   gh auth login --hostname github.com
   git init
   git add .
   git commit -m "Build Coral AI workspace"
   gh repo create Coral --private --source=. --remote=origin --push
   ```

   Choose public visibility if your Pages plan requires it. Keep `.env`, `.coral`, signing files, and build output out of Git. GitHub Pages publishing from a private repository depends on your GitHub plan.

2. In Render, create a Blueprint from this repository using `render.yaml`. Keep the **Starter** always-on plan, one instance, and its persistent `/data` disk. A service that sleeps cannot execute the scheduler while your apps are closed. The Docker build context is the repository root.

3. Register a GitHub OAuth App in **GitHub → Settings → Developer settings → OAuth Apps**. Set the authorization callback URL to:

   ```text
   https://YOUR_BACKEND/auth/callback
   ```

4. Set the backend environment values from `.env.example`:

   ```text
   GITHUB_CLIENT_ID=your-oauth-app-id
   GITHUB_CLIENT_SECRET=your-oauth-app-secret
   CORAL_ENCRYPTION_KEY=your-generated-fernet-key
   CORAL_PUBLIC_URL=https://YOUR_BACKEND
   CORAL_WEB_URL=https://YOUR_ACCOUNT.github.io/Coral
   CORAL_DATABASE=/data/coral.sqlite
   CORAL_DEMO=0
   ```

   Generate the encryption key once, preserve it in your secret manager, and back it up with the database:

   ```bash
   python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
   ```

   Rotating this key without re-encrypting stored tokens makes existing profile credentials unusable; reconnect the profiles if you intentionally replace it.

5. The default OAuth scope is `codespace`, for Codespace management. For private repositories, opt into `GITHUB_OAUTH_SCOPES=codespace,repo` and sign in again. OAuth `repo` is broad; use it only when private repository access is needed. GitHub identity comes from `/user`, without requiring email access.

6. Verify `https://YOUR_BACKEND/health`. The response should report `production`. Configure both apps and the dashboard with this backend address.

The backend must use one Uvicorn worker. A database lock prevents two scheduler processes from running against one database. SQLite WAL storage retains tasks, schedule occurrences, results, and usage through restarts. Use provider disk snapshots/SQLite online backups for disaster recovery; do not copy an active SQLite file without its WAL.

### Independent watchdog option

On an always-on Linux host, install the project at `/opt/coral`, create a `coral` service account, install Python dependencies and `gh`, and put the backend environment in `/etc/coral.env` (readable only by root and that service account). Run Uvicorn behind an HTTPS reverse proxy. Install the systemd units in `docs/` and enable `coral.service` and `coral-watchdog.timer`.

The watchdog is a separate, stop-only process. If the main worker heartbeat is stale for 90 seconds, it retries Codespace shutdown using the stored, encrypted account credentials. It does not execute or replay scheduled tasks. It shares the persistent backend database. Render's blueprint restarts the service and uses GitHub's 10-minute idle timeout as its fallback; the separate systemd watchdog is available for deployments requiring independent process supervision.

## Publish GitHub Pages

Set `website/config.js` to your public backend URL. This file contains only a public address. In the repository settings choose **Pages → Source → GitHub Actions**. Enable it with GitHub CLI if needed:

```bash
gh api --method POST repos/YOUR_ACCOUNT/Coral/pages --input - <<'JSON'
{"build_type":"workflow"}
JSON
```

If Pages already exists, inspect it with `gh api repos/YOUR_ACCOUNT/Coral/pages` and update its configuration instead of creating it again. The `.github/workflows/pages.yml` workflow publishes `website/` on main changes. The website contains no server code or scheduler. A Content Security Policy, escaping, and session-scoped bearer storage protect the dashboard; privileged GitHub credentials stay on the backend.

## Configure the native apps

Open `native/Coral.xcodeproj` in Xcode. The project has two shared schemes:

- **Coral-macOS**: Mac app; select My Mac. Embedded SSH console plus Terminal/iTerm launch.
- **Coral-iOS**: iPhone/iPad app; select an iPhone simulator or your physical device. Session controls, Hermes, schedules, and More → Files/Terminal/Usage/Profiles/Settings.

For an archive, set your Apple development team and a unique bundle identifier in Signing & Capabilities. Simulator builds do not require a paid signing account. A physical iPhone requires your Apple signing setup. Mac distribution requires signing/notarization appropriate to your distribution channel; the Mac app uses local process access for official SSH and is not App Store sandboxed.

Configure the backend in the app's Settings, or create an ignored `native/Config.local.xcconfig`:

```xcconfig
CORAL_BACKEND_URL = https:/$()/YOUR_BACKEND
```

The `$()` keeps Xcode from interpreting `//` as a comment. Coral stores its own session bearer in Keychain, on this device only. GitHub tokens and private keys are not returned to the app. Sign-in uses an ephemeral system authentication session, OAuth state, a verifier-bound single-use callback code, and a backend exchange.

## Connect Hermes and your Codespace

1. Sign into Coral with the GitHub account that should pay for your Codespace.
2. Open Profiles and enter `owner/repository`. Leave the Codespace name empty to create one, or enter an existing owned Codespace name. Coral rejects a different repository or a known billable owner that does not match the profile account.
3. Coral starts or resumes the Codespace, installs its private bridge, and installs Hermes from the official repository. GitHub automatically clones the selected repository. Use Coral's `.devcontainer/devcontainer.json` together with the `codespace/` scripts in that repository, or ensure its existing devcontainer installs an SSH server. The included configuration forwards no public bridge ports. The bridge defaults to `/workspaces/REPOSITORY_NAME`; a custom devcontainer workspace should set `CORAL_WORKSPACE` to its designated repository folder.
4. Configure Hermes's model provider in the Codespace using the official setup flow:

   ```bash
   gh codespace ssh --codespace YOUR_CODESPACE
   ~/.local/bin/hermes setup
   ~/.local/bin/hermes chat --help
   ```

   Provider credentials belong in Hermes's own configuration or GitHub Codespaces secrets, never Coral client source. Model-provider inference charges are separate from Codespaces compute and Coral's four-hour allowance.
5. Send an initial task. Coral uses Hermes's noninteractive `hermes chat -q` entry point; check the upstream CLI help before live use. Installation fails explicitly if that entry point has changed. See [Hermes integration notes](docs/HERMES.md).

The installer defaults to `origin/main`; set `HERMES_REF` to a reviewed tag/commit in your Codespace for reproducibility. It records the installed commit and CLI help in `~/.local/share/coral/hermes-agent/`. The backend provisions the bridge over official `gh codespace ssh`; a repository other than Coral does not need to include the backend or native project.

Hermes Start/Stop controls enable or disable accepting new agent tasks. Stopping Hermes cancels its current task; it does not delete workspace files or turn off the Codespace. Stop workspace shuts down the Codespace. Tasks are discrete CLI invocations, and each task's prompt/output is retained in Coral's history; separate CLI invocations do not automatically share an upstream Hermes conversation thread. Include the relevant context in subsequent prompts.

## SSH

Coral's SSH authentication is deliberately separate from its backend API connection. On your Mac:

```bash
gh auth login --hostname github.com
gh auth switch --hostname github.com --user YOUR_PROFILE_ACCOUNT
gh codespace ssh --codespace YOUR_CODESPACE
```

The embedded Mac SSH console runs a real PTY through `script` and the official GitHub CLI, with input and Ctrl+C support. It presents readable command output; use **Open in Terminal/iTerm** for full-screen programs such as Vim and tmux. Switching SSH profiles selects the corresponding locally authenticated GitHub CLI account. You must have that account signed in locally. Coral does not install or retrieve private SSH keys itself.

For standard OpenSSH tooling:

```bash
gh codespace ssh --codespace YOUR_CODESPACE --config > ~/.ssh/coral-codespaces
```

Add `Include ~/.ssh/coral-codespaces` to your SSH config, then use the generated host alias. Protect that file normally; no private keys are exported by Coral. The official GitHub workflow may create or choose a key in your own local `~/.ssh` directory.

On iPhone, the native command interface uses the authenticated backend to run commands in your Codespace. Official `gh codespace ssh` remains available from a computer; Coral does not embed a separate iOS SSH key manager. Standard external SSH activity does not reset Coral's server-side inactivity timer. Enable a finite extension before a long standalone SSH session; the daily allowance still applies.

## Sessions, scheduling, and limits

- The account receives **14,400 seconds per UTC day**, shared across its linked profiles. Only one profile has a live session at once. Profile-specific daily history is also retained.
- VM startup, provisioning, interactive work, extended mode, and scheduled work all consume allowance. Usage continues until GitHub confirms shutdown, including retries.
- Normal mode stops after **600 seconds without meaningful interaction**. Read-only polling, status checks, and automatic refresh never reset `last_activity`. Clients throttle deliberate typing/navigation events to avoid flooding the server.
- Extensions last **15–120 minutes** in the apps and expire at the earlier of their requested expiration or the current session's allowance deadline. Coral temporarily adjusts GitHub's native idle timeout to avoid an early shutdown, then restores ten minutes on normal mode or extension expiration. Organization timeout policies may restrict that update; Coral reports the error. Returning to normal mode gives a new inactivity interval.
- Coral reserves 30 seconds for shutdown before allowance exhaustion, refuses new starts/tasks near exhaustion, and imposes a local deadline on every remote task. Actual GitHub billing cannot be guaranteed during a GitHub API outage or failure of all supervisory services; failed stops retain usage accounting and retry instead of falsely reporting the Codespace as stopped.
- One-time, daily, weekly, and interval tasks are persistent database schedules executed by the always-on external backend. Daily/weekly repeats use UTC intervals; the date picker displays local time. Missed recurring runs coalesce into one occurrence rather than replaying a backlog.
- Scheduled tasks wait while an interactive session is active. Once free: allowance check → start/resume → execute → save result and notification → immediate shutdown on the next control-plane tick (normally within five seconds). Duration limits include startup. No available allowance produces a recorded skipped execution.
- `(schedule_id, occurrence)` is unique; an active-task index, active-session index, and request idempotency keys prevent duplicate work.
- Cancellation kills the remote process group. CLI progress is captured as it is emitted and exposed through polling and authenticated SSE. Upstream output buffering can delay intermediate progress; the final result is persisted.
- Restart recovery records interrupted executions as failures and stops remaining sessions. It never automatically replays a possibly completed command.
- Results are delivered to a **durable backend inbox** and shown in Home and task history on your next visit. Native local notifications can be enabled and appear when the app receives results while running or on reopening. APNs push while the iPhone app is terminated, email, and SMS are not configured.
- Stopping a Codespace preserves its filesystem. GitHub's retention period still applies; commit/push important work and configure retention before leaving it stopped for long periods. Coral never uses `gh codespace delete` as a stop operation.

## Files and command permissions

File endpoints are authenticated and authorized against the profile. They resolve paths within the designated repository, reject traversal and symlink escapes, hide protected directories and known secret file patterns, and limit editor operations to UTF-8 files up to 1 MB. The editor saves to the Codespace. Mac drafts survive navigation within the app; phone sheets protect unsaved edits.

Terminal commands and Hermes tools execute as the Codespace's authenticated owner. They are intentionally capable of changing that user's workspace and invoking shell tools. They are not a sandbox for untrusted prompts or third-party users. The backend never exposes a public command endpoint without authentication and does not accept an arbitrary remote hostname. The bridge uses JSON stdin through a fixed SSH command, not user input interpolated into shell arguments.

## Checks

```bash
python3 -m pytest backend/tests -q
node --test website/tests/*.test.cjs
bash scripts/test.sh
# On a machine with an available iPhone simulator:
xcrun simctl list devices available
bash scripts/test-simulator.sh SIMULATOR_UUID
```

Xcode MCP can also select the shared schemes, run the Mac app on **My Mac**, run the iPhone app on an eligible iOS simulator, and run the native tests. Use Xcode's device/runtime tools; there is no macOS simulator for a native Mac app.

See [architecture and API details](docs/ARCHITECTURE.md), [verification results](docs/VERIFICATION.md), and [the first live-session checklist](docs/LIVE_ACCEPTANCE.md).

Development builds from the verified Xcode run are available locally at `build/deliverables/Coral-macOS.app` and `build/deliverables/Coral-iOS-Simulator.app`. The iPhone bundle targets Simulator; use Xcode and your signing team for installation on a physical iPhone. Real simulator screenshots are saved in `build/screenshots/`.
