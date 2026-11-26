import base64
import hashlib
import secrets
import time
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


class Security:
    def __init__(self, db, config):
        self.db = db
        self.cipher = Fernet(config.encryption_key or Fernet.generate_key())
        self.oauth_fallback = (config.client_id, config.client_secret) if config.client_id and config.client_secret else None

    def seal(self, value):
        return self.cipher.encrypt(value.encode()).decode()

    def open(self, value, *, ttl=None):
        return self.cipher.decrypt(value.encode(), ttl=ttl).decode()

    def github_oauth_credentials(self):
        row = self.db.one("SELECT client_id,client_secret FROM github_oauth_credentials WHERE id=1")
        if row:
            return self.open(row["client_id"]), self.open(row["client_secret"])
        return self.oauth_fallback

    def save_github_oauth_credentials(self, client_id, client_secret):
        self.db.execute(
            """INSERT INTO github_oauth_credentials (id,client_id,client_secret) VALUES (1,?,?)
               ON CONFLICT (id) DO UPDATE SET client_id=excluded.client_id,client_secret=excluded.client_secret""",
            (self.seal(client_id), self.seal(client_secret)),
        )

    def issue(self, user_id):
        token = secrets.token_urlsafe(48)
        self.db.execute("INSERT INTO auth_tokens VALUES(?,?,?)", (digest(token), user_id, time.time() + 30 * 86400))
        return token

    def authenticate(self, authorization):
        token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
        result = self.db.one("SELECT user_id FROM auth_tokens WHERE hash=? AND expires>?", (digest(token), time.time()))
        if not result:
            raise HTTPException(401, "Sign in with GitHub to continue.")
        return result["user_id"]

    def issue_agent_token(self, task_id):
        return self.seal("coral-hermes-task:" + task_id)

    def authenticate_agent(self, authorization):
        token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
        try:
            claim = self.open(token, ttl=7200)
        except InvalidToken:
            raise HTTPException(401, "Coral tools require an active Hermes task.") from None
        if not claim.startswith("coral-hermes-task:"):
            raise HTTPException(401, "Coral tools require an active Hermes task.")
        now = time.time()
        result = self.db.one(
            """SELECT p.id AS profile_id, p.user_id, t.id AS task_id FROM tasks t JOIN profiles p ON p.id=t.profile_id
               JOIN sessions s ON s.profile_id=p.id
               WHERE t.id=? AND t.kind='hermes' AND t.status IN ('queued','running') AND t.deadline>?
               AND p.state='available' AND s.ended IS NULL AND s.deadline>?""",
            (claim.removeprefix("coral-hermes-task:"), now, now),
        )
        if not result:
            raise HTTPException(401, "The Hermes task or Codespace session has ended.")
        return result
