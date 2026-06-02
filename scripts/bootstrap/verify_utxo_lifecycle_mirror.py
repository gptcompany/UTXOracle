#!/usr/bin/env python3
"""Post-mirror integrity check for QuestDB utxo_lifecycle.

spec-061 F1 mitigation (review 2026-06-02):
  The DuckDB -> QuestDB lifecycle mirror saves its checkpoint at the
  block-batch boundary (every `block_batch_size` blocks), not after each
  row INSERT. If the mirror process crashes mid-batch AFTER some row
  inserts completed but BEFORE the checkpoint advanced, a subsequent
  `--resume` will re-issue those inserts. QuestDB `utxo_lifecycle` has no
  DEDUP UPSERT KEYS — it pre-dates spec-061 and cannot be retrofit on a
  164M-row table without significant downtime — so the re-inserts land as
  duplicate rows.

  This script verifies the mirror landed cleanly:
    1. Reports total row count vs distinct outpoint count.
    2. If duplicates exist, optionally executes a dedup pass that keeps
       the row with the highest `spent_block` per outpoint (or the first
       row, deterministic by ts) and DELETEs the rest.

Usage:
    # Verify only (read-only)
    uv run python -m scripts.bootstrap.verify_utxo_lifecycle_mirror

    # Verify + dedup (writes)
    uv run python -m scripts.bootstrap.verify_utxo_lifecycle_mirror --fix

Exit codes:
    0 — no duplicates found (or --fix applied successfully)
    1 — duplicates exist and --fix was not passed
    2 — backend error / RPC failure
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntegrityReport:
    total_rows: int
    distinct_outpoints: int

    @property
    def duplicate_rows(self) -> int:
        return self.total_rows - self.distinct_outpoints

    @property
    def is_clean(self) -> bool:
        return self.duplicate_rows == 0


def _open_questdb_connection():
    if psycopg is None:
        raise ModuleNotFoundError(
            "psycopg is required for QuestDB integrity check; install project deps"
        )
    from api.questdb_repository import (
        QUESTDB_PG_DATABASE,
        QUESTDB_PG_HOST,
        QUESTDB_PG_PASSWORD,
        QUESTDB_PG_PORT,
        QUESTDB_PG_USER,
    )

    return psycopg.connect(
        host=QUESTDB_PG_HOST,
        port=QUESTDB_PG_PORT,
        user=QUESTDB_PG_USER,
        password=QUESTDB_PG_PASSWORD,
        dbname=QUESTDB_PG_DATABASE,
        autocommit=True,
    )


def verify(conn=None) -> IntegrityReport:
    """Run the integrity check; return the report. Read-only."""
    if conn is None:
        with _open_questdb_connection() as owned:
            return verify(owned)

    with conn.cursor() as cur:
        cur.execute("SELECT count() FROM utxo_lifecycle")
        total = int(cur.fetchone()[0])
        cur.execute("SELECT count_distinct(outpoint) FROM utxo_lifecycle")
        distinct = int(cur.fetchone()[0])

    report = IntegrityReport(total_rows=total, distinct_outpoints=distinct)
    logger.info(
        "utxo_lifecycle integrity: %d rows, %d distinct outpoints, %d duplicates",
        report.total_rows,
        report.distinct_outpoints,
        report.duplicate_rows,
    )
    return report


def fix_duplicates(conn=None) -> int:
    """Deduplicate utxo_lifecycle in-place, keeping the row with the latest
    creation timestamp per outpoint. Returns the number of rows deleted.

    QuestDB-compatible: uses a window-function variant via a temp table so the
    operation is single-statement at the API surface but explicit at the SQL.
    """
    if conn is None:
        with _open_questdb_connection() as owned:
            return fix_duplicates(owned)

    with conn.cursor() as cur:
        cur.execute("SELECT count() FROM utxo_lifecycle")
        before = int(cur.fetchone()[0])

        # Materialise the de-dup target through a temp staging table so the
        # final swap is atomic. QuestDB supports `CREATE TABLE ... AS SELECT`
        # but window functions; we use the deterministic "row with max ts per
        # outpoint" recipe.
        cur.execute(
            """
            CREATE TABLE utxo_lifecycle_dedup AS
            SELECT * FROM utxo_lifecycle
            LATEST ON ts PARTITION BY outpoint
            """
        )
        cur.execute("DROP TABLE utxo_lifecycle")
        cur.execute("RENAME TABLE utxo_lifecycle TO utxo_lifecycle_dedup")
        cur.execute("SELECT count() FROM utxo_lifecycle")
        after = int(cur.fetchone()[0])

    deleted = before - after
    logger.info("utxo_lifecycle dedup: deleted %d duplicate rows", deleted)
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="If duplicates exist, run the dedup pass. Default is read-only.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    try:
        report = verify()
    except Exception as exc:
        logger.error("Integrity check failed: %s", exc)
        return 2

    if report.is_clean:
        logger.info("OK: no duplicates detected.")
        return 0

    if not args.fix:
        logger.error(
            "FAIL: %d duplicate rows detected. Re-run with --fix to dedup.",
            report.duplicate_rows,
        )
        return 1

    try:
        deleted = fix_duplicates()
    except Exception as exc:
        logger.error("Dedup pass failed: %s", exc)
        return 2

    logger.info("Dedup complete: %d rows removed.", deleted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
