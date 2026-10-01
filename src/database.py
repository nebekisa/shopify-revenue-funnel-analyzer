"""DuckDB connection and query helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from src import config as cfg
from src.utils import get_logger, ensure_dirs

logger = get_logger(__name__)


def connect(db_path: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    """Open (or create) a DuckDB connection.

    Pass ':memory:' for an ephemeral in-memory DB (used in tests).
    """
    if db_path == ":memory:":
        return duckdb.connect(":memory:")
    ensure_dirs(cfg.PROCESSED_DIR)
    path = db_path or cfg.DUCKDB_PATH
    return duckdb.connect(str(path))


def register_raw(con: duckdb.DuckDBPyConnection,
                 tables: dict[str, pd.DataFrame]) -> None:
    for name, df in tables.items():
        con.register(name, df)
        logger.info("Registered raw view: %s (%d rows)", name, len(df))


def run_sql_file(con: duckdb.DuckDBPyConnection, path: Path) -> pd.DataFrame:
    sql = path.read_text(encoding="utf-8")
    return con.execute(sql).df()


def query(con: duckdb.DuckDBPyConnection,
          sql: str,
          params: dict[str, Any] | None = None) -> pd.DataFrame:
    """Execute a parameterized query safely.

    DuckDB's Python API accepts a dict for named ($name) parameters.
    We always pass a dict — never None — to avoid version-specific
    TypeError on empty-parameter queries.
    """
    if params:
        return con.execute(sql, params).df()
    return con.execute(sql).df()