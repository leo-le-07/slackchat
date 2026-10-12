"""SQLite log. Queryable with SQL, which is what replay eval will need."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from slackchat.core.types import Result

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the run log with WAL enabled.

    WAL is what lets the daemon and the CLI write at the same time without
    one of them getting ``database is locked``.
    """
    if path is None:
        from slackchat.config import db_path  # local import: config is a sibling layer

        path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    return conn


def insert_run(conn: sqlite3.Connection, result: Result, client: str) -> None:
    conn.execute(
        """
        INSERT INTO runs (
          run_id, created_at, client, mode, forced, input, output, provider,
          model, prompt_version, prompt_hash, input_tokens, output_tokens,
          cost_usd, latency_ms, changed_ratio, flags, error
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            result.run_id,
            result.created_at,
            client,
            result.mode,
            int(result.forced),
            result.original,
            result.output,
            result.provider,
            result.model,
            result.prompt_version,
            result.prompt_hash,
            result.input_tokens,
            result.output_tokens,
            result.cost_usd,
            result.latency_ms,
            result.changed_ratio,
            json.dumps(result.flags),
            result.error,
        ),
    )
    conn.commit()


def recent_runs(
    conn: sqlite3.Connection, limit: int = 20, mode: str | None = None
) -> list[sqlite3.Row]:
    if mode is None:
        sql = "SELECT * FROM runs ORDER BY created_at DESC, rowid DESC LIMIT ?"
        params: tuple[object, ...] = (limit,)
    else:
        sql = "SELECT * FROM runs WHERE mode = ? ORDER BY created_at DESC, rowid DESC LIMIT ?"
        params = (mode, limit)
    return list(conn.execute(sql, params))
