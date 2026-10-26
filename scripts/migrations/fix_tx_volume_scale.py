#!/usr/bin/env python3
"""Rescale metrics.tx_volume_* rows written before UTXOracle#62 (F-439).

Before #62 daily_analysis stored vout values already in BTC and estimate_real_volume
divided them by 1e8 again, so tx_volume_btc and tx_volume_usd are 1e-8 too small:
the fix multiplies both by 1e8.

Dry-run by default; --apply writes. The cutoff (--before, the instant #62 went live
for the writer) is mandatory and never guessed. Idempotence: every corrected
timestamp is recorded in `tx_volume_scale_fix` in the same transaction as the
UPDATE, and recorded rows are skipped, so a second --apply changes nothing.
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import duckdb

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SCALE = 100_000_000
MARKER_TABLE = "tx_volume_scale_fix"

# Rows before the cutoff with a volume, not yet recorded as corrected.
_PENDING = f"""
    FROM metrics m
    WHERE m.timestamp < ?
      AND (m.tx_volume_btc IS NOT NULL OR m.tx_volume_usd IS NOT NULL)
      AND NOT EXISTS (SELECT 1 FROM {MARKER_TABLE} f WHERE f.timestamp = m.timestamp)
"""


def fix_tx_volume_scale(db_path, before: datetime, apply: bool = False) -> dict:
    """Return {"found", "to_change", "changed"}; writes only when `apply`."""
    started = time.monotonic()
    conn = duckdb.connect(str(db_path), read_only=not apply)
    try:
        has_marker = bool(
            conn.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
                [MARKER_TABLE],
            ).fetchone()[0]
        )
        found = conn.execute(
            "SELECT count(*) FROM metrics WHERE timestamp < ?", [before]
        ).fetchone()[0]
        if apply and not has_marker:
            conn.execute(
                f"CREATE TABLE {MARKER_TABLE} (timestamp TIMESTAMP PRIMARY KEY,"
                " corrected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            has_marker = True
        if has_marker:
            to_change = conn.execute(
                f"SELECT count(*) {_PENDING}", [before]
            ).fetchone()[0]
        else:
            to_change = conn.execute(
                "SELECT count(*) FROM metrics WHERE timestamp < ?"
                " AND (tx_volume_btc IS NOT NULL OR tx_volume_usd IS NOT NULL)",
                [before],
            ).fetchone()[0]
        changed = 0
        if apply and to_change:
            conn.execute("BEGIN")
            try:
                # Pending is defined by the marker, not by the values, so the UPDATE does
                # not change the set the INSERT then reads.
                changed = conn.execute(
                    "UPDATE metrics SET tx_volume_btc = tx_volume_btc * ?,"
                    " tx_volume_usd = tx_volume_usd * ?"
                    " WHERE timestamp < ?"
                    " AND (tx_volume_btc IS NOT NULL OR tx_volume_usd IS NOT NULL)"
                    f" AND NOT EXISTS (SELECT 1 FROM {MARKER_TABLE} f"
                    " WHERE f.timestamp = metrics.timestamp)",
                    [SCALE, SCALE, before],
                ).fetchone()[0]
                conn.execute(
                    f"INSERT INTO {MARKER_TABLE} (timestamp) SELECT m.timestamp {_PENDING}",
                    [before],
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                logger.error("tx_volume correction rolled back", exc_info=True)
                raise
    finally:
        conn.close()
    result = {"found": found, "to_change": to_change, "changed": changed}
    logger.info(
        "%s before=%s found=%d to_change=%d changed=%d elapsed=%.3fs",
        "apply" if apply else "dry-run",
        before.isoformat(),
        found,
        to_change,
        changed,
        time.monotonic() - started,
    )
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, required=True, help="DuckDB file")
    parser.add_argument(
        "--before",
        type=datetime.fromisoformat,
        required=True,
        help="rows with timestamp strictly before this ISO instant are corrected",
    )
    parser.add_argument("--apply", action="store_true", help="write (default: dry-run)")
    args = parser.parse_args(argv)
    fix_tx_volume_scale(args.db, args.before, apply=args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
