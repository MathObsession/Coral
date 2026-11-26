# Deploy Coral using a Render Free Web Service

Use **New → Web Service**, with **Docker** and the **Free** instance type. You do not need to create a Blueprint. `render.free.yaml` records the equivalent settings; the original `render.yaml` remains the optional paid persistent-disk deployment.

The free deployment uses the following components:

| Service | Role |
| --- | --- |
| Render Free Web Service | Python backend, GitHub OAuth, `gh`, Codespace controls, task workers |
| External free PostgreSQL, such as Supabase | Persistent accounts, encrypted OAuth credentials and tokens, usage, schedules, and results |
| Supabase Cron or cron-job.org | Authenticated scheduling and shutdown check every minute, independently of your apps |

GitHub Pages continues to host the static dashboard. Your Mac can be off. Each provider's free quotas and availability still apply. GitHub Codespaces compute and Hermes inference have their own billing.

## 1. Create the persistent database

Create a Free project at https://supabase.com/. Create a database password and keep it in your secret manager. In **Connect**, choose a **Session pooler** PostgreSQL connection string that supports IPv4 (usually port 5432). This avoids direct-database IPv6 compatibility problems with the backend host.

Copy the URI in this form, with your actual password substituted and URL-encoded when necessary:

```text
postgresql://USER:PASSWORD@POOLER_HOST:5432/postgres?sslmode=require
```

This is a private server credential, not the Supabase public/anon API key. Enter it only in Render's environment settings as `CORAL_DATABASE_URL`. Coral connects with TLS and creates its tables automatically in a private `coral` schema with row-level security enabled. Keep that schema out of Supabase's exposed API schemas; use the backend database-owner role from the Session pooler connection string. Use a dedicated project/database for Coral. Free projects may be paused under the provider's inactivity policy; follow its current dashboard/documentation when resuming a paused project.

To initialize and verify the database before deploying Render, run:

```bash
python3 scripts/bootstrap_supabase.py --save-env
```

Paste the Session pooler URI at the hidden prompt. The script creates Coral's schema, checks real transactional storage and timestamp precision, and saves the verified URI in the ignored `.coral/render-database.env` file with permissions `600`. It never prints the password or connection URI. It initializes an existing hosted project; it does not create or upgrade a Supabase organization/project.

An existing PostgreSQL provider can be used instead. If choosing Neon, check its current free compute allowance before keeping a frequently polled backend database active around the clock.

## 2. Create the Render Web Service

On https://render.com/ choose **New → Web Service**, connect GitHub, and select `MathObsession/Coral`.

| Setting | Value |
| --- | --- |
| Name | `coral-api` or another available name |
| Branch | `main` |
| Root Directory | Leave empty |
| Runtime/Language | Docker |
| Dockerfile Path | `backend/Dockerfile` |
| Docker Build Context | Repository root (`.`), if shown |
| Instance Type | Free |
| Health Check Path | `/health` |

The Dockerfile supplies the command and listens on port 8000. Do not add a disk. Use one instance and one Uvicorn worker. Render passes the assigned HTTPS URL to Coral at startup as `RENDER_EXTERNAL_URL`.

## 3. Set the backend environment

In **Render → Service → Environment**, set:

```env
CORAL_ADMIN_PASSWORD=YOUR_RANDOM_ADMIN_PASSWORD
CORAL_ENCRYPTION_KEY=YOUR_FERNET_KEY
CORAL_DATABASE_URL=YOUR_PRIVATE_POSTGRESQL_CONNECTION_URI
CORAL_SCHEDULER_TOKEN=YOUR_RANDOM_SCHEDULER_SECRET
CORAL_WEB_URL=https://mathobsession.github.io/Coral
CORAL_DATABASE=/tmp/coral/control-plane.sqlite
CORAL_HOSTING_MODE=render-free
CORAL_DEMO=0
GITHUB_OAUTH_SCOPES=codespace
```

`CORAL_DATABASE` supplies a local worker-lock path in this mode. Application data lives in the external PostgreSQL database, not in this local path. Free mode deliberately refuses to start without external storage and a scheduler secret, preventing accidental loss/reset of usage or authentication after a restart.

Set `CORAL_PUBLIC_URL` only if you want Coral to use a custom HTTPS domain for OAuth callbacks.

Generate an encryption key and two separate secrets locally.

```bash
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Use the values in order for `CORAL_ENCRYPTION_KEY`, `CORAL_SCHEDULER_TOKEN`, and `CORAL_ADMIN_PASSWORD`. Preserve the encryption key across redeployments. Save the environment and deploy.

Once Render displays the service URL, open `/admin` on that address and enter the password from Render. The panel shows the URLs to use when creating or updating your app in **GitHub → Settings → Developer settings → OAuth Apps**.

```text
Homepage URL = https://mathobsession.github.io/Coral
Authorization callback URL = https://YOUR_RENDER_SERVICE.onrender.com/auth/callback
```

Generate a client secret in GitHub, paste the Client ID and Client Secret into the panel, and select **Save credentials**. Coral encrypts both values in Supabase. The next GitHub sign-in uses the saved pair without a Render redeploy. For private repositories, use `GITHUB_OAUTH_SCOPES=codespace,repo` and authenticate again.

## 4. Configure the external scheduler

The Coral deployment uses Supabase Cron with `pg_net` for the one-minute check. The job reads its URL and token from Supabase Vault and sends the request described below.

For a deployment using cron-job.org, create a free account and add a cron job with the following settings.

| Setting | Value |
| --- | --- |
| URL | `https://YOUR_RENDER_SERVICE.onrender.com/internal/tick` |
| Method | POST |
| Interval | Every minute |
| Request header | `X-Coral-Scheduler-Token: YOUR_RANDOM_SCHEDULER_SECRET` |
| Notifications | Enable failure notifications |

The endpoint verifies the private scheduler token, then wakes Coral's scheduler/supervision loop. It does not record user interaction, reset inactivity, or extend a Codespace session. SQL occurrence constraints still prevent duplicate execution. Keep the scheduler token in the cron service's private header settings.

These requests perform scheduling and shutdown supervision while the apps are closed. They also allow an external request to reach the backend after a Render sleep/restart. A free service can have cold-start delays; initial cron requests can time out during startup. Review execution logs and ensure the external job remains enabled. Do not depend on exact-to-the-second dispatch on a free cold-start host.

## 5. Verify and connect

Open:

```text
https://YOUR_RENDER_SERVICE.onrender.com/health
```

The response should include:

```json
{"status":"ok","name":"Coral","mode":"production","storage":"postgresql","hosting":"render-free"}
```

Verify the cron job gets HTTP 200 with `{"accepted":true}`. Requests without the correct header must get HTTP 401.

In the Pages dashboard and both native apps, save the Render URL as the backend address and authenticate with GitHub. Connect your repository/Codespace and configure Hermes's model provider through SSH.

Test a one-time scheduled task while both apps are closed and the Mac is off. Confirm the persisted result, shared daily usage, and Codespace shutdown. Redeploy the backend and confirm profiles, usage, and schedules remain present. Restart recovery intentionally fails uncertain in-flight executions and stops their Codespaces; it never blindly replays a command.

If you are switching from SQLite, plan a separate data migration to carry accounts, schedules, and usage into PostgreSQL. Stop active sessions before switching deployments.

## Verification limits

Local tests cover encrypted OAuth storage, credential rotation, the sign-in flow with mocked GitHub responses, and the PostgreSQL schema and scheduler trigger. A separate opt-in storage integration test runs against `CORAL_TEST_DATABASE_URL`. To verify the live setup, sign in through your registered GitHub OAuth app and check your external scheduler's delivery history.
