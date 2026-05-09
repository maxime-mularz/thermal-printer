"""Historique des impressions stocke en SQLite."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

DB_DIR = Path.home() / "thermal-printer" / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "history.db"


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT,
                preview TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON prints(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON prints(source)")
        conn.commit()


def log_print(source: str, kind: str, title: Optional[str], preview: str):
    """Enregistre un ticket dans l'historique."""
    preview_short = (preview or "")[:200]
    with _conn() as conn:
        conn.execute(
            "INSERT INTO prints (timestamp, source, kind, title, preview) VALUES (?, ?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), source, kind, title, preview_short),
        )
        conn.commit()


def get_history(limit: int = 20):
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, timestamp, source, kind, title, preview FROM prints ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def count_recent(source: str, since: datetime) -> int:
    """Compte les impressions d'une source depuis un timestamp."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM prints WHERE source LIKE ? AND timestamp >= ?",
            (f"{source}%", since.isoformat(timespec="seconds")),
        ).fetchone()
        return row["n"]


# Init au chargement du module
init_db()
