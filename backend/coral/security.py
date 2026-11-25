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

    def seal(self, value):
        return self.cipher.encrypt(value.encode()).decode()

    def open(self, value):
        return self.cipher.decrypt(value.encode()).decode()

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
