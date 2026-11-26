import base64
import hashlib
import secrets
import time
from cryptography.fernet import Fernet
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
