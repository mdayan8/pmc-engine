"""
Database Layer — Simple SQLite wrapper.
"""
import sqlite3
from typing import Optional, Any


DB_PATH = ":memory:"


def connect() -> sqlite3.Connection:
    """Connect to the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def close(conn: sqlite3.Connection):
    """Close database connection."""
    conn.close()


def query(sql: str, params: tuple = ()) -> Optional[Any]:
    """
    Execute a query and return first row or None.

    Args:
        sql: SQL query string
        params: Query parameters

    Returns:
        First row as dict, or None
    """
    conn = connect()
    try:
        cursor = conn.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        close(conn)


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a query and return all rows."""
    conn = connect()
    try:
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        close(conn)
