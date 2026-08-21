"""SQLite database connection manager.

Uses Python's built-in sqlite3 module with WAL mode, foreign keys, and busy timeout enabled.
Supports context manager usage and direct helper methods.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sqlite3
from typing import Any

from app.database.schema import CREATE_TABLES_SQL

logger = logging.getLogger(__name__)

# Default database path (relative to project root)
DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "mehman.db"


class Database:
    """SQLite database connection manager with concurrency and transaction support.

    Usage:
        db = Database()
        db.connect()
        rows = db.execute("SELECT * FROM properties").fetchall()
        db.close()

    Or as a context manager:
        with Database() as db:
            rows = db.execute("SELECT * FROM properties").fetchall()
    """

    def __init__(self, db_path: str | Path | None = None, timeout: float = 15.0) -> None:
        self._path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._timeout = timeout
        self._conn: sqlite3.Connection | None = None

    @property
    def path(self) -> Path:
        return self._path

    def connect(self) -> sqlite3.Connection:
        """Open a connection to the SQLite database with WAL, foreign keys, and busy timeout."""
        if self._conn is not None:
            return self._conn

        if str(self._path) != ":memory:":
            self._path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self._path), timeout=self._timeout)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.execute("PRAGMA busy_timeout = 15000;")
        if str(self._path) != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL;")
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def execute(self, sql: str, params: tuple | list | dict = ()) -> sqlite3.Cursor:
        """Execute a SQL statement."""
        if self._conn is None:
            self.connect()
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, params_list: list[Any]) -> sqlite3.Cursor:
        """Execute a SQL statement against many parameter sets."""
        if self._conn is None:
            self.connect()
        return self._conn.executemany(sql, params_list)

    def executescript(self, sql_script: str) -> sqlite3.Cursor:
        """Execute multiple SQL statements formatted as a script."""
        if self._conn is None:
            self.connect()
        return self._conn.executescript(sql_script)

    def commit(self) -> None:
        """Commit the current transaction."""
        if self._conn is not None:
            self._conn.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        if self._conn is not None:
            self._conn.rollback()

    def create_tables(self) -> None:
        """Create all database tables defined in schema.py."""
        self.executescript(CREATE_TABLES_SQL)
        self.commit()

    def __enter__(self) -> "Database":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()


def get_db(db_path: str | Path | None = None) -> Database:
    """Factory helper to obtain a Database instance."""
    return Database(db_path=db_path)
