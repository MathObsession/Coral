import re
import time
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from coral.app import create_app
from coral.config import Config
from coral.security import challenge


BACKEND = "https://coral.example.com"
DASHBOARD = "https://example.github.io/Coral"
VERIFIER = "v" * 43


@pytest.fixture
def config(tmp_path):
    return Config(database=str(tmp_path / "coral.sqlite"), database_url="", demo=False, hosting_mode="standard",
                  admin_password="test-admin-password+&🔑", encryption_key=Fernet.generate_key().decode(),
                  client_id="", client_secret="", public_url=BACKEND + "/", web_url=DASHBOARD)


def open_client(config):
    return TestClient(create_app(config, worker=False), base_url=BACKEND)


def sign_in(client, config):
    response = client.post("/admin/login", data={"password": config.admin_password}, follow_redirects=False)
    assert response.status_code == 303
    return response


def form_csrf(client):
    page = client.get("/admin")
    return re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)


def prepare(client, kind="web"):
    response = client.post("/auth/prepare", json={"client": kind, "challenge": challenge(VERIFIER)})
    assert response.status_code == 200
    return parse_qs(urlsplit(response.json()["url"]).query)


def test_admin_protects_credentials_and_uses_secure_sessions(config):
    with open_client(config) as client:
        response = client.get("/admin")
        assert "Admin password" in response.text
        assert "Client Secret" not in response.text
        assert response.headers["Cache-Control"] == "no-store"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        assert client.post("/auth/prepare", json={"challenge": challenge(VERIFIER)}).status_code == 503

        credentials = {"client_id": "stored-id", "client_secret": "stored-secret"}
        assert client.post("/admin", data=credentials).status_code == 401
        rejected = client.post("/admin/login", data={"password": "wrong"})
        assert rejected.status_code == 401
        assert "set-cookie" not in rejected.headers

        cookie = sign_in(client, config).headers["set-cookie"]
        assert all(flag in cookie for flag in ("HttpOnly", "Secure", "SameSite=strict", "Max-Age=900", "Path=/admin"))
        page = client.get("/admin")
        assert BACKEND + "/auth/callback" in page.text
        assert DASHBOARD in page.text
        assert client.post("/admin", data=credentials).status_code == 403

        csrf = form_csrf(client)
        assert client.post("/admin", data={"csrf": csrf, **credentials, "client_secret": ""}).status_code == 400
        assert client.app.state.db.one("SELECT * FROM github_oauth_credentials") is None
        saved = client.post("/admin", data={"csrf": csrf, **credentials})
        assert "Credentials saved" in saved.text
        row = client.app.state.db.one("SELECT * FROM github_oauth_credentials")
        for key, value in credentials.items():
            assert value not in saved.text
            assert row[key] != value
            assert client.app.state.security.open(row[key]) == value
        assert config.admin_password not in saved.text

        response = client.post("/admin", data={"csrf": csrf, "action": "logout"})
        assert "Admin password" in response.text
        assert client.post("/admin", data={"csrf": csrf, **credentials}).status_code == 401


def test_admin_login_is_rate_limited_and_cookie_expires(config):
    with open_client(config) as client:
        sign_in(client, config)
        cookie = client.cookies.get("coral_admin")
        cipher = client.app.state.security.cipher
        expired = cipher.encrypt_at_time(cipher.decrypt(cookie.encode()), int(time.time()) - 901).decode()
        client.cookies.set("coral_admin", expired, domain="coral.example.com", path="/admin")
        assert "Admin password" in client.get("/admin").text
        for _ in range(7):
            assert client.post("/admin/login", data={"password": "wrong"}).status_code == 401
        assert client.post("/admin/login", data={"password": "wrong"}).status_code == 429
        assert client.get("/health").status_code == 200


def test_saved_credentials_drive_oauth_and_survive_restart(config, monkeypatch):
    exchanged = []

    def github(request):
        if request.url.host == "github.com":
            assert request.url.path == "/login/oauth/access_token"
            exchanged.append(parse_qs(request.content.decode()))
            return httpx.Response(200, json={"access_token": "github-account-token"})
        assert request.url == "https://api.github.com/user"
        assert request.headers["Authorization"] == "Bearer github-account-token"
        return httpx.Response(200, json={"id": 1234, "login": "coral-user"})

    async_client = httpx.AsyncClient
    monkeypatch.setattr("coral.app.httpx.AsyncClient", lambda **kwargs: async_client(transport=httpx.MockTransport(github), **kwargs))

    legacy = replace(config, client_id="legacy-id", client_secret="legacy-secret")
    with open_client(legacy) as client:
        assert prepare(client)["client_id"] == ["legacy-id"]
        sign_in(client, legacy)
        csrf = form_csrf(client)
        client.post("/admin", data={"csrf": csrf, "client_id": "saved-id", "client_secret": "initial-secret"})
        params = prepare(client)
        assert params["client_id"] == ["saved-id"]
        assert params["redirect_uri"] == [BACKEND + "/auth/callback"]
        client.post("/admin", data={"csrf": csrf, "client_id": "saved-id", "client_secret": "rotated-secret"})
        client.app.state.db.connection.close()

    with open_client(replace(legacy, admin_password="")) as client:
        assert client.get("/admin").status_code == 404
        assert prepare(client)["client_id"] == ["saved-id"]
        callback = client.get("/auth/callback", params={"state": params["state"][0], "code": "from-github"}, follow_redirects=False)
        assert callback.status_code == 302
        assert exchanged == [{"client_id": ["saved-id"], "client_secret": ["rotated-secret"],
                              "code": ["from-github"], "redirect_uri": [BACKEND + "/auth/callback"]}]
        redirect = urlsplit(callback.headers["Location"])
        assert callback.headers["Location"].startswith(DASHBOARD + "/#code=")
        code = parse_qs(redirect.fragment)["code"][0]
        exchange = client.post("/auth/exchange", json={"code": code, "verifier": VERIFIER})
        assert exchange.status_code == 200
        profiles = client.get("/profiles", headers={"Authorization": "Bearer " + exchange.json()["token"]})
        assert profiles.json()["profiles"][0]["login"] == "coral-user"


def test_switching_github_apps_requires_a_fresh_login(config):
    with open_client(replace(config, client_id="old-app", client_secret="old-secret")) as client:
        params = prepare(client, "native")
        sign_in(client, config)
        client.post("/admin", data={"csrf": form_csrf(client), "client_id": "new-app", "client_secret": "new-secret"})
        callback = client.get("/auth/callback", params={"state": params["state"][0], "code": "from-github"}, follow_redirects=False)
        assert callback.status_code == 302
        assert callback.headers["Location"].startswith("coral://auth?")
        assert "Start sign-in again" in parse_qs(urlsplit(callback.headers["Location"]).query)["error"][0]
