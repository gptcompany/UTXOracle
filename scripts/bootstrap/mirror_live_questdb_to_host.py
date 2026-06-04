#!/usr/bin/env python3
"""Mirror live QuestDB streams from :9912 (docker live stack) to :8812 (host).

spec-061 unification path (2026-06-03). Resolves the dual-QuestDB
divergence: live producers (Docker stack) write to ``utxoracle-live-questdb``
on host port 9912; the spec-061 endpoint reads from the host QuestDB on
8812. Without a bridge, fresh live data never reaches the consumer
contract.

This script is idempotent and resilient:
- Per-stream watermark in /tmp/spec061_mirror_checkpoint.json
  (``last_ts`` per table). Re-runs pick up from the last copied row.
- Empty source table -> no-op (logged at DEBUG).
- Source unreachable -> log and skip; the next cycle retries.
- Target unreachable -> abort with non-zero exit (systemd records failure).
- Uses ILP (Sender) to the host QuestDB on :9009 because the daily/live
  tables either have DEDUP UPSERT KEYS(ts) or carry a unique primary key
  (snapshot_ts on live_snapshots) — duplicates are absorbed at the WAL.

Run as a systemd timer (suggested cadence: every minute) or one-shot.

Usage:
    uv run python -m scripts.bootstrap.mirror_live_questdb_to_host

    # One stream only
    uv run python -m scripts.bootstrap.mirror_live_questdb_to_host \\
        --stream live_snapshots
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time

# Strict ISO-8601 timestamp shape; what `datetime.isoformat()` emits.
_ISO_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$"
)
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import psycopg
from questdb.ingress import Sender, IngressError

logger = logging.getLogger(__name__)

CHECKPOINT_PATH = Path("/tmp/spec061_mirror_checkpoint.json")

# Per-stream copy spec.
# - source_table / target_table: same name in both QuestDBs.
# - timestamp_column: the column used for the watermark.
# - columns_query: the SELECT list (psycopg returns dicts in this order).
# - symbol_cols: ILP symbols (low-cardinality strings).
# - column_cols: ILP columns (everything else).
# - at_column: which column becomes the ILP `at` (the designated timestamp).


@dataclass
class StreamSpec:
    source_table: str
    target_table: str
    timestamp_column: str
    column_query: str
    symbol_cols: tuple[str, ...]
    column_cols: tuple[str, ...]
    at_column: str


# Spec-061 streams that are produced by the live Docker stack.
# We mirror only what we know the live stack actually writes. Adding more
# is a config change in this dict.
STREAMS: dict[str, StreamSpec] = {
    "live_snapshots": StreamSpec(
        source_table="live_snapshots",
        target_table="live_snapshots",
        timestamp_column="ts",
        column_query=(
            "ts, snapshot_ts, schema_version, block_height, "
            "utxoracle_price, utxoracle_confidence, "
            "mempool_exchange_price, hyperliquid_oracle_price, "
            "hyperliquid_mark_price, comparison_json, features_json, "
            "source_health_json, source_timestamps_json, snapshot_json"
        ),
        # Target columns are STRING (not SYMBOL); they must be sent as
        # ILP columns. ILP symbols would crash with "Broken pipe" because
        # QuestDB rejects the type-mixed buffer wholesale.
        symbol_cols=(),
        column_cols=(
            "snapshot_ts",
            "schema_version",
            "block_height",
            "utxoracle_price",
            "utxoracle_confidence",
            "mempool_exchange_price",
            "hyperliquid_oracle_price",
            "hyperliquid_mark_price",
            "comparison_json",
            "features_json",
            "source_health_json",
            "source_timestamps_json",
            "snapshot_json",
        ),
        at_column="ts",
    ),
    "urpd_features_daily": StreamSpec(
        source_table="urpd_features_daily",
        target_table="urpd_features_daily",
        timestamp_column="ts",
        column_query=(
            "ts, schema_version, block_height, current_price_usd, "
            "bucket_size_usd, total_supply_btc, supply_below_price_pct, "
            "supply_above_price_pct, top_bucket_concentration, "
            "dominant_bucket_distance_pct, distribution_entropy, "
            "confidence, availability_timestamp, source_health_json, "
            "source_freshness_seconds"
        ),
        # schema_version is a SYMBOL on urpd_features_daily; verified via
        # SHOW COLUMNS. Other STRING / DOUBLE / TIMESTAMP go in column_cols.
        symbol_cols=("schema_version",),
        column_cols=(
            "block_height",
            "current_price_usd",
            "bucket_size_usd",
            "total_supply_btc",
            "supply_below_price_pct",
            "supply_above_price_pct",
            "top_bucket_concentration",
            "dominant_bucket_distance_pct",
            "distribution_entropy",
            "confidence",
            "availability_timestamp",
            "source_health_json",
            "source_freshness_seconds",
        ),
        at_column="ts",
    ),
}


def _load_checkpoint() -> dict[str, str]:
    if not CHECKPOINT_PATH.exists():
        return {}
    try:
        return json.loads(CHECKPOINT_PATH.read_text())
    except Exception as exc:
        logger.warning("Failed to load checkpoint %s: %s", CHECKPOINT_PATH, exc)
        return {}


def _save_checkpoint(state: dict[str, str]) -> None:
    tmp = CHECKPOINT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(CHECKPOINT_PATH)


def _source_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("LIVE_QUESTDB_PG_HOST", "127.0.0.1"),
        port=int(os.getenv("LIVE_QUESTDB_PG_PORT", "9912")),
        user=os.getenv("LIVE_QUESTDB_PG_USER", "admin"),
        password=os.getenv("LIVE_QUESTDB_PG_PASSWORD", "quest"),
        dbname=os.getenv("LIVE_QUESTDB_PG_DATABASE", "qdb"),
        autocommit=True,
        connect_timeout=10,
    )


def _target_sender() -> Sender:
    host = os.getenv("QUESTDB_ILP_HOST", "127.0.0.1")
    port = int(os.getenv("QUESTDB_ILP_PORT", "9009"))
    return Sender.from_conf(f"tcp::addr={host}:{port};")


def _stream_rows(
    conn: psycopg.Connection, spec: StreamSpec, last_ts: str | None, limit: int
) -> Iterable[dict]:
    """Yield rows from the live QuestDB strictly after ``last_ts``.

    Uses a single SELECT with ORDER BY ts ASC LIMIT, so each cycle copies a
    bounded slice (controls memory and ILP buffer pressure). The watermark
    advances strictly to avoid duplicate rows in the target.
    """
    # QuestDB PG-wire's parametrised query support is incomplete: $1 binding
    # silently returns zero rows even when the literal form matches. Inline
    # the watermark instead (and reject anything that doesn't look like a
    # plain ISO timestamp so SQL injection isn't possible).
    where = ""
    if last_ts:
        if not _ISO_TIMESTAMP_RE.match(last_ts):
            raise ValueError(f"invalid watermark format: {last_ts!r}")
        where = f"WHERE {spec.timestamp_column} > '{last_ts}'"
    query = (
        f"SELECT {spec.column_query} FROM {spec.source_table} "
        f"{where} ORDER BY {spec.timestamp_column} ASC LIMIT {int(limit)}"
    )
    with conn.cursor() as cur:
        cur.execute(query)  # type: ignore[arg-type]
        cols = [d[0] for d in (cur.description or [])]
        for row in cur:
            yield dict(zip(cols, row))


def mirror_stream(
    conn: psycopg.Connection, sender: Sender, spec: StreamSpec, last_ts: str | None,
    batch_limit: int = 5000,
) -> tuple[int, str | None]:
    """Mirror one stream. Returns (rows_copied, new_watermark)."""
    copied = 0
    new_watermark = last_ts
    for row in _stream_rows(conn, spec, last_ts, batch_limit):
        ts_value = row[spec.at_column]
        symbols = {
            k: str(row[k]) for k in spec.symbol_cols if row.get(k) is not None
        }
        columns = {}
        for k in spec.column_cols:
            v = row.get(k)
            if v is None:
                continue
            # ILP accepts datetime objects natively for TIMESTAMP columns;
            # do NOT convert to ISO string here or QuestDB rejects the row.
            columns[k] = v
        try:
            sender.row(
                spec.target_table, symbols=symbols, columns=columns, at=ts_value
            )
        except IngressError as exc:
            logger.error("ILP write failed for %s @ ts=%s: %s",
                         spec.target_table, ts_value, exc)
            break
        copied += 1
        new_watermark = (
            ts_value.isoformat() if isinstance(ts_value, datetime) else str(ts_value)
        )
    if copied:
        sender.flush()
    return copied, new_watermark


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stream",
        choices=tuple(STREAMS.keys()),
        default=None,
        help="Mirror only this stream (default: all configured streams).",
    )
    parser.add_argument("--batch-limit", type=int, default=5000)
    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    streams = (
        {args.stream: STREAMS[args.stream]} if args.stream else STREAMS
    )

    try:
        source = _source_connection()
    except Exception as exc:
        logger.warning("Source QuestDB unreachable; skipping cycle: %s", exc)
        return 0

    try:
        sender = _target_sender()
        sender.establish()
    except Exception as exc:
        logger.error("Target QuestDB unreachable: %s", exc)
        source.close()
        return 2

    state = _load_checkpoint()
    total = 0
    t0 = time.monotonic()
    try:
        for name, spec in streams.items():
            last_ts = state.get(name)
            try:
                copied, new_watermark = mirror_stream(
                    source, sender, spec, last_ts, args.batch_limit,
                )
            except Exception as exc:
                logger.error("Stream %s failed: %s", name, exc)
                continue
            if copied:
                state[name] = new_watermark or last_ts or ""
                logger.info(
                    "Mirrored %s: %d rows, new watermark %s",
                    name, copied, state[name],
                )
            else:
                logger.debug("Stream %s: no new rows (watermark %s)", name, last_ts)
            total += copied
    finally:
        try:
            sender.close()
        except Exception:
            pass
        source.close()

    _save_checkpoint(state)
    elapsed = time.monotonic() - t0
    logger.info("Mirror cycle complete: %d rows total in %.2fs", total, elapsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
