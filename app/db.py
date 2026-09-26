"""SQLite access layer: connection helper, schema bootstrap, small utilities."""
import datetime
import sqlite3
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS brands (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    domain        TEXT NOT NULL,
    location_code INTEGER NOT NULL DEFAULT 2840,
    language_code TEXT NOT NULL DEFAULT 'en',
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS keywords (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id   INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    keyword    TEXT NOT NULL,
    tier       TEXT NOT NULL DEFAULT 'target',
    created_at TEXT NOT NULL,
    UNIQUE(brand_id, keyword)
);

CREATE TABLE IF NOT EXISTS geogrids (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id      INTEGER NOT NULL UNIQUE REFERENCES brands(id) ON DELETE CASCADE,
    center_lat    REAL NOT NULL,
    center_lng    REAL NOT NULL,
    grid          INTEGER NOT NULL DEFAULT 7,
    spacing_miles REAL NOT NULL DEFAULT 3.5,
    zoom          TEXT NOT NULL DEFAULT '13z',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS geogrid_keywords (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    geogrid_id INTEGER NOT NULL REFERENCES geogrids(id) ON DELETE CASCADE,
    keyword    TEXT NOT NULL,
    UNIQUE(geogrid_id, keyword)
);

CREATE TABLE IF NOT EXISTS geogrid_points (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at   TEXT NOT NULL,
    brand_id INTEGER NOT NULL,
    brand    TEXT NOT NULL,
    keyword  TEXT NOT NULL,
    lat      REAL NOT NULL,
    lng      REAL NOT NULL,
    rank     INTEGER,
    top3     TEXT
);
CREATE INDEX IF NOT EXISTS ix_geogrid_points ON geogrid_points(brand_id, keyword, run_at);

CREATE TABLE IF NOT EXISTS ai_runs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id INTEGER NOT NULL,
    ran_at   TEXT NOT NULL,
    n_ai     INTEGER NOT NULL DEFAULT 0,
    n_cited  INTEGER NOT NULL DEFAULT 0,
    total_kw INTEGER NOT NULL DEFAULT 0,
    cost     REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_ai_runs ON ai_runs(brand_id, ran_at);

CREATE TABLE IF NOT EXISTS ai_results (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id  INTEGER NOT NULL REFERENCES ai_runs(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    has_ai  INTEGER NOT NULL DEFAULT 0,
    cited   INTEGER NOT NULL DEFAULT 0,
    refs    TEXT
);
CREATE INDEX IF NOT EXISTS ix_ai_results ON ai_results(run_id);

CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT NOT NULL,
    brand_id    INTEGER,
    brand       TEXT,
    status      TEXT NOT NULL DEFAULT 'queued',
    progress    INTEGER NOT NULL DEFAULT 0,
    total       INTEGER NOT NULL DEFAULT 0,
    cost        REAL NOT NULL DEFAULT 0,
    message     TEXT,
    error       TEXT,
    created_at  TEXT NOT NULL,
    started_at  TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_jobs_status ON jobs(status);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS counters (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
"""


def now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today() -> str:
    return datetime.date.today().isoformat()


def connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=30000")
    return con


@contextmanager
def cursor(commit: bool = False):
    con = connect()
    try:
        yield con
        if commit:
            con.commit()
    finally:
        con.close()


def init_db() -> None:
    with cursor(commit=True) as con:
        con.executescript(SCHEMA)
        for key, value in config.DEFAULT_SETTINGS.items():
            con.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))


def get_setting(key: str, default: str = "") -> str:
    with cursor() as con:
        row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def get_settings() -> dict:
    with cursor() as con:
        rows = con.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def set_settings(values: dict) -> None:
    with cursor(commit=True) as con:
        for key, value in values.items():
            con.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )


def bump_counter(key: str, amount: int = 1) -> int:
    with cursor(commit=True) as con:
        con.execute(
            "INSERT INTO counters(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = value + excluded.value",
            (key, amount),
        )
        row = con.execute("SELECT value FROM counters WHERE key = ?", (key,)).fetchone()
    return row["value"]


def read_counter(key: str) -> int:
    with cursor() as con:
        row = con.execute("SELECT value FROM counters WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else 0
