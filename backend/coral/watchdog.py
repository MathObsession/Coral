"""Independent stop-only watchdog for a systemd/cron host sharing Coral's database."""
import asyncio
import time
from .config import Config
from .db import Database
from .github import GitHub
from .security import Security
from .service import Service


async def check():
    config = Config()
    config.validate()
    db = Database(config.database, config.database_url)
    heartbeat = db.one("SELECT value FROM metadata WHERE key='worker_heartbeat'")
    if heartbeat and time.time() - heartbeat["value"] < 90:
        return
    security = Security(db, config)
    service = Service(db, config, GitHub(security))
    for session in db.rows("SELECT * FROM sessions WHERE ended IS NULL"):
        await service.stop(session["user_id"], session["profile_id"], "watchdog_worker_unavailable")


if __name__ == "__main__":
    asyncio.run(check())
