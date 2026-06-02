#!/usr/bin/env python3
"""Mirror DuckDB UTXO lifecycle rows into QuestDB.

spec-061 operational precondition for T036:
`historical_spent_backfill --target-backend questdb` updates existing
QuestDB rows. If `utxo_lifecycle` is empty, the spent backfill can run for
days and still advance zero rows. This script seeds the QuestDB consumption
surface from the canonical DuckDB `utxo_lifecycle_full` view before the
spent-block catch-up runs.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import duckdb

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None  # type: ignore[assignment]

from scripts.config import UTXORACLE_DB_PATH

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 10_000
_DEFAULT_BLOCK_BATCH_SIZE = 1_000
_DEFAULT_CHECKPOINT_PATH = Path("data/questdb_utxo_lifecycle_mirror_checkpoint.json")

_SELECT_SQL = """
    SELECT
        txid,
        vout,
        creation_block,
        creation_timestamp,
        creation_price_usd,
        btc_value,
        realized_value_usd,
        spent_block,
        spent_timestamp,
        spent_price_usd,
        age_blocks,
        age_days,
        CAST(cohort AS VARCHAR) AS cohort,
        sopr,
        is_coinbase,
        is_spent
    FROM utxo_lifecycle_full
    WHERE creation_block BETWEEN ? AND ?
"""

_INSERT_SQL = """
    INSERT INTO utxo_lifecycle (
        outpoint,
        txid,
        vout_index,
        creation_block,
        ts,
        creation_price_usd,
        btc_value,
        realized_value_usd,
        spent_block,
        spent_timestamp,
        spent_price_usd,
        spending_txid,
        age_blocks,
        age_days,
        cohort,
        sub_cohort,
        sopr,
        is_coinbase,
        is_spent,
        price_source
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


@dataclass(frozen=True)
class MirrorStats:
    """Summary returned by `mirror` for tests and operator logs."""

    source_rows: int
    mirrored_rows: int
    start_block: int
    end_block: int
    dry_run: bool
    checkpoint_path: str | None = None


def _utc_from_unix_seconds(value: Any) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


def _row_to_insert_params(row: Sequence[Any]) -> tuple[Any, ...]:
    """Map one DuckDB `utxo_lifecycle_full` row into QuestDB insert params."""
    (
        txid,
        vout,
        creation_block,
        creation_timestamp,
        creation_price_usd,
        btc_value,
        realized_value_usd,
        spent_block,
        spent_timestamp,
        spent_price_usd,
        age_blocks,
        age_days,
        cohort,
        sopr,
        is_coinbase,
        is_spent,
    ) = row

    outpoint = f"{txid}:{int(vout)}"
    return (
        outpoint,
        txid,
        int(vout),
        int(creation_block),
        _utc_from_unix_seconds(creation_timestamp),
        float(creation_price_usd) if creation_price_usd is not None else None,
        float(btc_value) if btc_value is not None else None,
        float(realized_value_usd) if realized_value_usd is not None else None,
        int(spent_block) if spent_block is not None else None,
        _utc_from_unix_seconds(spent_timestamp),
        float(spent_price_usd) if spent_price_usd is not None else None,
        None,  # spending_txid is not present in the DuckDB source schema.
        int(age_blocks) if age_blocks is not None else None,
        int(age_days) if age_days is not None else None,
        cohort,
        None,  # sub_cohort is not present in the DuckDB source schema.
        float(sopr) if sopr is not None else None,
        bool(is_coinbase),
        bool(is_spent),
        "utxoracle",
    )


def _open_questdb_connection():
    if psycopg is None:
        raise ModuleNotFoundError(
            "psycopg is required for QuestDB PG-wire mirroring; install project deps"
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


def _questdb_target_count(conn: Any) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count() FROM utxo_lifecycle")
        row = cur.fetchone()
    return int(row[0] if row else 0)


def _load_checkpoint(path: str | Path) -> dict[str, Any] | None:
    checkpoint_path = Path(path)
    if not checkpoint_path.exists():
        return None
    return json.loads(checkpoint_path.read_text(encoding="utf-8"))


def _save_checkpoint(
    path: str | Path,
    *,
    last_block: int,
    mirrored_rows: int,
    start_block: int,
    end_block: int,
) -> None:
    checkpoint_path = Path(path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "last_block": last_block,
            "mirrored_rows": mirrored_rows,
            "start_block": start_block,
            "end_block": end_block,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        indent=2,
    )
    tmp_path = checkpoint_path.with_suffix(checkpoint_path.suffix + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(checkpoint_path)


def _insert_batch(conn: Any, rows: Iterable[Sequence[Any]]) -> int:
    params = [_row_to_insert_params(row) for row in rows]
    if not params:
        return 0
    with conn.cursor() as cur:
        cur.executemany(_INSERT_SQL, params)
    return len(params)


def _count_source_rows(
    conn: duckdb.DuckDBPyConnection, start_block: int, end_block: int
) -> int:
    row = conn.execute(
        """
        SELECT count()
        FROM utxo_lifecycle_full
        WHERE creation_block BETWEEN ? AND ?
        """,
        [start_block, end_block],
    ).fetchone()
    return int(row[0] if row else 0)


def _resolve_end_block(conn: duckdb.DuckDBPyConnection, end_block: int | None) -> int:
    if end_block is not None:
        return end_block
    row = conn.execute("SELECT max(creation_block) FROM utxo_lifecycle_full").fetchone()
    if not row or row[0] is None:
        raise RuntimeError("DuckDB source has no utxo_lifecycle_full rows")
    return int(row[0])


def mirror(
    *,
    duckdb_path: str | Path = UTXORACLE_DB_PATH,
    start_block: int = 1,
    end_block: int | None = None,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    block_batch_size: int = _DEFAULT_BLOCK_BATCH_SIZE,
    dry_run: bool = False,
    allow_nonempty_target: bool = False,
    truncate_target: bool = False,
    resume: bool = False,
    checkpoint_path: str | Path = _DEFAULT_CHECKPOINT_PATH,
) -> MirrorStats:
    """Mirror DuckDB lifecycle rows into QuestDB.

    By default this refuses to write into a non-empty QuestDB target. That
    keeps the bootstrap idempotent enough for operators: an accidental rerun
    fails fast instead of duplicating a 164M-row table.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    if block_batch_size <= 0:
        raise ValueError("block_batch_size must be > 0")

    source = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        resolved_end = _resolve_end_block(source, end_block)
        original_start = start_block
        checkpoint = _load_checkpoint(checkpoint_path) if resume else None
        mirrored = 0
        checkpoint_used = False
        if (
            checkpoint is not None
            and int(checkpoint.get("last_block", 0)) >= start_block
        ):
            checkpoint_end = int(checkpoint.get("end_block", resolved_end))
            if checkpoint_end != resolved_end:
                raise RuntimeError(
                    "checkpoint end_block does not match requested end_block: "
                    f"{checkpoint_end} != {resolved_end}"
                )
            start_block = int(checkpoint["last_block"]) + 1
            mirrored = int(checkpoint.get("mirrored_rows", 0))
            checkpoint_used = True
            logger.info(
                "Resuming mirror from checkpoint %s at block %s",
                checkpoint_path,
                start_block,
            )

        if start_block > resolved_end:
            return MirrorStats(
                source_rows=0,
                mirrored_rows=mirrored,
                start_block=start_block,
                end_block=resolved_end,
                dry_run=dry_run,
                checkpoint_path=str(checkpoint_path) if resume else None,
            )

        remaining_source_rows = _count_source_rows(source, start_block, resolved_end)
        total_source_rows = mirrored + remaining_source_rows

        logger.info(
            "UTXO lifecycle mirror source range %s-%s has %s rows",
            start_block,
            resolved_end,
            f"{remaining_source_rows:,}",
        )
        if dry_run:
            return MirrorStats(
                source_rows=total_source_rows,
                mirrored_rows=0,
                start_block=start_block,
                end_block=resolved_end,
                dry_run=True,
                checkpoint_path=str(checkpoint_path) if resume else None,
            )

        with _open_questdb_connection() as target:
            target_count = _questdb_target_count(target)
            if target_count > 0 and not (
                allow_nonempty_target or truncate_target or checkpoint_used
            ):
                raise RuntimeError(
                    "QuestDB utxo_lifecycle is non-empty "
                    f"({target_count:,} rows); pass --allow-nonempty-target, "
                    "--truncate-target, or --resume with a valid checkpoint "
                    "intentionally"
                )
            if truncate_target:
                with target.cursor() as cur:
                    cur.execute("TRUNCATE TABLE utxo_lifecycle")
                checkpoint_file = Path(checkpoint_path)
                checkpoint_file.unlink(missing_ok=True)
                mirrored = 0

            current_block = start_block
            while current_block <= resolved_end:
                chunk_end = min(current_block + block_batch_size - 1, resolved_end)
                cursor = source.execute(_SELECT_SQL, [current_block, chunk_end])
                while True:
                    rows = cursor.fetchmany(batch_size)
                    if not rows:
                        break
                    mirrored += _insert_batch(target, rows)
                    logger.info(
                        "Mirrored %s/%s rows",
                        f"{mirrored:,}",
                        f"{total_source_rows:,}",
                    )
                _save_checkpoint(
                    checkpoint_path,
                    last_block=chunk_end,
                    mirrored_rows=mirrored,
                    start_block=original_start,
                    end_block=resolved_end,
                )
                current_block = chunk_end + 1

        return MirrorStats(
            source_rows=total_source_rows,
            mirrored_rows=mirrored,
            start_block=start_block,
            end_block=resolved_end,
            dry_run=False,
            checkpoint_path=str(checkpoint_path),
        )
    finally:
        source.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mirror DuckDB utxo_lifecycle_full rows into QuestDB"
    )
    parser.add_argument("--duckdb-path", default=str(UTXORACLE_DB_PATH))
    parser.add_argument("--start-block", type=int, default=1)
    parser.add_argument("--end-block", type=int)
    parser.add_argument("--batch-size", type=int, default=_DEFAULT_BATCH_SIZE)
    parser.add_argument(
        "--block-batch-size", type=int, default=_DEFAULT_BLOCK_BATCH_SIZE
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--checkpoint-path", default=str(_DEFAULT_CHECKPOINT_PATH))
    parser.add_argument("--allow-nonempty-target", action="store_true")
    parser.add_argument(
        "--truncate-target",
        action="store_true",
        help="TRUNCATE QuestDB utxo_lifecycle before mirroring",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    stats = mirror(
        duckdb_path=args.duckdb_path,
        start_block=args.start_block,
        end_block=args.end_block,
        batch_size=args.batch_size,
        block_batch_size=args.block_batch_size,
        dry_run=args.dry_run,
        allow_nonempty_target=args.allow_nonempty_target,
        truncate_target=args.truncate_target,
        resume=args.resume,
        checkpoint_path=args.checkpoint_path,
    )
    logger.info("Mirror complete: %s", stats)


if __name__ == "__main__":
    main()
