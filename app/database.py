import os
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def get_database_path() -> Path:
    configured_path = os.getenv("CODEADVENTURE_DB_PATH")
    path = Path(configured_path) if configured_path else PROJECT_ROOT / "data" / "codeadventure.db"
    return path.expanduser().resolve()


@contextmanager
def get_connection(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    database_path = path or get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            yield connection


def initialize_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (1)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (2)"
        )
