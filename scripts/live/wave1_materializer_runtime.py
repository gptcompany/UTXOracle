from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

import duckdb

from scripts.metrics.materialize_wave1 import run_materialization_pass


def _setup_script_logging(name: str) -> logging.Logger:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
    return logging.getLogger(name)


logger = _setup_script_logging("live_wave1_materializer")

DEFAULT_INTERVAL_SECONDS = int(os.getenv("LIVE_WAVE1_INTERVAL_SECONDS", "3600"))
DEFAULT_DUCKDB_PATH = os.getenv("DUCKDB_PATH", "data/utxoracle.duckdb")


def _configure_live_questdb_defaults() -> None:
    os.environ.setdefault("QUESTDB_PG_HOST", "127.0.0.1")
    os.environ.setdefault("QUESTDB_PG_PORT", "9912")
    os.environ.setdefault("QUESTDB_ILP_HOST", "127.0.0.1")
    os.environ.setdefault("QUESTDB_ILP_PORT", "9909")
    os.environ.setdefault("QUESTDB_HTTP_HOST", "127.0.0.1")
    os.environ.setdefault("QUESTDB_HTTP_PORT", "9900")


async def _run_once() -> bool:
    started_at = datetime.now(timezone.utc)
    conn = duckdb.connect(DEFAULT_DUCKDB_PATH, read_only=True)
    try:
        ok = await run_materialization_pass(conn, started_at)
        if ok:
            logger.info(
                "Wave 1 live materialization pass completed for %s",
                started_at.isoformat(),
            )
        else:
            logger.error(
                "Wave 1 live materialization pass failed for %s",
                started_at.isoformat(),
            )
        return ok
    finally:
        conn.close()


async def main() -> None:
    _configure_live_questdb_defaults()
    interval_seconds = max(DEFAULT_INTERVAL_SECONDS, 300)

    if not os.path.exists(DEFAULT_DUCKDB_PATH):
        raise FileNotFoundError(f"DuckDB database not found at {DEFAULT_DUCKDB_PATH}")

    while True:
        try:
            await _run_once()
        except Exception as exc:
            logger.exception("Unhandled Wave 1 live materializer failure: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
