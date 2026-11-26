import os
import sqlite3
import time
import uuid
from types import SimpleNamespace
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from coral.app import create_app
from coral.config import Config
from coral.db import Database, PostgresConnection, postgres_schema, postgres_sql, postgres_bootstrap


def production_config(**values):
    args = dict(demo=False, hosting_mode="render-free", database_url="postgresql://user:password@host/db",
                scheduler_token="s" * 48, client_id="id", client_secret="secret",
                encryption_key=Fernet.generate_key().decode(), public_url="https://coral.example.com",
                web_url="https://mathobsession.github.io/Coral")
    args.update(values)
    return Config(**args)


def test_free_hosting_refuses_ephemeral_database_fallback():
    with pytest.raises(RuntimeError, match="external persistent PostgreSQL"):
        production_config(database_url="").validate()
    with pytest.raises(RuntimeError, match="CORAL_SCHEDULER_TOKEN"):
        production_config(scheduler_token="short").validate()
    production_config().validate()


def test_postgres_preserves_timestamp_precision_and_domain_constraints():
    schema = postgres_schema()
    assert "PRAGMA" not in schema
    assert "expires DOUBLE PRECISION" in schema
    assert "started DOUBLE PRECISION" in schema
    assert "github_id BIGINT" in schema
    assert "WHERE ended IS NULL" in schema
    assert "UNIQUE(schedule_id,occurrence)" in schema


def test_fixed_sql_translation_keeps_values_parameterized():
    assert postgres_sql("BEGIN IMMEDIATE") == "BEGIN"
    assert postgres_sql("SELECT * FROM profiles WHERE user_id=? ORDER BY rowid") == "SELECT * FROM profiles WHERE user_id=%s ORDER BY id"
    assert postgres_sql("INSERT OR IGNORE INTO users VALUES(?,?,?)") == "INSERT INTO users VALUES(%s,%s,%s) ON CONFLICT DO NOTHING"


def test_supabase_backend_tables_are_private_and_use_rls():
    statements = postgres_bootstrap()
    assert statements[0] == "CREATE SCHEMA IF NOT EXISTS coral"
    assert "REVOKE ALL ON SCHEMA coral FROM PUBLIC" in statements
    assert "ALTER TABLE coral.profiles ENABLE ROW LEVEL SECURITY" in statements
    assert "ALTER TABLE coral.auth_tokens ENABLE ROW LEVEL SECURITY" in statements
    assert "ALTER TABLE coral.usage ENABLE ROW LEVEL SECURITY" in statements


def test_postgres_adapter_uses_tls_and_maps_integrity_failures(monkeypatch):
    import psycopg
    calls = []
    class Connection:
        closed = False
        def execute(self, sql, args=None):
            calls.append((sql, args))
            if args == ("duplicate",):
                raise psycopg.IntegrityError("private database details")
            return SimpleNamespace(fetchall=lambda: [], fetchone=lambda: None, rowcount=1)
    connections = []
    def connect(url, **options):
        connections.append(options)
        return Connection()
    monkeypatch.setattr(psycopg, "connect", connect)
    db = PostgresConnection("postgresql://private/database")
    assert connections[0]["sslmode"] == "require"
    assert connections[0]["options"] == "-c search_path=coral"
    malicious = "'; DROP TABLE profiles; --"
    db.execute("SELECT id FROM profiles WHERE login=?", (malicious,))
    assert calls[-1] == ("SELECT id FROM profiles WHERE login=%s", (malicious,))
    with pytest.raises(sqlite3.IntegrityError, match="constraint"):
        db.execute("INSERT INTO users VALUES(?)", ("duplicate",))


def test_postgres_reconnects_idle_connection_but_not_mid_transaction(monkeypatch):
    import psycopg
    connections = []
    class Connection:
        closed = False
        def execute(self, sql, args=None): return SimpleNamespace(fetchall=lambda: [])
    def connect(*args, **options):
        result = Connection(); connections.append(result); return result
    monkeypatch.setattr(psycopg, "connect", connect)
    db = PostgresConnection("postgresql://private/database")
    db.raw.closed = True
    db.execute("SELECT 1")
    assert len(connections) == 2
    db.execute("BEGIN IMMEDIATE")
    db.raw.closed = True
    with pytest.raises(sqlite3.OperationalError, match="interrupted"):
        db.execute("UPDATE usage SET seconds=0")
    assert len(connections) == 2


def test_external_scheduler_is_authenticated_and_does_not_reset_idle(tmp_path):
    config = Config(database=str(tmp_path / "db"), demo=True, scheduler_token="scheduler-" + "s" * 40)
    app = create_app(config, worker=False)
    with TestClient(app) as client:
        assert client.post("/internal/tick").status_code == 401
        assert client.post("/internal/tick", headers={"X-Coral-Scheduler-Token": "wrong"}).status_code == 401
        token = client.post("/auth/local").json()["token"]
        headers = {"Authorization": "Bearer " + token}
        profile = client.get("/profiles", headers=headers).json()["profiles"][0]
        client.post(f'/profiles/{profile["id"]}/connect', headers=headers, json={"repository": "local/workspace"})
        previous = app.state.db.one("SELECT last_activity FROM sessions WHERE ended IS NULL")["last_activity"]
        response = client.post("/internal/tick", headers={"X-Coral-Scheduler-Token": config.scheduler_token})
        assert response.status_code == 200
        assert response.json() == {"accepted": True}
        assert app.state.service.wake.is_set()
        assert app.state.db.one("SELECT last_activity FROM sessions WHERE ended IS NULL")["last_activity"] == previous
        assert client.get("/health").json()["storage"] == "sqlite"


@pytest.mark.skipif(not os.getenv("CORAL_TEST_DATABASE_URL"), reason="Configure a dedicated PostgreSQL test database to run the live storage integration.")
def test_real_postgres_transaction_and_uniqueness():
    db = Database(":memory:", os.environ["CORAL_TEST_DATABASE_URL"])
    key = "integration-" + str(uuid.uuid4())
    try:
        with db.transaction() as tx:
            tx.execute("INSERT INTO metadata VALUES(?,?)", (key, 1700000000.125))
        assert db.one("SELECT value FROM metadata WHERE key=?", (key,))["value"] == 1700000000.125
        with pytest.raises(sqlite3.IntegrityError):
            with db.transaction() as tx:
                tx.execute("INSERT INTO metadata VALUES(?,?)", (key, 1))
        assert db.one("SELECT value FROM metadata WHERE key=?", (key,))["value"] == 1700000000.125
    finally:
        db.execute("DELETE FROM metadata WHERE key=?", (key,))
        db.connection.close()
