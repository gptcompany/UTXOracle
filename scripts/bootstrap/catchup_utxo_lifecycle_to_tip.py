#!/usr/bin/env python3
"""Catch up UTXO lifecycle creations before spent-state backfill.

This is the creation-side companion to spec-061 T036. The spent backfill
only updates rows already present in QuestDB; it cannot insert UTXOs created
after the DuckDB snapshot. This script:

1. verifies the initial DuckDB -> QuestDB mirror is complete,
2. syncs DuckDB `utxo_lifecycle` from its current creation tip to Bitcoin tip,
3. mirrors those newly created rows into QuestDB.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import duckdb

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None  # type: ignore[assignment]

from scripts.bootstrap.mirror_utxo_lifecycle_to_questdb import mirror
from scripts.config import UTXORACLE_DB_PATH

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LifecycleState:
    count: int
    max_creation_block: int | None


@dataclass(frozen=True)
class CatchupStats:
    start_block: int
    end_block: int
    dry_run: bool
    sync_result: dict[str, Any] | None
    mirrored_rows: int


def _duckdb_state(duckdb_path: str | Path = UTXORACLE_DB_PATH) -> LifecycleState:
    conn = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        row = conn.execute(
            "SELECT count(), max(creation_block) FROM utxo_lifecycle_full"
        ).fetchone()
        if row is None:
            return LifecycleState(count=0, max_creation_block=None)
        return LifecycleState(
            count=int(row[0]),
            max_creation_block=int(row[1]) if row[1] is not None else None,
        )
    finally:
        conn.close()


def _questdb_connection():
    if psycopg is None:
        raise ModuleNotFoundError(
            "psycopg is required for QuestDB PG-wire access; install project deps"
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


def _questdb_state() -> LifecycleState:
    with _questdb_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(), max(creation_block) FROM utxo_lifecycle")
            row = cur.fetchone()
    return LifecycleState(
        count=int(row[0] if row else 0),
        max_creation_block=int(row[1]) if row and row[1] is not None else None,
    )


def _bitcoin_tip() -> int:
    from scripts.sync_utxo_lifecycle import get_current_block_height

    return int(get_current_block_height())


def _assert_initial_mirror_complete(
    *, duckdb_state: LifecycleState, questdb_state: LifecycleState
) -> None:
    if questdb_state.max_creation_block is None:
        raise RuntimeError("QuestDB utxo_lifecycle is empty; run T036a mirror first")
    if questdb_state.count < duckdb_state.count:
        raise RuntimeError(
            "QuestDB initial mirror is incomplete: "
            f"{questdb_state.count:,}/{duckdb_state.count:,} rows"
        )
    if (
        duckdb_state.max_creation_block is not None
        and questdb_state.max_creation_block < duckdb_state.max_creation_block
    ):
        raise RuntimeError(
            "QuestDB initial mirror creation tip is behind DuckDB: "
            f"{questdb_state.max_creation_block} < {duckdb_state.max_creation_block}"
        )


def catchup(
    *,
    duckdb_path: str | Path = UTXORACLE_DB_PATH,
    start_block: int | None = None,
    end_block: int | None = None,
    source: str = "rpc-v3",
    workers: int = 4,
    dry_run: bool = False,
) -> CatchupStats:
    """Sync DuckDB creations to tip and mirror the new creation range to QuestDB."""
    before_duckdb = _duckdb_state(duckdb_path)
    before_questdb = _questdb_state()
    _assert_initial_mirror_complete(
        duckdb_state=before_duckdb, questdb_state=before_questdb
    )

    resolved_start = (
        start_block
        if start_block is not None
        else int(before_duckdb.max_creation_block or 0) + 1
    )
    resolved_end = end_block if end_block is not None else _bitcoin_tip()

    if resolved_start > resolved_end:
        return CatchupStats(
            start_block=resolved_start,
            end_block=resolved_end,
            dry_run=dry_run,
            sync_result={"status": "up_to_date"},
            mirrored_rows=0,
        )

    logger.info("Creation catch-up range: blocks %s-%s", resolved_start, resolved_end)
    if dry_run:
        return CatchupStats(
            start_block=resolved_start,
            end_block=resolved_end,
            dry_run=True,
            sync_result=None,
            mirrored_rows=0,
        )

    sync_module = cast(Any, importlib.import_module("scripts.sync_utxo_lifecycle"))
    previous_utxo_path = sync_module.UTXO_DB_PATH
    previous_main_path = sync_module.MAIN_DB_PATH
    sync_module.UTXO_DB_PATH = str(duckdb_path)
    if previous_main_path == previous_utxo_path:
        sync_module.MAIN_DB_PATH = str(duckdb_path)
    try:
        sync_result = sync_module.run_sync(
            start_block=resolved_start,
            end_block=resolved_end,
            source=source,
            workers=workers,
            prune=False,
        )
    finally:
        sync_module.UTXO_DB_PATH = previous_utxo_path
        sync_module.MAIN_DB_PATH = previous_main_path

    mirror_stats = mirror(
        duckdb_path=duckdb_path,
        start_block=resolved_start,
        end_block=resolved_end,
        allow_nonempty_target=True,
        resume=True,
        checkpoint_path="data/questdb_utxo_lifecycle_creation_catchup_checkpoint.json",
    )
    return CatchupStats(
        start_block=resolved_start,
        end_block=resolved_end,
        dry_run=False,
        sync_result=sync_result,
        mirrored_rows=mirror_stats.mirrored_rows,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Catch up UTXO lifecycle creations and mirror them to QuestDB"
    )
    parser.add_argument("--duckdb-path", default=str(UTXORACLE_DB_PATH))
    parser.add_argument("--start-block", type=int)
    parser.add_argument("--end-block", type=int)
    parser.add_argument(
        "--source", default="rpc-v3", choices=["rpc-v3", "electrs", "rpc"]
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    stats = catchup(
        duckdb_path=args.duckdb_path,
        start_block=args.start_block,
        end_block=args.end_block,
        source=args.source,
        workers=args.workers,
        dry_run=args.dry_run,
    )
    logger.info("Creation catch-up complete: %s", stats)


if __name__ == "__main__":
    main()
