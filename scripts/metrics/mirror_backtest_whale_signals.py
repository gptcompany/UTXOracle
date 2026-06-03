"""Mirror backtest_whale_signals from DuckDB to QuestDB (spec-061 T026a, R8).

The producer (`scripts/whale_flow_backtest.py`) writes a DuckDB table
with `timestamp BIGINT` (seconds since epoch). The consumer-visible
QuestDB surface needs `ts TIMESTAMP` matching the contract registry's
pinned columns. This script bridges the two: read every DuckDB row,
convert `timestamp` to a UTC datetime, and write to QuestDB via the
existing `save_backtest_whale_signal_row` save method (idempotent via
DEDUP UPSERT KEYS(ts)).

Producer-side rewrite (sole-producer to QuestDB) is out of scope for
spec-061. This mirror runs on its own systemd timer
(`utxoracle-backtest-mirror.timer`, 03:00 UTC, offset from the daily
aggregator at 02:30).

Usage:
    python -m scripts.metrics.mirror_backtest_whale_signals
    python -m scripts.metrics.mirror_backtest_whale_signals --duckdb-path /custom/path
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from typing import Optional

import duckdb

from api.questdb_repository import save_backtest_whale_signal_row
from scripts.config import UTXORACLE_DB_PATH

logger = logging.getLogger(__name__)

# Columns must match the pinned set in
# docs/contracts/stream_registry.yaml::backtest_whale_signals.pinned_columns
# (minus `ts`, which is derived from the BIGINT `timestamp`).
_SELECT_COLUMNS = (
    "timestamp",
    "net_flow_btc",
    "confidence",
    "btc_price",
    "inflow_btc",
    "outflow_btc",
    "tx_count_relevant",
)


def mirror(duckdb_path: Optional[str] = None) -> int:
    """Read every row from the DuckDB producer table and mirror into QuestDB.

    Returns the count of rows successfully written. A row whose write
    raises is logged and skipped - the remaining rows still ship.
    Idempotent: re-runs UPSERT on `ts` (QuestDB DEDUP UPSERT KEYS).
    """
    path = duckdb_path or str(UTXORACLE_DB_PATH)
    conn = duckdb.connect(path, read_only=True)
    try:
        table_exists = conn.execute(
            """
            SELECT count(*)
            FROM information_schema.tables
            WHERE table_schema = 'main'
              AND table_name = 'backtest_whale_signals'
            """
        ).fetchone()
        if not table_exists or int(table_exists[0]) == 0:
            logger.warning(
                "mirror_backtest_whale_signals: DuckDB source table is missing; "
                "nothing to mirror"
            )
            return 0

        rows = conn.execute(
            f"SELECT {', '.join(_SELECT_COLUMNS)} FROM backtest_whale_signals "
            f"ORDER BY timestamp"
        ).fetchall()
    finally:
        conn.close()
    logger.info("mirror_backtest_whale_signals: read %d rows from DuckDB", len(rows))

    written = 0
    for row in rows:
        (
            ts_bigint,
            net_flow_btc,
            confidence,
            btc_price,
            inflow_btc,
            outflow_btc,
            tx_count_relevant,
        ) = row
        ts = datetime.fromtimestamp(int(ts_bigint), tz=timezone.utc)
        try:
            save_backtest_whale_signal_row(
                ts=ts,
                net_flow_btc=(
                    float(net_flow_btc) if net_flow_btc is not None else None
                ),
                confidence=(float(confidence) if confidence is not None else None),
                btc_price=(float(btc_price) if btc_price is not None else None),
                inflow_btc=(float(inflow_btc) if inflow_btc is not None else None),
                outflow_btc=(float(outflow_btc) if outflow_btc is not None else None),
                tx_count_relevant=(
                    int(tx_count_relevant) if tx_count_relevant is not None else None
                ),
            )
            written += 1
        except Exception as exc:
            logger.error(
                "mirror_backtest_whale_signals: row at ts=%s failed: %s", ts, exc
            )

    logger.info(
        "mirror_backtest_whale_signals: wrote %d/%d rows to QuestDB", written, len(rows)
    )
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--duckdb-path", default=None, help="Override the DuckDB source path"
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    mirror(duckdb_path=args.duckdb_path)


if __name__ == "__main__":
    main()
