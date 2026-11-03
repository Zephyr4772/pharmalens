"""Single-process DuckDB access.

DuckDB allows one writer process, so the API server owns the database: request
handlers take cursors off one shared connection, and connectors run in the same
process (scheduler thread) and serialize their writes through WRITE_LOCK.
"""
import threading
from contextlib import contextmanager
from pathlib import Path

import duckdb

from .config import DB_PATH, duckdb_settings


class DatabaseUnavailable(RuntimeError):
    pass


_conn: duckdb.DuckDBPyConnection | None = None
_conn_lock = threading.Lock()
WRITE_LOCK = threading.RLock()


def get_conn() -> duckdb.DuckDBPyConnection:
    global _conn
    with _conn_lock:
        if _conn is None:
            if not DB_PATH.exists():
                raise DatabaseUnavailable(
                    f"database not found at {DB_PATH}. run: py -3 -m pharmalens.pipeline.build_core"
                )
            _conn = duckdb.connect(str(DB_PATH))
            duckdb_settings(_conn)
            # live tables are CREATE IF NOT EXISTS, so new ones appear without a core rebuild
            _conn.execute((Path(__file__).parent / "schema.sql").read_text())
        return _conn


def cursor() -> duckdb.DuckDBPyConnection:
    return get_conn().cursor()


@contextmanager
def writer():
    with WRITE_LOCK:
        cur = get_conn().cursor()
        try:
            cur.execute("BEGIN")
            yield cur
            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise
        finally:
            cur.close()


def rows(cur, sql: str, params=None) -> list[dict]:
    res = cur.execute(sql, params or [])
    cols = [d[0] for d in res.description]
    return [dict(zip(cols, r)) for r in res.fetchall()]


def one(cur, sql: str, params=None) -> dict | None:
    r = rows(cur, sql, params)
    return r[0] if r else None


def memory_top(n: int = 4) -> str:
    """DuckDB's largest memory users right now, for out-of-memory reports."""
    try:
        return ", ".join(f"{t} {mb:.0f}MB" for t, mb in cursor().execute(
            "SELECT tag, memory_usage_bytes / 1e6 FROM duckdb_memory() ORDER BY 2 DESC LIMIT ?", [n]).fetchall())
    except Exception:  # noqa: BLE001
        return "?"


@contextmanager
def memory_limit(limit: str):
    """Run with a different DuckDB memory limit (one connection, so it applies process-wide), then restore it."""
    from .config import DUCKDB_MEMORY
    cur = cursor()
    cur.execute(f"SET memory_limit = '{limit}'")
    try:
        yield
    finally:
        cur.execute(f"SET memory_limit = '{DUCKDB_MEMORY}'")


def close():
    global _conn
    with _conn_lock:
        if _conn is not None:
            try:
                _conn.execute("CHECKPOINT")
            except Exception:  # noqa: BLE001
                pass
            _conn.close()
            _conn = None
