import re
import secrets
from html import escape
from pathlib import Path
from string import Template
from urllib.parse import parse_qsl

from cryptography.fernet import InvalidToken
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .security import digest


COOKIE = "coral_admin"
SESSION_SECONDS = 900
PAGE_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
}

LOGIN_FORM = """
<p>Sign in to configure GitHub OAuth for this Coral backend.</p>
<form method="post" action="/admin/login">
  <label for="password">Admin password</label>
  <input id="password" name="password" type="password" autocomplete="current-password" required>
  <button type="submit">Sign in</button>
</form>
"""

SETTINGS_FORM = """
<p>{status}</p>
<div class="setup">
  <p><a href="https://github.com/settings/applications/new">Register a GitHub OAuth app</a> with these URLs.</p>
  <dl>
    <dt>Homepage URL</dt>
    <dd><code>{homepage}</code></dd>
    <dt>Authorization callback URL</dt>
    <dd><code>{callback}</code></dd>
  </dl>
</div>
<form method="post" action="/admin" autocomplete="off">
  <input type="hidden" name="csrf" value="{csrf}">
  <label for="client-id">GitHub Client ID</label>
  <input id="client-id" name="client_id" autocapitalize="none" spellcheck="false" maxlength="255" required>
  <label for="client-secret">GitHub Client Secret</label>
  <input id="client-secret" name="client_secret" type="password" autocomplete="off" maxlength="255" required>
  <button type="submit">Save credentials</button>
</form>
<form method="post" action="/admin" class="sign-out">
  <input type="hidden" name="csrf" value="{csrf}">
  <button type="submit" name="action" value="logout">Sign out</button>
</form>
"""


async def read_form(request):
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    body = await request.body()
    if content_type != "application/x-www-form-urlencoded" or len(body) > 8192:
        raise HTTPException(400, "Submit the Coral admin form.")
    try:
        return dict(parse_qsl(body.decode(), max_num_fields=8, errors="strict"))
    except ValueError:
        raise HTTPException(400, "Invalid admin form.") from None


def install_admin(app, config, security):
    if not config.admin_password:
        return

    template = Template(Path(__file__).with_name("admin.html").read_text(encoding="utf-8"))
    session_prefix = "coral-admin:" + digest(config.admin_password) + ":"

    def get_csrf(request):
        try:
            session = security.open(request.cookies.get(COOKIE, ""), ttl=SESSION_SECONDS)
        except InvalidToken:
            return ""
        return session.removeprefix(session_prefix) if session.startswith(session_prefix) else ""

    def page(heading, content, *, message="", code=200):
        role = "alert" if code >= 400 else "status"
        notice = f'<p class="notice" role="{role}">{escape(message)}</p>' if message else ""
        return HTMLResponse(template.substitute(heading=heading, notice=notice, content=content), code, headers=PAGE_HEADERS)

    def settings(csrf, **feedback):
        try:
            configured = security.github_oauth_credentials() is not None
            status = (
                "GitHub OAuth credentials are configured. Saving replaces the pair."
                if configured else "Add your GitHub OAuth credentials to enable sign-in."
            )
        except InvalidToken:
            status = "Coral could not decrypt the saved credentials. Enter both values again."
        content = SETTINGS_FORM.format(status=status, homepage=escape(config.web_url),
                                       callback=escape(config.oauth_callback_url), csrf=escape(csrf))
        return page("GitHub OAuth", content, **feedback)

    @app.get("/admin", include_in_schema=False)
    async def admin(request: Request):
        csrf = get_csrf(request)
        if not csrf:
            return page("Coral admin", LOGIN_FORM)
        message = "Credentials saved. Test them by signing in with GitHub from Coral." if request.query_params.get("saved") == "1" else ""
        return settings(csrf, message=message)

    @app.post("/admin/login", include_in_schema=False)
    async def login(request: Request):
        fields = await read_form(request)
        if not secrets.compare_digest(fields.get("password", "").encode(), config.admin_password.encode()):
            return page("Coral admin", LOGIN_FORM, message="Incorrect admin password.", code=401)
        response = RedirectResponse("/admin", 303)
        response.set_cookie(COOKIE, security.seal(session_prefix + secrets.token_urlsafe(32)),
                            max_age=SESSION_SECONDS, path="/admin", secure=True, httponly=True, samesite="strict")
        return response

    @app.post("/admin", include_in_schema=False)
    async def update_admin(request: Request):
        csrf = get_csrf(request)
        if not csrf:
            return page("Coral admin", LOGIN_FORM, message="Sign in to manage credentials.", code=401)
        fields = await read_form(request)
        if not secrets.compare_digest(fields.get("csrf", "").encode(), csrf.encode()):
            raise HTTPException(403, "Reload the admin page and try again.")
        if fields.get("action") == "logout":
            response = RedirectResponse("/admin", 303)
            response.delete_cookie(COOKIE, path="/admin", secure=True, httponly=True, samesite="strict")
            return response

        client_id, client_secret = fields.get("client_id", "").strip(), fields.get("client_secret", "").strip()
        if not all(re.fullmatch(r"[A-Za-z0-9_-]{1,255}", value) for value in (client_id, client_secret)):
            return settings(csrf, message="Enter a valid GitHub Client ID and Client Secret.", code=400)
        security.save_github_oauth_credentials(client_id, client_secret)
        return RedirectResponse("/admin?saved=1", 303)
