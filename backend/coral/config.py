import os
from dataclasses import dataclass


@dataclass
class Config:
    database: str = os.getenv("CORAL_DATABASE", ".coral/coral.sqlite")
    database_url: str = os.getenv("CORAL_DATABASE_URL", "")
    scheduler_token: str = os.getenv("CORAL_SCHEDULER_TOKEN", "")
    hosting_mode: str = os.getenv("CORAL_HOSTING_MODE", "standard")
    encryption_key: str = os.getenv("CORAL_ENCRYPTION_KEY", "")
    client_id: str = os.getenv("GITHUB_CLIENT_ID", "")
    client_secret: str = os.getenv("GITHUB_CLIENT_SECRET", "")
    public_url: str = os.getenv("CORAL_PUBLIC_URL", "http://127.0.0.1:8000")
    web_url: str = os.getenv("CORAL_WEB_URL", "http://127.0.0.1:8080")
    demo: bool = os.getenv("CORAL_DEMO", "0") == "1"
    tick_seconds: float = 5
    allowance: int = 4 * 60 * 60
    idle_seconds: int = 600
    max_extension: int = 120 * 60
    stop_reserve: int = 30

    def validate(self):
        if not self.demo:
            if not all((self.encryption_key, self.client_id, self.client_secret)):
                raise RuntimeError("Configure CORAL_ENCRYPTION_KEY and GitHub OAuth credentials. See README.")
            if not self.public_url.startswith("https://") or not self.web_url.startswith("https://"):
                raise RuntimeError("Production requires HTTPS backend and dashboard URLs.")
            if self.hosting_mode == "render-free":
                if not self.database_url.startswith(("postgresql://", "postgres://")):
                    raise RuntimeError("Render Free requires CORAL_DATABASE_URL for an external persistent PostgreSQL database.")
                if len(self.scheduler_token) < 32:
                    raise RuntimeError("Render Free requires a CORAL_SCHEDULER_TOKEN of at least 32 characters and an external scheduler.")
