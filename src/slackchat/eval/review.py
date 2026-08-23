"""Human scoring against the rubric. Phase 1 has no LLM judge on purpose.

Human scores are the real ground truth, and later the calibration set for a
judge. The ``reviewer`` column is in the primary key from the start, so
measuring judge-human agreement in Phase 2 is a JOIN, not a migration.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from slackchat.core.prompts import parse_frontmatter
from slackchat.store import sqlite as store

DIMENSIONS: dict[str, tuple[str, ...]] = {
    "translation": ("Adequacy", "Naturalness", "Voice compliance", "Concision"),
    "correction": ("Minimality", "Correctness", "Voice preservation"),
}

_RUBRIC_PATH = Path(__file__).resolve().parent / "rubric.md"
VALID_SCORES = {"0", "1", "2"}


def rubric_version() -> str:
    meta, _ = parse_frontmatter(_RUBRIC_PATH.read_text(encoding="utf-8"))
    return meta.get("version", "0")


def unreviewed_runs(
    conn: sqlite3.Connection, limit: int, reviewer: str = "human"
) -> list[sqlite3.Row]:
    """Eval runs this reviewer has not scored yet, oldest first."""
    return list(
        conn.execute(
            """
            SELECT r.* FROM runs r
            WHERE r.client = 'eval'
              AND r.error IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM reviews v
                WHERE v.run_id = r.run_id AND v.reviewer = ?
              )
            ORDER BY r.created_at ASC, r.rowid ASC
            LIMIT ?
            """,
            (reviewer, limit),
        )
    )


def review_session(
    conn: sqlite3.Connection,
    *,
    limit: int,
    read_line: Callable[[str], str],
    write: Callable[[str], None],
    clock: Callable[[], str],
    reviewer: str = "human",
) -> int:
    """Score runs one at a time. Returns how many were fully scored.

    Scores for a run are written only after every dimension is answered, so
    an interrupted session leaves no half-scored run behind to skew an
    agreement calculation later.
    """
    runs = unreviewed_runs(conn, limit, reviewer)
    if not runs:
        write("nothing to review\n")
        return 0

    write(f"rubric version {rubric_version()} — scores are 0, 1 or 2\n")
    scored = 0
    for index, row in enumerate(runs, start=1):
        write(f"\n[{index}/{len(runs)}] {row['run_id']}  {row['mode']}\n")
        write(f"  in : {row['input']}\n")
        write(f"  out: {row['output']}\n")

        pending: list[tuple[str, int]] = []
        try:
            for dimension in DIMENSIONS[row["mode"]]:
                pending.append((dimension, _ask_score(dimension, read_line)))
            note = read_line("  note (optional): ").strip() or None
        except EOFError:
            write("\nstopped\n")
            break

        for dimension, score in pending:
            store.insert_review(
                conn,
                run_id=row["run_id"],
                dimension=dimension,
                score=score,
                reviewer=reviewer,
                note=note,
                created_at=clock(),
            )
        scored += 1

    write(f"\nscored {scored} run(s)\n")
    return scored


def _ask_score(dimension: str, read_line: Callable[[str], str]) -> int:
    while True:
        answer = read_line(f"  {dimension} [0/1/2]: ").strip()
        if answer in VALID_SCORES:
            return int(answer)
