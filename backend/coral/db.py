import sqlite3
import re
import threading
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, login TEXT NOT NULL, github_id INTEGER UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS profiles(
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), login TEXT NOT NULL,
 github_id INTEGER NOT NULL, token TEXT NOT NULL, repository TEXT NOT NULL DEFAULT '',
 codespace TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'unconfigured',
 hermes INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '', UNIQUE(user_id,github_id));
CREATE UNIQUE INDEX IF NOT EXISTS bound_codespace ON profiles(codespace) WHERE codespace != '';
CREATE TABLE IF NOT EXISTS auth_tokens(hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS github_oauth_credentials(
 id INTEGER PRIMARY KEY CHECK (id=1), client_id TEXT NOT NULL, client_secret TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS oauth(state TEXT PRIMARY KEY,challenge TEXT NOT NULL,client TEXT NOT NULL,user_id TEXT,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS exchanges(code TEXT PRIMARY KEY,user_id TEXT NOT NULL,challenge TEXT NOT NULL,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),profile_id TEXT NOT NULL REFERENCES profiles(id),
 mode TEXT NOT NULL, started REAL NOT NULL,accounted REAL NOT NULL,last_activity REAL NOT NULL,
 extended_until REAL, ended REAL,reason TEXT NOT NULL DEFAULT '',deadline REAL NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS one_live_session ON sessions(user_id) WHERE ended IS NULL;
CREATE TABLE IF NOT EXISTS usage(user_id TEXT NOT NULL,day TEXT NOT NULL,seconds REAL NOT NULL,PRIMARY KEY(user_id,day));
CREATE TABLE IF NOT EXISTS profile_usage(profile_id TEXT NOT NULL,day TEXT NOT NULL,seconds REAL NOT NULL,PRIMARY KEY(profile_id,day));
CREATE TABLE IF NOT EXISTS schedules(
 id TEXT PRIMARY KEY,profile_id TEXT NOT NULL REFERENCES profiles(id),title TEXT NOT NULL,prompt TEXT NOT NULL,
 recurrence TEXT NOT NULL,next_run REAL NOT NULL,interval_seconds INTEGER NOT NULL,
 duration_limit INTEGER NOT NULL,paused INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS tasks(
 id TEXT PRIMARY KEY,profile_id TEXT NOT NULL REFERENCES profiles(id),schedule_id TEXT,
 occurrence REAL,kind TEXT NOT NULL,prompt TEXT NOT NULL,status TEXT NOT NULL,
 output TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '',created REAL NOT NULL,
 deadline REAL NOT NULL,finished REAL, UNIQUE(schedule_id,occurrence));
CREATE UNIQUE INDEX IF NOT EXISTS one_running_task ON tasks(profile_id) WHERE status IN ('queued','running');
CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,task_id TEXT NOT NULL,title TEXT NOT NULL,created REAL NOT NULL,read INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS requests(user_id TEXT NOT NULL,key TEXT NOT NULL,task_id TEXT NOT NULL,PRIMARY KEY(user_id,key));
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value REAL NOT NULL);
"""


def postgres_sql(sql):
    """Translate the small, fixed set of SQL statements used by Coral; values stay bound."""
    if sql == "BEGIN IMMEDIATE":
        return "BEGIN"
    ignore = bool(re.match(r"INSERT OR IGNORE INTO\b", sql, re.I))
    sql = re.sub(r"INSERT OR IGNORE INTO\b", "INSERT INTO", sql, flags=re.I)
    sql = re.sub(r"\browid\b", "id", sql, flags=re.I)
    sql = sql.replace("?", "%s")
    if ignore:
        sql = sql.rstrip("; ") + " ON CONFLICT DO NOTHING"
    return sql


def postgres_schema():
    # PostgreSQL REAL has too little precision for Unix timestamps. Use float64.
    schema = re.sub(r"PRAGMA[^;]*;", "", SCHEMA)
    schema = re.sub(r"\bREAL\b", "DOUBLE PRECISION", schema)
    return re.sub(r"github_id INTEGER", "github_id BIGINT", schema)


def postgres_bootstrap():
    # Backend tables contain OAuth credentials and must not live in Supabase's
    # public API schema. Do not add this schema to Supabase's exposed schemas.
    statements = ["CREATE SCHEMA IF NOT EXISTS coral", "REVOKE ALL ON SCHEMA coral FROM PUBLIC"]
    statements.extend(statement.strip() for statement in postgres_schema().split(";") if statement.strip())
    tables = re.findall(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", postgres_schema())
    statements.extend(f"ALTER TABLE coral.{table} ENABLE ROW LEVEL SECURITY" for table in tables)
    return statements


class PostgresConnection:
    def __init__(self, url):
        import psycopg
        from psycopg.rows import dict_row
        self.psycopg = psycopg
        self.url = url
        self.row_factory = dict_row
        self.in_transaction = False
        self.raw = self.connect()
        for statement in postgres_bootstrap():
            self.raw.execute(statement)

    def connect(self):
        return self.psycopg.connect(self.url, autocommit=True, row_factory=self.row_factory,
                                    sslmode="require", connect_timeout=15, application_name="Coral",
                                    options="-c search_path=coral")

    def execute(self, sql, args=()):
        translated = postgres_sql(sql)
        if self.raw.closed:
            if self.in_transaction:
                if translated == "ROLLBACK":
                    self.in_transaction = False
                raise sqlite3.OperationalError("Database connection was interrupted during a transaction.")
            self.raw = self.connect()
        try:
            result = self.raw.execute(translated, args or None)
            if translated == "BEGIN":
                self.in_transaction = True
            elif translated in ("COMMIT", "ROLLBACK"):
                self.in_transaction = False
            return result
        except self.psycopg.IntegrityError as error:
            # Preserve the same domain error handling for both storage engines.
            raise sqlite3.IntegrityError("A database uniqueness or ownership constraint was violated.") from error

    def close(self):
        self.raw.close()


class Database:
    def __init__(self, path, database_url=""):
        self.engine = "postgresql" if database_url else "sqlite"
        if database_url:
            self.connection = PostgresConnection(database_url)
        else:
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA busy_timeout=5000")
            self.connection.executescript(SCHEMA)
        self.lock = threading.RLock()

    @contextmanager
    def transaction(self):
        with self.lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield self.connection
                self.connection.execute("COMMIT")
            except BaseException:
                try:
                    self.connection.execute("ROLLBACK")
                except Exception:
                    pass # Preserve the original error when the connection itself failed.
                raise

    def rows(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.connection.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.rows(sql, args)
        return rows[0] if rows else None

    def execute(self, sql, args=()):
        with self.lock:
            return self.connection.execute(sql, args)
