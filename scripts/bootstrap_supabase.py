#!/usr/bin/env python3
"""Initialize an existing Supabase database without printing its credentials."""
import argparse
import getpass
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from coral.db import Database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save-env", action="store_true", help="Save the verified URI in ignored .coral/render-database.env (permissions 600).")
    args = parser.parse_args()
    uri = os.environ.get("CORAL_DATABASE_URL") or getpass.getpass("Supabase Session pooler URI (hidden): ")
    parsed = urlsplit(uri)
    if parsed.scheme not in ("postgresql", "postgres") or not parsed.hostname or not parsed.password:
        parser.error("Provide the PostgreSQL Session pooler URI with its database password.")
    if any(character in uri for character in ("\n", "\r", "\x00")):
        parser.error("The database URI must be a single line.")
    db = None
    marker = "bootstrap-" + str(uuid.uuid4())
    try:
        db = Database(":memory:", uri)
        with db.transaction() as tx:
            tx.execute("INSERT INTO metadata VALUES(?,?)", (marker, 1700000000.125))
        row = db.one("SELECT value FROM metadata WHERE key=?", (marker,))
        if not row or row["value"] != 1700000000.125:
            raise RuntimeError("Database timestamp precision check failed")
        db.execute("DELETE FROM metadata WHERE key=?", (marker,))
        if args.save_env:
            destination = Path(__file__).resolve().parents[1] / ".coral/render-database.env"
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                stream.write("CORAL_DATABASE_URL=" + uri + "\n")
            print("Verified database URI saved in .coral/render-database.env. Copy its value into Render; do not commit it.")
        print("Coral's private database schema is initialized; TLS, transactions, and timestamp precision verified.")
    except FileExistsError:
        print("Database initialized. Existing .coral/render-database.env was preserved; no credentials overwritten.", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Database initialization failed ({type(error).__name__}). Check the connection URI, network access, and database role permissions. Credentials were not printed.", file=sys.stderr)
        return 1
    finally:
        if db:
            db.connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
