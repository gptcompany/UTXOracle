"""
Repository for interacting with QuestDB.
"""

import asyncio
import fcntl
import inspect
import logging
import sys
import weakref
import threading
import time
import json
import os
import re
from pathlib import Path
from api.models.data import WhaleTransaction, NetFlowMetrics, Alert
from scripts.models.metrics_models import (
    WalletWavesResult,
    AbsorptionRatesResult,
    AddressCohortsResult,
)
from typing import TYPE_CHECKING, Optional, List, Dict, Any, Union
from datetime import datetime, timedelta, timezone

if TYPE_CHECKING:
    from scripts.models.metrics_models import CostBasisResult, URPDFeaturesResult

try:
    import asyncpg
except ModuleNotFoundError:  # pragma: no cover - exercised indirectly in test envs
    asyncpg = None  # type: ignore[assignment]

try:
    from questdb.ingress import Sender
except ModuleNotFoundError:  # pragma: no cover - exercised indirectly in test envs
    Sender = None  # type: ignore[assignment]

AsyncpgPool = Any
AsyncpgRecord = Any

logger = logging.getLogger(__name__)

# Indirections so tests can drive a fake clock without really waiting.
_monotonic = time.monotonic
_sleep = asyncio.sleep

# address_clusters is swapped in by RENAME (F-424): for the few ms between the two RENAMEs
# a read finds the table absent. Readers retry a short, bounded number of times on that
# error only; any other error, or a persistent absence, still fails the read.
ADDRESS_CLUSTERS_READ_ATTEMPTS = 3
ADDRESS_CLUSTERS_READ_RETRY_PAUSE_S = 0.3


async def fetch_address_clusters(repo, query: str, *args):
    """repo.fetch with the short retry on "table does not exist" (see above)."""
    for attempt in range(1, ADDRESS_CLUSTERS_READ_ATTEMPTS + 1):
        try:
            return await repo.fetch(query, *args)
        except Exception as exc:
            if (
                "does not exist" not in str(exc)
                or attempt == ADDRESS_CLUSTERS_READ_ATTEMPTS
            ):
                raise
            logger.warning(
                "address_clusters absent (refresh swap in progress), retry %d/%d",
                attempt,
                ADDRESS_CLUSTERS_READ_ATTEMPTS - 1,
            )
            await _sleep(ADDRESS_CLUSTERS_READ_RETRY_PAUSE_S)


# QuestDB connection details from environment variables
QUESTDB_ILP_HOST = os.getenv("QUESTDB_ILP_HOST", "localhost")
QUESTDB_ILP_PORT = int(os.getenv("QUESTDB_ILP_PORT", 9009))
QUESTDB_PG_HOST = os.getenv("QUESTDB_PG_HOST", "localhost")
QUESTDB_PG_PORT = int(os.getenv("QUESTDB_PG_PORT", 8812))
QUESTDB_HTTP_HOST = os.getenv("QUESTDB_HTTP_HOST", "localhost")
QUESTDB_HTTP_PORT = int(os.getenv("QUESTDB_HTTP_PORT", 9000))
QUESTDB_PG_USER = os.getenv("QUESTDB_PG_USER", "admin")
QUESTDB_PG_PASSWORD = os.getenv("QUESTDB_PG_PASSWORD", "quest")
QUESTDB_PG_DATABASE = os.getenv("QUESTDB_PG_DATABASE", "main")

ADDRESS_CLUSTERS_TABLE = "address_clusters"
ADDRESS_CLUSTERS_STAGING_TABLE = "address_clusters_staging"
# Ceiling on the wait for WAL to apply the staged rows: max(MIN_WAIT, rows / MIN_APPLY_RATE).
# The full sync (scripts/bootstrap/sync_clusters_to_questdb.py) reads about 55M rows
# (specs/037-database-consolidation/spec.md), so 3.8k rows/s gives ~4 h for the full sync;
# the CSV ingest (tens of thousands of rows) gets the 10 min floor.
ADDRESS_CLUSTERS_MIN_APPLY_ROWS_PER_S = 3800.0
# Operator procedure shown when the staging table is not WAL (no automatic migration).
ADDRESS_CLUSTERS_NOT_WAL_HINT = (
    "DROP TABLE address_clusters_staging (it is empty outside a refresh and is "
    "recreated as WAL at the next start); or ALTER TABLE address_clusters_staging "
    "SET TYPE WAL followed by a QuestDB restart"
)
ADDRESS_CLUSTERS_MIN_WAIT_S = 600.0
# Rows per confirmed HTTP flush of the staging load (auto_flush is off).
ADDRESS_CLUSTERS_FLUSH_ROWS = 5000
# One INFO line per poll: 5 s keeps a 4 h wait to ~2.9k lines at worst, while a
# normal small ingest is done within one or two polls.
ADDRESS_CLUSTERS_POLL_S = 5.0
# Name and type of every column the staging table must have to become the live table.
ADDRESS_CLUSTERS_SCHEMA = [
    ("address", "STRING"),
    ("cluster_id", "STRING"),
    ("ts", "TIMESTAMP"),
    ("last_seen", "TIMESTAMP"),
    ("is_exchange_likely", "BOOLEAN"),
    ("label", "SYMBOL"),
    ("confidence", "DOUBLE"),
]
ADDRESS_CLUSTERS_STAGING_DDL = f"""
    CREATE TABLE IF NOT EXISTS {ADDRESS_CLUSTERS_STAGING_TABLE} (
        address STRING,
        cluster_id STRING,
        ts TIMESTAMP,
        last_seen TIMESTAMP,
        is_exchange_likely BOOLEAN,
        label SYMBOL,
        confidence DOUBLE
    ) timestamp(ts) PARTITION BY YEAR WAL
"""


class ConcurrentRefreshError(RuntimeError):
    """Another process holds the address_clusters refresh lock."""


class OldCopyCleanupError(RuntimeError):
    """The swap succeeded but dropping older _old copies failed (exit code 5)."""

    def __init__(self, names: list[str]):
        super().__init__(
            f"swap ok, cleanup failed; _old copies left: {', '.join(names)}"
        )
        self.names = names


class RefreshLockError(RuntimeError):
    """A refresh mutation was called without the live lock token."""


class AddressClustersLostError(RuntimeError):
    """The refresh state is lost or unobservable (exit code 6): no live table and no _old
    copy after a swap, or the tables could not be observed or restored, at any moment."""


class RefreshLock:
    """Token of the host-local flock that serialises address_clusters refreshes.

    Acquired in ONE place, QuestDBRepository.refresh_address_clusters (which every
    caller, sync_clusters and save_address_clusters_bulk included, goes through), and held
    from before the first mutation to commit or abort. prepare, commit and abort require
    the live token. No reentrancy: a second acquire, in this process or another, is
    refused with ERROR `concurrent_refresh`.

    Path: $ADDRESS_CLUSTERS_LOCK_DIR/address_clusters.lock, default
    <project>/data/locks/address_clusters.lock. `data/` is the directory the compose
    services (data-updater included) bind-mount at /app/data, so host and containers
    lock the same inode.
    """

    def __init__(self, fd: int, path: Path):
        self._fd: Optional[int] = fd
        self.path = path

    @classmethod
    def acquire(cls) -> "RefreshLock":
        lock_dir = Path(
            os.getenv("ADDRESS_CLUSTERS_LOCK_DIR")
            or Path(__file__).resolve().parent.parent / "data" / "locks"
        )
        lock_dir.mkdir(parents=True, exist_ok=True)
        path = lock_dir / "address_clusters.lock"
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            logger.error(
                "address_clusters refresh refused (concurrent_refresh): %s is locked "
                "by another holder",
                path,
            )
            raise ConcurrentRefreshError(str(path))
        return cls(fd, path)

    @property
    def alive(self) -> bool:
        return self._fd is not None

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)  # closing the descriptor releases the flock
            self._fd = None


def _require_lock(token: Any) -> None:
    if not isinstance(token, RefreshLock) or not token.alive:
        raise RefreshLockError(
            "address_clusters refresh mutations need the live RefreshLock "
            "(go through QuestDBRepository.refresh_address_clusters)"
        )


def _swallow_if_in_flight(what: str, error: BaseException, in_flight) -> None:
    """Called from an except block: a cleanup error never replaces the primary error. It
    is re-raised only when no other exception is in flight; otherwise it is logged."""
    if in_flight is None:
        raise error
    logger.error(
        "Closing %s failed while another error is in flight (kept as primary): %s",
        what,
        error,
    )


async def close_safely(closer, what: str) -> None:
    """Run a cleanup (sync or async callable) on the way out of a refresh step. If an
    exception is already in flight, a failure of the cleanup is logged at ERROR and not
    raised, so the primary error (and its exit classification) survives."""
    in_flight = sys.exc_info()[1]
    try:
        result = closer()
        if inspect.isawaitable(result):
            await result
    except (Exception, asyncio.CancelledError) as e:
        # CancelledError is a BaseException: without this it would replace the primary
        # error and bypass the exit classification (R12). KeyboardInterrupt/SystemExit
        # are deliberately left alone.
        _swallow_if_in_flight(what, e, in_flight)


async def close_all(closers) -> list[BaseException]:
    """Run EVERY (closer, what) pair, sync or async, after the outcome is already decided
    (never inside a try/finally of the caller). Each failure is logged at ERROR; the list
    of errors is returned and nothing is ever raised, so a cleanup can neither skip the
    next closer nor change an exit classification already taken."""
    errors: list[BaseException] = []
    for closer, what in closers:
        try:
            result = closer()
            if inspect.isawaitable(result):
                await result
        except (Exception, asyncio.CancelledError) as e:
            logger.error("Closing %s failed: %s", what, e)
            errors.append(e)
    return errors


def refresh_exit_status(exc: BaseException) -> Optional[tuple[int, str]]:
    """Exit code and message for a refresh failure, decided on the WHOLE exception chain
    (__cause__ and __context__, cycle-safe): an AddressClustersLostError anywhere in it is
    exit 6 with its own manual command, whatever exception reached the top. Else 5 for an
    OldCopyCleanupError, 1 for a concurrent refresh, None for anything else."""
    seen: set[int] = set()
    stack: list[Optional[BaseException]] = [exc]
    while stack:
        current = stack.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, AddressClustersLostError):
            return 6, str(current)
        stack.extend((current.__cause__, current.__context__))
    if isinstance(exc, OldCopyCleanupError):
        return 5, str(exc)
    if isinstance(exc, ConcurrentRefreshError):
        return 1, f"another address_clusters refresh holds the lock: {exc}"
    return None


ADDRESS_CLUSTERS_REBUILD_COMMAND = (
    "rebuild it with `uv run python -m scripts.bootstrap.sync_clusters_to_questdb`"
)
_OLD_COPY_RE = re.compile(r"^address_clusters_old_[0-9]{8}T[0-9]{6}Z$")


QUESTDB_POOL_MIN_SIZE = int(os.getenv("QUESTDB_POOL_MIN_SIZE", "5"))
QUESTDB_POOL_MAX_SIZE = int(os.getenv("QUESTDB_POOL_MAX_SIZE", "20"))
QUESTDB_COMMAND_TIMEOUT = int(os.getenv("QUESTDB_COMMAND_TIMEOUT", "30"))
QUESTDB_MAX_INACTIVE_LIFETIME = int(os.getenv("QUESTDB_MAX_INACTIVE_LIFETIME", "300"))


# Defense-in-depth: identifiers in the freshness probes come from the registry
# YAML (already validated against `stream_registry.schema.yaml` pattern
# `^[a-z][a-z0-9_]*$`), but we re-check here so a misconfigured loader cannot
# inject SQL via table or column names.
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _validate_identifier(name: str, kind: str) -> str:
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"invalid {kind} identifier: {name!r}")
    return name


async def _fetch_stream_probe_value(query: str):
    """Run a scalar freshness probe using the shared PG pool when available."""
    if asyncpg is None:
        raise ModuleNotFoundError(
            "asyncpg is required for stream freshness probes; install project deps"
        )

    if QuestDBRepository._pool is not None:
        async with QuestDBRepository._pool.acquire() as conn:
            return await conn.fetchval(query)

    conn = await asyncpg.connect(
        host=QUESTDB_PG_HOST,
        port=QUESTDB_PG_PORT,
        user=QUESTDB_PG_USER,
        password=QUESTDB_PG_PASSWORD,
        database=QUESTDB_PG_DATABASE,
    )
    try:
        return await conn.fetchval(query)
    finally:
        await conn.close()


async def read_stream_max_ts(table: str, timestamp_column: str) -> Optional[datetime]:
    """Return `max(timestamp_column)` from `table`, or None if the table is empty.

    Used by the freshness endpoint (spec-061 FR-003) for streams whose
    registry entry declares `freshness_strategy: max_ts`. Raises on
    backend failure; the caller maps that to status `MISSING` with an
    `error` field.
    """
    if asyncpg is None:
        raise ModuleNotFoundError(
            "asyncpg is required for read_stream_max_ts; install project deps"
        )
    _validate_identifier(table, "table")
    _validate_identifier(timestamp_column, "timestamp_column")
    return await _fetch_stream_probe_value(
        f"SELECT max({timestamp_column}) FROM {table}"
    )


async def read_stream_tip_lag_seconds(
    table: str, block_column: str, current_tip: int
) -> Optional[int]:
    """Return `(current_tip - max(block_column)) * 600` from `table`, or None if empty.

    Used by streams whose registry entry declares
    `freshness_strategy: tip_lag_blocks` - currently only `utxo_lifecycle_full`,
    where the row's `ts` is creation-time and `max(ts)` would falsely report
    `OK` during a backfill. Block lag is the authoritative freshness signal.
    Raises on backend failure; caller maps to MISSING with `error`.
    """
    if asyncpg is None:
        raise ModuleNotFoundError(
            "asyncpg is required for read_stream_tip_lag_seconds; install project deps"
        )
    _validate_identifier(table, "table")
    _validate_identifier(block_column, "block_column")
    max_block = await _fetch_stream_probe_value(
        f"SELECT max({block_column}) FROM {table}"
    )
    if max_block is None:
        return None
    return (int(current_tip) - int(max_block)) * 600


# spec-061 T022: synchronous save methods for the daily aggregator.
# The producer (`scripts/metrics/calculate_daily_metrics.py::persist_metrics`)
# runs in sync context, so we use psycopg over the QuestDB PG-wire port
# rather than asyncpg. Failure isolation is the caller's job (R5 strangler-fig);
# these functions raise on backend errors and return True/False on logical
# outcomes. Tables MUST exist before calling (create_tables_if_not_exist).

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None  # type: ignore[assignment]


def _open_pg_sync():
    """Open a one-shot synchronous psycopg connection to QuestDB."""
    if psycopg is None:
        raise ModuleNotFoundError(
            "psycopg is required for sync daily-aggregator saves; install project deps"
        )
    return psycopg.connect(
        host=QUESTDB_PG_HOST,
        port=QUESTDB_PG_PORT,
        user=QUESTDB_PG_USER,
        password=QUESTDB_PG_PASSWORD,
        dbname=QUESTDB_PG_DATABASE,
        autocommit=True,
    )


def save_mvrv_daily(
    ts: datetime,
    mvrv: float,
    mvrv_z: Optional[float] = None,
    mvrv_z_rbn: Optional[float] = None,
    market_cap: Optional[float] = None,
    realized_cap: Optional[float] = None,
) -> bool:
    """Persist one row to QuestDB mvrv_daily. Idempotent per FR-010 + DEDUP."""

    def insert_row(cur):
        cur.execute(
            """
            INSERT INTO mvrv_daily (ts, mvrv, mvrv_z, mvrv_z_rbn,
                                    market_cap, realized_cap, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (ts, mvrv, mvrv_z, mvrv_z_rbn, market_cap, realized_cap, ts),
        )

    with _open_pg_sync() as conn:
        with conn.cursor() as cur:
            try:
                insert_row(cur)
            except Exception as exc:
                try:
                    cur.execute(
                        "ALTER TABLE mvrv_daily ADD COLUMN mvrv_z_rbn DOUBLE",
                        (),
                    )
                except Exception:
                    raise exc
                insert_row(cur)
    return True


def save_nupl_daily(
    ts: datetime,
    nupl: float,
    market_cap: Optional[float] = None,
    realized_cap: Optional[float] = None,
    unrealized_profit: Optional[float] = None,
    unrealized_loss: Optional[float] = None,
) -> bool:
    """Persist one row to QuestDB nupl_daily. Idempotent per FR-010 + DEDUP."""
    with _open_pg_sync() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO nupl_daily (ts, nupl, market_cap, realized_cap,
                                        unrealized_profit, unrealized_loss, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    ts,
                    nupl,
                    market_cap,
                    realized_cap,
                    unrealized_profit,
                    unrealized_loss,
                    ts,
                ),
            )
    return True


def save_realized_cap_daily(
    ts: datetime,
    realized_cap: float,
    total_supply: Optional[float] = None,
) -> bool:
    """Persist one row to QuestDB realized_cap_daily. Idempotent per FR-010 + DEDUP."""
    with _open_pg_sync() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO realized_cap_daily (ts, realized_cap, total_supply, created_at)
                VALUES (%s, %s, %s, %s)
                """,
                (ts, realized_cap, total_supply, ts),
            )
    return True


def save_backtest_whale_signal_row(
    ts: datetime,
    net_flow_btc: Optional[float] = None,
    confidence: Optional[float] = None,
    btc_price: Optional[float] = None,
    inflow_btc: Optional[float] = None,
    outflow_btc: Optional[float] = None,
    tx_count_relevant: Optional[int] = None,
) -> bool:
    """Persist one row to QuestDB backtest_whale_signals (T026a mirror target).

    Used by scripts/metrics/mirror_backtest_whale_signals.py to bridge the
    DuckDB producer to the consumer-visible QuestDB surface. Idempotent
    per FR-010 + DEDUP UPSERT KEYS(ts).
    """
    with _open_pg_sync() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO backtest_whale_signals (ts, net_flow_btc, confidence, btc_price,
                                                    inflow_btc, outflow_btc, tx_count_relevant, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    ts,
                    net_flow_btc,
                    confidence,
                    btc_price,
                    inflow_btc,
                    outflow_btc,
                    tx_count_relevant,
                    ts,
                ),
            )
    return True


_TABLE_STATE_QUERY = "SELECT walEnabled, dedup FROM tables() WHERE table_name = $1"


async def read_table_states(tables) -> dict:
    """tables() state (walEnabled, dedup) of each table, None when it does not exist.

    Read on a connection of its own, closed on return: QuestDB 7.x breaks a connection that
    runs a DDL after an extended-protocol query (asyncpg: 'NoneType' has no attribute
    'decode'), so the DDL connection must never run a fetch.
    """
    if asyncpg is None:
        raise ModuleNotFoundError(
            "asyncpg package is required to read tables(); install project dependencies"
        )
    conn = await asyncpg.connect(
        host=QUESTDB_PG_HOST,
        port=QUESTDB_PG_PORT,
        user=QUESTDB_PG_USER,
        password=QUESTDB_PG_PASSWORD,
        database=QUESTDB_PG_DATABASE,
    )
    try:
        return {t: await conn.fetchrow(_TABLE_STATE_QUERY, t) for t in tables}
    finally:
        await conn.close()


async def read_table_columns(table: str) -> set[str]:
    """Column names of `table`, read on a connection of its own (see read_table_states).

    `table` is spliced into table_columns('...'): it must be a plain identifier.
    """
    if asyncpg is None:
        raise ModuleNotFoundError(
            "asyncpg package is required to read table_columns(); install project dependencies"
        )
    if not table.isidentifier():
        raise ValueError(f"not a table identifier: {table!r}")
    conn = await asyncpg.connect(
        host=QUESTDB_PG_HOST,
        port=QUESTDB_PG_PORT,
        user=QUESTDB_PG_USER,
        password=QUESTDB_PG_PASSWORD,
        database=QUESTDB_PG_DATABASE,
    )
    try:
        rows = await conn.fetch(f"SELECT \"column\" FROM table_columns('{table}')")
        return {row["column"] for row in rows}
    finally:
        await conn.close()


async def _enable_daily_dedup(conn, table: str) -> None:
    """Enable DEDUP UPSERT KEYS(ts) on `table` when the state reported by tables() allows it.

    The decision is taken from the walEnabled and dedup columns, never from an error text;
    `conn` is the DDL connection and only executes the ALTER (simple protocol):
    - dedup already on: INFO, nothing else;
    - WAL without dedup: ALTER ... DEDUP ENABLE; a failure is fatal, because without dedup
      the daily rerun would duplicate its row;
    - not WAL: no schema conversion (that is not a service-startup step); ERROR with the
      table name and startup goes on. The daily job itself refuses to write to a table
      without dedup (tables_without_dedup), so the error stays visible.
    """
    row = (await read_table_states([table]))[table]
    if row is None:
        return  # created just before by the caller with dedup; nothing to migrate
    if row["dedup"]:
        logger.info("%s: dedup already active, no change", table)
    elif row["walEnabled"]:
        ddl = f"ALTER TABLE {table} DEDUP ENABLE UPSERT KEYS(ts)"
        try:
            await conn.execute(ddl)
        except Exception as exc:
            logger.error("%s: %s failed: %s", table, ddl, exc)
            raise
        logger.info("%s: dedup enabled on ts", table)
    else:
        logger.error("%s: dedup non attivabile: tabella non WAL", table)


async def tables_without_dedup(tables) -> list[str]:
    """Names among `tables` that do not exist or are not deduplicating (read from tables())."""
    states = await read_table_states(tables)
    return [t for t in tables if states[t] is None or not states[t]["dedup"]]


async def tables_with_day_row(tables, day: datetime) -> list[str]:
    """Names among `tables` that already hold a row whose ts is exactly `day` (read-only).

    `day` is a UTC midnight built by the caller, so it is rendered into the query as a
    literal: the connection stays on one-shot reads and takes no bind parameters.
    """
    if asyncpg is None:
        raise ModuleNotFoundError(
            "asyncpg package is required to read QuestDB; install project dependencies"
        )
    literal = day.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    conn = await asyncpg.connect(
        host=QUESTDB_PG_HOST,
        port=QUESTDB_PG_PORT,
        user=QUESTDB_PG_USER,
        password=QUESTDB_PG_PASSWORD,
        database=QUESTDB_PG_DATABASE,
    )
    try:
        found = []
        for table in tables:
            count = await conn.fetchval(
                f"SELECT count() FROM {table} WHERE ts = '{literal}'"
            )
            if count:
                found.append(table)
        return found
    finally:
        await conn.close()


async def create_tables_if_not_exist():
    """
    Creates the necessary tables in QuestDB if they do not already exist.
    """
    if asyncpg is None:
        raise ModuleNotFoundError(
            "asyncpg package is required for QuestDB schema initialization; install project dependencies"
        )
    conn = None
    try:
        conn = await asyncpg.connect(
            host=QUESTDB_PG_HOST,
            port=QUESTDB_PG_PORT,
            user=QUESTDB_PG_USER,
            password=QUESTDB_PG_PASSWORD,
            database=QUESTDB_PG_DATABASE,
        )

        # Whale and Mempool Tables
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS whale_transactions (
                transaction_id SYMBOL,
                block_height LONG,
                ts TIMESTAMP,
                amount_btc DOUBLE,
                amount_usd DOUBLE,
                direction SYMBOL,
                urgency_score DOUBLE,
                fee_rate DOUBLE,
                confidence DOUBLE,
                is_mempool BOOLEAN,
                detected_at TIMESTAMP
            ) timestamp(ts) PARTITION BY DAY;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS net_flow_metrics (
                period_start TIMESTAMP,
                period_end TIMESTAMP,
                interval SYMBOL,
                net_flow_btc DOUBLE,
                net_flow_usd DOUBLE,
                total_buy_btc DOUBLE,
                total_sell_btc DOUBLE,
                transaction_count LONG,
                direction SYMBOL,
                strength DOUBLE,
                largest_tx_btc DOUBLE,
                ts TIMESTAMP
            ) timestamp(ts) PARTITION BY DAY;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                alert_id SYMBOL,
                transaction_id SYMBOL,
                severity SYMBOL,
                trigger_type SYMBOL,
                threshold_value DOUBLE,
                title STRING,
                message STRING,
                amount_btc DOUBLE,
                amount_usd DOUBLE,
                direction SYMBOL,
                acknowledged BOOLEAN,
                acknowledged_at TIMESTAMP,
                ts TIMESTAMP
            ) timestamp(ts) PARTITION BY DAY;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_analysis (
                ts TIMESTAMP,
                exchange_price DOUBLE,
                utxoracle_price DOUBLE,
                price_difference DOUBLE,
                avg_pct_diff DOUBLE,
                confidence DOUBLE,
                tx_count LONG,
                fetch_tier LONG,
                is_valid BOOLEAN,
                window_end_ts TIMESTAMP,
                created_at TIMESTAMP
            ) timestamp(ts) PARTITION BY DAY WAL
              DEDUP UPSERT KEYS(ts);
            """
        )

        # F-438: explicit end of the analysed window [ts, window_end_ts); additive, no rewrite.
        # ADD COLUMN IF NOT EXISTS of an existing column is a no-op that QuestDB (WAL tables)
        # rejects, so the columns are read first and the ALTER runs only when it is missing.
        # A failing ALTER is not caught here: create_tables_if_not_exist logs it and raises.
        if "window_end_ts" not in await read_table_columns("price_analysis"):
            await conn.execute(
                "ALTER TABLE price_analysis ADD COLUMN window_end_ts TIMESTAMP"
            )

        # Migration for T140: Add fetch_tier column if it doesn't exist
        try:
            await conn.execute("ALTER TABLE price_analysis ADD COLUMN fetch_tier LONG")
        except Exception:
            pass  # Already exists or table doesn't exist yet

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mempool_predictions (
                prediction_id SYMBOL,
                transaction_id SYMBOL,
                flow_type SYMBOL,
                btc_value DOUBLE,
                fee_rate DOUBLE,
                urgency_score DOUBLE,
                rbf_enabled BOOLEAN,
                ts TIMESTAMP,
                predicted_confirmation_block LONG,
                exchange_addresses STRING,
                confidence_score DOUBLE,
                was_modified BOOLEAN,
                created_at TIMESTAMP
            ) timestamp(ts) PARTITION BY DAY;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prediction_outcomes (
                outcome_id SYMBOL,
                prediction_id SYMBOL,
                transaction_id SYMBOL,
                predicted_flow SYMBOL,
                actual_outcome SYMBOL,
                confirmation_time TIMESTAMP,
                confirmation_block LONG,
                accuracy_score DOUBLE,
                time_to_confirmation LONG,
                final_fee_rate DOUBLE,
                ts TIMESTAMP
            ) timestamp(ts) PARTITION BY DAY;
            """
        )

        # UTXO Lifecycle and Core Tables
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS utxo_lifecycle (
                outpoint STRING,
                txid STRING,
                vout_index LONG,
                creation_block LONG,
                ts TIMESTAMP,
                creation_price_usd DOUBLE,
                btc_value DOUBLE,
                realized_value_usd DOUBLE,
                spent_block LONG,
                spent_timestamp TIMESTAMP,
                spent_price_usd DOUBLE,
                spending_txid STRING,
                age_blocks LONG,
                age_days LONG,
                cohort SYMBOL,
                sub_cohort SYMBOL,
                sopr DOUBLE,
                is_coinbase BOOLEAN,
                is_spent BOOLEAN,
                price_source SYMBOL
            ) timestamp(ts) PARTITION BY MONTH;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS utxo_sync_state (
                id LONG,
                last_processed_block LONG,
                ts TIMESTAMP,
                total_utxos_created LONG,
                total_utxos_spent LONG,
                sync_started TIMESTAMP,
                sync_duration_seconds DOUBLE
            ) timestamp(ts) PARTITION BY YEAR;
            """
        )

        # Phase 1.5-v2 source freshness tables. These replace the deprecated
        # DuckDB production refresh path for block timestamps and daily prices.
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS block_heights (
                height LONG,
                ts TIMESTAMP,
                fetched_at TIMESTAMP
            ) timestamp(ts) PARTITION BY YEAR WAL
              DEDUP UPSERT KEYS(ts, height);
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_prices (
                date TIMESTAMP,
                price_usd DOUBLE,
                source SYMBOL,
                fetched_at TIMESTAMP
            ) timestamp(date) PARTITION BY YEAR WAL
              DEDUP UPSERT KEYS(date);
            """
        )

        for table_name, dedup_keys in (
            ("block_heights", "ts, height"),
            ("daily_prices", "date"),
        ):
            for ddl in (
                f"ALTER TABLE {table_name} SET TYPE WAL",
                f"ALTER TABLE {table_name} DEDUP ENABLE UPSERT KEYS({dedup_keys})",
            ):
                try:
                    await conn.execute(ddl)
                except Exception:
                    pass

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS utxo_snapshots (
                block_height LONG,
                ts TIMESTAMP,
                total_supply_btc DOUBLE,
                sth_supply_btc DOUBLE,
                lth_supply_btc DOUBLE,
                realized_cap_usd DOUBLE,
                market_cap_usd DOUBLE,
                mvrv DOUBLE,
                nupl DOUBLE,
                hodl_waves_json STRING
            ) timestamp(ts) PARTITION BY MONTH;
            """
        )

        # On-Chain Metrics Tables
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS btc_feature_bundles (
                bundle_id SYMBOL,
                sequence_id LONG,
                produced_at TIMESTAMP,
                bundle_status SYMBOL,
                degraded_reasons STRING,
                payload_json STRING,
                ts TIMESTAMP
            ) timestamp(ts) PARTITION BY DAY;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS btc_signal_snapshots (
                schema_version SYMBOL,
                sequence_id LONG,
                produced_at TIMESTAMP,
                service_status SYMBOL,
                payload_json STRING,
                ts TIMESTAMP
            ) timestamp(ts) PARTITION BY DAY;
            """
        )

        # Entity Intelligence Tables (spec-053)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entity_registry_serving (
                entity_id SYMBOL INDEX,
                entity_kind SYMBOL,
                registry_status SYMBOL,
                display_label SYMBOL,
                cluster_confidence DOUBLE,
                mapping_confidence DOUBLE,
                label_confidence DOUBLE,
                confidence_overall DOUBLE,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                source_status SYMBOL,
                ts TIMESTAMP
            ) timestamp(ts) PARTITION BY DAY;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entity_provenance_serving (
                entity_id SYMBOL INDEX,
                primary_source_kind SYMBOL,
                review_status SYMBOL,
                provenance_summary_json STRING,
                ts TIMESTAMP
            ) timestamp(ts) PARTITION BY DAY;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entity_flows_daily (
                entity_id SYMBOL INDEX,
                date TIMESTAMP,
                inflow_btc DOUBLE,
                outflow_btc DOUBLE,
                netflow_btc DOUBLE,
                is_exchange BOOLEAN,
                ts TIMESTAMP
            ) timestamp(ts) PARTITION BY DAY;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entity_balance_snapshots_daily (
                entity_id SYMBOL INDEX,
                date TIMESTAMP,
                balance_btc DOUBLE,
                ts TIMESTAMP
            ) timestamp(ts) PARTITION BY DAY;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entity_counterparty_edges_daily (
                source_entity_id SYMBOL INDEX,
                target_entity_id SYMBOL INDEX,
                movement_classification SYMBOL,
                materialization_status SYMBOL,
                window_start TIMESTAMP,
                window_end TIMESTAMP,
                btc_amount DOUBLE,
                attribution_confidence DOUBLE,
                is_internal BOOLEAN,
                ts TIMESTAMP
            ) timestamp(ts) PARTITION BY DAY;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                ts TIMESTAMP,
                signal_mean DOUBLE,
                signal_std DOUBLE,
                ci_lower DOUBLE,
                ci_upper DOUBLE,
                action SYMBOL,
                action_confidence DOUBLE,
                n_samples LONG,
                distribution_type SYMBOL,
                block_height LONG,
                active_addresses_block LONG,
                active_addresses_24h LONG,
                unique_senders LONG,
                unique_receivers LONG,
                is_anomaly BOOLEAN,
                tx_count LONG,
                tx_volume_btc DOUBLE,
                tx_volume_usd DOUBLE,
                utxoracle_price_used DOUBLE,
                low_confidence BOOLEAN,
                wasserstein_distance DOUBLE,
                wasserstein_normalized DOUBLE,
                wasserstein_shift_direction SYMBOL,
                wasserstein_regime_status SYMBOL,
                wasserstein_vote DOUBLE,
                wasserstein_is_valid BOOLEAN,
                created_at TIMESTAMP
            ) timestamp(ts) PARTITION BY DAY WAL
              DEDUP UPSERT KEYS(ts);
            """
        )

        # F-419: one row per analysed day (DEDUP UPSERT KEYS(ts)); see _enable_daily_dedup.
        for table_name in ("price_analysis", "metrics"):
            await _enable_daily_dedup(conn, table_name)

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_events (
                ts TIMESTAMP,
                event_id STRING,
                event_type SYMBOL,
                severity SYMBOL,
                payload STRING,
                webhook_status SYMBOL,
                webhook_attempts LONG,
                webhook_response_code LONG,
                webhook_error STRING,
                created_at TIMESTAMP,
                sent_at TIMESTAMP
            ) timestamp(ts) PARTITION BY DAY;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cointime_metrics (
                block_height LONG,
                ts TIMESTAMP,
                coinblocks_created DOUBLE,
                coinblocks_destroyed DOUBLE,
                cumulative_created DOUBLE,
                cumulative_destroyed DOUBLE,
                liveliness DOUBLE,
                vaultedness DOUBLE,
                active_supply_btc DOUBLE,
                vaulted_supply_btc DOUBLE,
                true_market_mean_usd DOUBLE,
                aviv_ratio DOUBLE,
                aviv_percentile DOUBLE,
                created_at TIMESTAMP
            ) timestamp(ts) PARTITION BY MONTH;
            """
        )

        # Daily Aggregates
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sopr_daily (
                ts TIMESTAMP,
                sopr DOUBLE,
                sopr_adjusted DOUBLE,
                spent_volume DOUBLE,
                profit_volume DOUBLE,
                loss_volume DOUBLE,
                created_at TIMESTAMP
            ) timestamp(ts) PARTITION BY YEAR;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nupl_daily (
                ts TIMESTAMP,
                nupl DOUBLE,
                market_cap DOUBLE,
                realized_cap DOUBLE,
                unrealized_profit DOUBLE,
                unrealized_loss DOUBLE,
                created_at TIMESTAMP
            ) timestamp(ts) PARTITION BY YEAR WAL
              DEDUP UPSERT KEYS(ts);
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mvrv_daily (
                ts TIMESTAMP,
                mvrv DOUBLE,
                mvrv_z DOUBLE,
                mvrv_z_rbn DOUBLE,
                market_cap DOUBLE,
                realized_cap DOUBLE,
                created_at TIMESTAMP
            ) timestamp(ts) PARTITION BY YEAR WAL
              DEDUP UPSERT KEYS(ts);
            """
        )

        for table_name in ("nupl_daily", "mvrv_daily"):
            for ddl in (
                f"ALTER TABLE {table_name} SET TYPE WAL",
                f"ALTER TABLE {table_name} DEDUP ENABLE UPSERT KEYS(ts)",
            ):
                try:
                    await conn.execute(ddl)
                except Exception:
                    pass

        try:
            await conn.execute("ALTER TABLE mvrv_daily ADD COLUMN mvrv_z_rbn DOUBLE")
        except Exception:
            pass

        # spec-061 T022: realized_cap_daily - added because the pre-existing DDL
        # set covered mvrv_daily + nupl_daily but not realized_cap_daily, which
        # the contract registry exposes as its own consumer-facing stream.
        # WAL + DEDUP UPSERT KEYS(ts) makes same-day re-runs replace rows.
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS realized_cap_daily (
                ts TIMESTAMP,
                realized_cap DOUBLE,
                total_supply DOUBLE,
                created_at TIMESTAMP
            ) timestamp(ts) PARTITION BY YEAR WAL
              DEDUP UPSERT KEYS(ts);
            """
        )

        # spec-061 T022 / R8: backtest_whale_signals - QuestDB consumption surface
        # for nautilus_dev. The producer (scripts/whale_flow_backtest.py) writes
        # DuckDB only; rows land here via scripts/metrics/mirror_backtest_whale_signals.py.
        # Columns match the pinned set in the registry + onchain_context.py.
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_whale_signals (
                ts TIMESTAMP,
                net_flow_btc DOUBLE,
                confidence DOUBLE,
                btc_price DOUBLE,
                inflow_btc DOUBLE,
                outflow_btc DOUBLE,
                tx_count_relevant LONG,
                created_at TIMESTAMP
            ) timestamp(ts) PARTITION BY MONTH WAL
              DEDUP UPSERT KEYS(ts);
            """
        )

        # Entity Clustering
        # The live address_clusters table is NOT created here: it is born only from a
        # refresh (RENAME of the staging table, under the refresh lock), so a restart
        # can never recreate an empty live table over a pending recovery (F-424).
        await conn.execute(ADDRESS_CLUSTERS_STAGING_DDL)

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exchange_addresses (
                address STRING,
                exchange_name SYMBOL,
                ts TIMESTAMP
            ) timestamp(ts) PARTITION BY YEAR;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS live_snapshots (
                ts TIMESTAMP,
                snapshot_ts TIMESTAMP,
                schema_version STRING,
                block_height LONG,
                utxoracle_price DOUBLE,
                utxoracle_confidence DOUBLE,
                mempool_exchange_price DOUBLE,
                hyperliquid_oracle_price DOUBLE,
                hyperliquid_mark_price DOUBLE,
                comparison_json STRING,
                features_json STRING,
                source_health_json STRING,
                source_timestamps_json STRING,
                snapshot_json STRING
            ) timestamp(ts) PARTITION BY DAY;
            """
        )

        # Wave 1 Materialization Tables (spec-046 Phase 4)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS wallet_waves_daily (
                ts TIMESTAMP,
                block_height LONG,
                total_supply_btc DOUBLE,
                retail_supply_pct DOUBLE,
                institutional_supply_pct DOUBLE,
                address_count_total LONG,
                null_address_btc DOUBLE,
                confidence DOUBLE,
                band SYMBOL,
                supply_btc DOUBLE,
                supply_pct DOUBLE,
                address_count LONG,
                avg_balance DOUBLE,
                created_at TIMESTAMP
            ) timestamp(ts) PARTITION BY MONTH;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS absorption_rates_daily (
                ts TIMESTAMP,
                block_height LONG,
                window_days INT,
                mined_supply_btc DOUBLE,
                dominant_absorber SYMBOL,
                retail_absorption DOUBLE,
                institutional_absorption DOUBLE,
                confidence DOUBLE,
                band SYMBOL,
                absorption_rate DOUBLE,
                supply_delta_btc DOUBLE,
                supply_start_btc DOUBLE,
                supply_end_btc DOUBLE,
                created_at TIMESTAMP
            ) timestamp(ts) PARTITION BY YEAR;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS address_cohorts_daily (
                ts TIMESTAMP,
                block_height LONG,
                current_price_usd DOUBLE,
                whale_retail_spread DOUBLE,
                whale_retail_mvrv_ratio DOUBLE,
                total_supply_btc DOUBLE,
                total_addresses LONG,
                cohort SYMBOL,
                cost_basis DOUBLE,
                supply_btc DOUBLE,
                supply_pct DOUBLE,
                mvrv DOUBLE,
                address_count LONG,
                created_at TIMESTAMP
            ) timestamp(ts) PARTITION BY MONTH;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cost_basis_daily (
                ts TIMESTAMP,
                block_height LONG,
                current_price_usd DOUBLE,
                sth_cost_basis DOUBLE,
                lth_cost_basis DOUBLE,
                total_cost_basis DOUBLE,
                sth_mvrv DOUBLE,
                lth_mvrv DOUBLE,
                sth_supply_btc DOUBLE,
                lth_supply_btc DOUBLE,
                confidence DOUBLE,
                created_at TIMESTAMP
            ) timestamp(ts) PARTITION BY MONTH;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS urpd_features_daily (
                ts TIMESTAMP,
                schema_version SYMBOL,
                block_height LONG,
                current_price_usd DOUBLE,
                bucket_size_usd DOUBLE,
                total_supply_btc DOUBLE,
                supply_below_price_pct DOUBLE,
                supply_above_price_pct DOUBLE,
                top_bucket_concentration DOUBLE,
                dominant_bucket_distance_pct DOUBLE,
                distribution_entropy DOUBLE,
                confidence DOUBLE,
                availability_timestamp TIMESTAMP,
                source_health_json STRING,
                source_freshness_seconds DOUBLE,
                created_at TIMESTAMP
            ) timestamp(ts) PARTITION BY MONTH;
            """
        )
        for column_name, column_type in (
            ("schema_version", "SYMBOL"),
            ("availability_timestamp", "TIMESTAMP"),
            ("source_health_json", "STRING"),
            ("source_freshness_seconds", "DOUBLE"),
        ):
            try:
                await conn.execute(
                    f"ALTER TABLE urpd_features_daily ADD COLUMN {column_name} {column_type}"
                )
            except Exception:
                pass

        logger.info("QuestDB tables verified/created successfully.")

    except Exception as e:
        logger.critical(f"Failed to initialize QuestDB tables: {e}")
        raise
    finally:
        if conn:
            await conn.close()


class QuestDBRepository:
    """
    Repository for interacting with QuestDB.
    Strictly Production-Ready: Handle connection pooling, retries, and network partitions.
    Lock-Free: Use ILP for all ingestion.
    """

    _pool: Optional[AsyncpgPool] = None

    def __init__(self):
        """
        Initializes the QuestDB repository.
        """
        import time

        self.ilp_host = QUESTDB_ILP_HOST
        self.ilp_port = QUESTDB_ILP_PORT
        self.sender: Sender | None = None
        self._unflushed_rows = 0
        self._last_flush_time = time.time()
        self._flush_batch_size = 100
        self._flush_interval_seconds = 5.0
        self._ingestion_aborted = False
        # Dedicated ILP/HTTP sender of the address_clusters refresh: flush() returns
        # only once the server committed the rows and raises if it rejects them (F-424).
        self._refresh_sender: Sender | None = None
        self._refresh_buffered = 0
        # Set when a swap is attempted in this process: from then on "neither live nor
        # _old" is a lost table, not a first install.
        self._swap_attempted = False

    def _build_refresh_sender(self):
        if Sender is None:
            raise ModuleNotFoundError(
                "questdb package is required for ILP ingestion; install project dependencies "
                "or monkeypatch QuestDBRepository._build_refresh_sender in tests"
            )
        sender = Sender("http", QUESTDB_HTTP_HOST, QUESTDB_HTTP_PORT, auto_flush=False)
        sender.establish()
        return sender

    def _close_refresh_sender(self) -> None:
        sender, self._refresh_sender = self._refresh_sender, None
        self._refresh_buffered = 0
        if sender is not None:
            in_flight = sys.exc_info()[1]
            try:
                sender.close(flush=False)
            except Exception as e:
                _swallow_if_in_flight("the refresh sender", e, in_flight)

    def _build_sender(self):
        if Sender is None:
            raise ModuleNotFoundError(
                "questdb package is required for ILP ingestion; install project dependencies "
                "or monkeypatch QuestDBRepository._build_sender in tests"
            )
        sender = Sender("tcp", self.ilp_host, self.ilp_port)
        sender.establish()
        return sender

    # Guards the creation of the shared class-level pool, one asyncio.Lock per event loop:
    # an asyncio.Lock belongs to the loop that uses it, and the synchronous LiveSnapshotStore
    # API runs its coroutines on loops of its own. A loop's lock is never replaced, so callers
    # of the same loop stay mutually excluded whatever other loops do meanwhile. The dict is
    # touched under a threading.Lock (loops can live in different threads) and holds loops
    # weakly. Callers on DIFFERENT loops are not excluded from each other: an asyncpg pool is
    # bound to the loop that created it, so sharing one across loops is a separate
    # pre-existing defect (F-410).
    _pool_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = weakref.WeakKeyDictionary()
    _pool_locks_guard = threading.Lock()

    @classmethod
    def _get_pool_lock(cls) -> "asyncio.Lock":
        loop = asyncio.get_running_loop()
        with cls._pool_locks_guard:  # lookup and insertion, no await inside
            lock = cls._pool_locks.get(loop)
            if lock is None:
                lock = asyncio.Lock()
                cls._pool_locks[loop] = lock
            return lock

    def _ensure_sender(self) -> Sender:
        if self.sender is None:
            self.sender = self._build_sender()
        return self.sender

    async def initialize(self):
        """
        Initializes the database by creating tables and establishing a connection pool.
        """
        await create_tables_if_not_exist()
        self._ensure_sender()

        if asyncpg is None:
            raise ModuleNotFoundError(
                "asyncpg package is required for QuestDB PG access; install project dependencies"
            )

        if QuestDBRepository._pool is None:
            # The None check and the assignment are separated by an await: without the lock
            # every concurrent caller (app retry, snapshot store, whale monitor) would build a
            # pool and the last assignment would orphan the others (F-399).
            async with QuestDBRepository._get_pool_lock():
                if QuestDBRepository._pool is None:
                    try:
                        QuestDBRepository._pool = await asyncpg.create_pool(
                            host=QUESTDB_PG_HOST,
                            port=QUESTDB_PG_PORT,
                            user=QUESTDB_PG_USER,
                            password=QUESTDB_PG_PASSWORD,
                            database=QUESTDB_PG_DATABASE,
                            min_size=QUESTDB_POOL_MIN_SIZE,
                            max_size=QUESTDB_POOL_MAX_SIZE,
                            command_timeout=QUESTDB_COMMAND_TIMEOUT,
                            max_inactive_connection_lifetime=QUESTDB_MAX_INACTIVE_LIFETIME,
                        )
                        logger.info(
                            f"QuestDB PG pool initialized (min={QUESTDB_POOL_MIN_SIZE}, max={QUESTDB_POOL_MAX_SIZE}, "
                            f"timeout={QUESTDB_COMMAND_TIMEOUT}s)"
                        )
                    except Exception as e:
                        logger.critical(
                            f"Failed to create QuestDB PG connection pool: {e}"
                        )
                        raise

    async def close(self):
        """Closes the connection pool and flushes pending data."""
        if not self._ingestion_aborted:
            # Flush ILP sender before closing
            try:
                await self.async_flush_ingestion()
            except Exception as e:
                logger.error(f"Error flushing ILP sender on shutdown: {e}")
        elif self._unflushed_rows > 0:
            logger.warning(
                "Skipping QuestDB ILP flush on shutdown because ingestion was aborted; dropping %s buffered rows",
                self._unflushed_rows,
            )

        if self.sender is not None:
            try:
                self.sender.close()
            except Exception as e:
                logger.error(f"Error closing QuestDB sender: {e}")
            finally:
                self.sender = None

        if QuestDBRepository._pool:
            try:
                await QuestDBRepository._pool.close()
            except Exception as e:
                logger.error(f"Error closing QuestDB connection pool: {e}")
            finally:
                QuestDBRepository._pool = None

    def abort_ingestion(self) -> None:
        """Drop any buffered ILP rows and prevent future flush on close."""
        dropped_rows = self._unflushed_rows
        self._ingestion_aborted = True
        self._unflushed_rows = 0

        if self.sender is not None:
            try:
                self.sender.close()
            except Exception as e:
                logger.error(f"Error closing QuestDB sender during abort: {e}")
            finally:
                self.sender = None

        logger.warning(
            "QuestDB ILP ingestion aborted; dropped %s buffered rows and disabled shutdown flush",
            dropped_rows,
        )

    # --- Write Path (ILP Ingestion) ---

    def _send_row(
        self,
        table: str,
        symbols: Dict[str, Any],
        columns: Dict[str, Any],
        at: Optional[Union[datetime, int]] = None,
        flush: bool = False,
    ):
        """
        Helper to send a row via ILP.
        Performance optimization: flush is False by default to allow buffering, but an automatic flush is triggered if batch size or time interval is exceeded.
        """
        import time

        if self._ingestion_aborted:
            logger.error(
                "ILP ingestion is aborted; refusing to queue new row for table %s",
                table,
            )
            return False
        try:
            try:
                sender = self._ensure_sender()
                sender.row(table, symbols=symbols, columns=columns, at=at)
            except Exception as exc:
                if "Sender is closed" not in str(exc):
                    raise
                logger.warning(
                    "QuestDB sender was closed; recreating sender and retrying once"
                )
                self.sender = None
                sender = self._ensure_sender()
                sender.row(table, symbols=symbols, columns=columns, at=at)

            self._unflushed_rows += 1
            now = time.time()

            if (
                flush
                or self._unflushed_rows >= self._flush_batch_size
                or (now - self._last_flush_time) >= self._flush_interval_seconds
            ):
                self.sender.flush()
                self._unflushed_rows = 0
                self._last_flush_time = now
            return True
        except Exception as e:
            logger.error(f"ILP Ingestion error on table {table}: {e}")
            return False

    def flush_ingestion(self):
        """Explicitly flush buffered ILP data."""
        import time

        if self._ingestion_aborted:
            logger.warning(
                "Skipping QuestDB sender flush because ingestion was aborted"
            )
            return False
        try:
            if self._unflushed_rows > 0:
                sender = self._ensure_sender()
                sender.flush()
                self._unflushed_rows = 0
                self._last_flush_time = time.time()
            return True
        except Exception as e:
            logger.error(f"Failed to flush QuestDB sender: {e}")
            return False

    async def async_send_row(
        self,
        table: str,
        symbols: Dict[str, Any],
        columns: Dict[str, Any],
        at: Optional[Union[datetime, int]] = None,
        flush: bool = False,
    ):
        """Async wrapper for _send_row.

        QuestDB's ILP sender is stateful and connection-oriented; keep row writes on the
        same thread that created the sender.
        """
        return self._send_row(table, symbols, columns, at, flush)

    async def async_flush_ingestion(self):
        """Async wrapper for flush_ingestion."""
        return self.flush_ingestion()

    def save_whale_transaction(self, transaction: WhaleTransaction) -> bool:
        """Save whale transaction via ILP."""
        return self._send_row(
            "whale_transactions",
            symbols={
                "transaction_id": transaction.transaction_id,
                "direction": transaction.direction,
            },
            columns={
                "block_height": transaction.block_height,
                "amount_btc": float(transaction.amount_btc),
                "amount_usd": float(transaction.amount_usd),
                "urgency_score": transaction.urgency_score,
                "fee_rate": transaction.fee_rate,
                "confidence": transaction.confidence,
                "is_mempool": transaction.is_mempool,
                "detected_at": transaction.detected_at,
            },
            at=transaction.timestamp,
        )

    def save_mempool_prediction(self, prediction: Any) -> bool:
        """
        Save mempool whale prediction via ILP.
        Takes a MempoolWhaleSignal or a dict with compatible fields.
        """
        if hasattr(prediction, "model_dump"):
            data = prediction.model_dump()
        elif hasattr(prediction, "to_db_dict"):
            data = prediction.to_db_dict()
        else:
            data = prediction

        return self._send_row(
            "mempool_predictions",
            symbols={
                "prediction_id": data.get("prediction_id"),
                "transaction_id": data.get("transaction_id"),
                "flow_type": str(data.get("flow_type", "unknown")),
            },
            columns={
                "btc_value": float(data.get("btc_value", 0.0)),
                "fee_rate": float(data.get("fee_rate", 0.0)),
                "urgency_score": float(data.get("urgency_score", 0.0)),
                "rbf_enabled": bool(data.get("rbf_enabled", False)),
                "ts": data.get("detection_timestamp") or data.get("ts"),
                "predicted_confirmation_block": data.get(
                    "predicted_confirmation_block"
                ),
                "exchange_addresses": str(data.get("exchange_addresses", "")),
                "confidence_score": float(data.get("confidence_score", 0.0))
                if data.get("confidence_score") is not None
                else None,
                "was_modified": bool(data.get("was_modified", False)),
                "created_at": data.get("created_at") or datetime.utcnow(),
            },
            at=data.get("detection_timestamp") or data.get("ts") or datetime.utcnow(),
        )

    def save_net_flow(self, metrics: NetFlowMetrics) -> bool:
        """Save net flow metrics via ILP."""
        return self._send_row(
            "net_flow_metrics",
            symbols={
                "interval": metrics.interval,
                "direction": metrics.direction,
            },
            columns={
                "period_start": metrics.period_start,
                "period_end": metrics.period_end,
                "net_flow_btc": float(metrics.net_flow_btc),
                "net_flow_usd": float(metrics.net_flow_usd),
                "total_buy_btc": float(metrics.total_buy_btc),
                "total_sell_btc": float(metrics.total_sell_btc),
                "transaction_count": metrics.transaction_count,
                "strength": metrics.strength,
                "largest_tx_btc": float(metrics.largest_tx_btc)
                if metrics.largest_tx_btc
                else None,
            },
            at=metrics.created_at,
        )

    def save_alert(self, alert: Alert) -> bool:
        """Save alert via ILP."""
        return self._send_row(
            "alerts",
            symbols={
                "alert_id": alert.alert_id,
                "transaction_id": alert.transaction_id,
                "severity": alert.severity,
                "trigger_type": alert.trigger_type,
                "direction": alert.direction,
            },
            columns={
                "threshold_value": float(alert.threshold_value),
                "title": alert.title,
                "message": alert.message,
                "amount_btc": float(alert.amount_btc),
                "amount_usd": float(alert.amount_usd),
                "acknowledged": alert.acknowledged,
                "acknowledged_at": alert.acknowledged_at,
            },
            at=alert.created_at,
        )

    def save_utxo_lifecycle(self, utxo_data: Dict[str, Any]) -> bool:
        """Save UTXO record via ILP (Initial creation)."""
        ts = utxo_data.get("creation_timestamp") or utxo_data.get("ts")
        return self._send_row(
            "utxo_lifecycle",
            symbols={
                "cohort": utxo_data.get("cohort", ""),
                "sub_cohort": utxo_data.get("sub_cohort", ""),
                "price_source": utxo_data.get("price_source", "utxoracle"),
            },
            columns={
                "outpoint": utxo_data["outpoint"],
                "txid": utxo_data["txid"],
                "vout_index": utxo_data["vout_index"],
                "creation_block": utxo_data["creation_block"],
                "creation_price_usd": float(utxo_data["creation_price_usd"]),
                "btc_value": float(utxo_data["btc_value"]),
                "realized_value_usd": float(utxo_data["realized_value_usd"]),
                "is_coinbase": utxo_data.get("is_coinbase", False),
                "is_spent": utxo_data.get("is_spent", False),
            },
            at=ts,
        )

    def save_wallet_waves(self, result: WalletWavesResult) -> bool:
        """
        Save wallet waves distribution via ILP.
        Saves one row per band to allow flexible time-series aggregation.
        """
        success = True
        created_at = datetime.utcnow()
        for band_metrics in result.bands:
            row_success = self._send_row(
                "wallet_waves_daily",
                symbols={
                    "band": band_metrics.band.value,
                },
                columns={
                    "block_height": result.block_height,
                    "total_supply_btc": float(result.total_supply_btc),
                    "retail_supply_pct": float(result.retail_supply_pct),
                    "institutional_supply_pct": float(result.institutional_supply_pct),
                    "address_count_total": int(result.address_count_total),
                    "null_address_btc": float(result.null_address_btc),
                    "confidence": float(result.confidence),
                    "supply_btc": float(band_metrics.supply_btc),
                    "supply_pct": float(band_metrics.supply_pct),
                    "address_count": int(band_metrics.address_count),
                    "avg_balance": float(band_metrics.avg_balance),
                    "created_at": created_at,
                },
                at=result.timestamp,
            )
            if not row_success:
                success = False
        return success

    def save_absorption_rates(self, result: AbsorptionRatesResult) -> bool:
        """
        Save absorption rates via ILP.
        Saves one row per band.
        """
        success = True
        created_at = datetime.utcnow()
        for band_metrics in result.bands:
            row_success = self._send_row(
                "absorption_rates_daily",
                symbols={
                    "band": band_metrics.band.value,
                    "dominant_absorber": result.dominant_absorber.value,
                },
                columns={
                    "block_height": result.block_height,
                    "window_days": int(result.window_days),
                    "mined_supply_btc": float(result.mined_supply_btc),
                    "retail_absorption": float(result.retail_absorption),
                    "institutional_absorption": float(result.institutional_absorption),
                    "confidence": float(result.confidence),
                    "absorption_rate": float(band_metrics.absorption_rate)
                    if band_metrics.absorption_rate is not None
                    else None,
                    "supply_delta_btc": float(band_metrics.supply_delta_btc),
                    "supply_start_btc": float(band_metrics.supply_start_btc),
                    "supply_end_btc": float(band_metrics.supply_end_btc),
                    "created_at": created_at,
                },
                at=result.timestamp,
            )
            if not row_success:
                success = False
        return success

    def stage_address_cluster(
        self,
        row: Dict[str, Any],
        *,
        table: str = ADDRESS_CLUSTERS_STAGING_TABLE,
    ) -> bool:
        """Stage a single address-cluster row for a full-refresh cutover."""
        ts = row.get("first_seen") or datetime.utcnow()
        symbols = {}
        if row.get("label"):
            symbols["label"] = str(row["label"])

        try:
            if self._refresh_sender is None:
                self._refresh_sender = self._build_refresh_sender()
            self._refresh_sender.row(
                table,
                symbols=symbols,
                columns={
                    "address": str(row["address"]),
                    "cluster_id": str(row["cluster_id"]),
                    "last_seen": row.get("last_seen"),
                    "is_exchange_likely": bool(row.get("is_exchange_likely", False)),
                    "confidence": float(row.get("confidence", 0.6)),
                },
                at=ts,
            )
            self._refresh_buffered += 1
            if self._refresh_buffered >= ADDRESS_CLUSTERS_FLUSH_ROWS:
                self._refresh_sender.flush()
                self._refresh_buffered = 0
            return True
        except Exception as e:
            logger.error(f"Failed to stage address_clusters row over ILP/HTTP: {e}")
            return False

    async def _run_ddl(self, *statements: str) -> None:
        """Run DDL on a dedicated connection (never the pool); a failure raises."""
        conn = await self._open_dedicated_connection()
        statement = ""
        try:
            try:
                for statement in statements:
                    await conn.execute(statement)
            except Exception:
                logger.exception(
                    "address_clusters DDL failed: %s", " ".join(statement.split())
                )
                raise
        finally:
            await close_safely(conn.close, "the DDL connection")

    async def prepare_address_clusters_refresh(self, token: RefreshLock) -> bool:
        """
        Make sure the staging table exists and is empty before loading a snapshot.

        Needs the live lock token. The live table is left untouched until the cutover. A
        failure raises.
        """
        _require_lock(token)
        self._close_refresh_sender()
        await self._run_ddl(
            ADDRESS_CLUSTERS_STAGING_DDL,
            f"TRUNCATE TABLE {ADDRESS_CLUSTERS_STAGING_TABLE}",
        )
        logger.info("Prepared QuestDB address_clusters staging table.")
        return True

    async def abort_address_clusters_refresh(self, token: RefreshLock) -> None:
        """Abort a staged refresh before the cutover: the staged rows are dropped. Needs
        the live lock token; a failing TRUNCATE raises."""
        _require_lock(token)
        self._close_refresh_sender()
        await self._run_ddl(f"TRUNCATE TABLE {ADDRESS_CLUSTERS_STAGING_TABLE}")

    async def _table_wal(self, table: str) -> Optional[Any]:
        rows = await self.fetch(
            'SELECT suspended, "writerTxn", "sequencerTxn", "errorTag", '
            '"errorMessage" FROM wal_tables() WHERE name = $1',
            table,
        )
        return rows[0] if rows else None

    async def _wait_table_applied(
        self,
        table: str,
        expected_rows: int,
        *,
        max_wait_s: float,
        poll_s: float,
        not_wal_hint: str = "",
    ) -> bool:
        """Wait until WAL has applied every row written to `table`, judged on wal_tables().

        The sequencerTxn read on entry (after the last confirmed write) is the target:
        wait for writerTxn >= target, then require an exact count. Returns False (ERROR
        with the cause: not_wal, suspended, ceiling, count_mismatch); exceptions propagate.
        """
        started = _monotonic()

        def fail(cause: str, detail: str) -> bool:
            logger.error(
                "%s not applied (%s): expected %d rows, %s, after %.1f s; live table "
                "left untouched",
                table,
                cause,
                expected_rows,
                detail,
                _monotonic() - started,
            )
            return False

        wal = await self._table_wal(table)
        if wal is None:
            return fail(
                "not_wal", f"{table} not in wal_tables(); operator: {not_wal_hint}"
            )
        target = int(wal["sequencerTxn"])
        while True:
            if wal is None:
                return fail(
                    "not_wal",
                    f"{table} vanished from wal_tables(); operator: {not_wal_hint}",
                )
            writer = int(wal["writerTxn"])
            logger.info(
                "%s WAL: writerTxn=%d target=%d suspended=%s after %.1f s",
                table,
                writer,
                target,
                bool(wal["suspended"]),
                _monotonic() - started,
            )
            if wal["suspended"]:
                return fail(
                    "suspended",
                    f"errorTag={wal['errorTag']!r} errorMessage={wal['errorMessage']!r}",
                )
            if writer >= target:
                break
            if _monotonic() - started >= max_wait_s:
                return fail("ceiling", f"ceiling {max_wait_s:.0f} s reached")
            await _sleep(poll_s)
            wal = await self._table_wal(table)

        count_row = await self.fetchrow(f"SELECT count(*) FROM {table}")
        observed = int(count_row[0]) if count_row is not None else 0
        if observed != expected_rows:
            return fail("count_mismatch", f"observed {observed}")
        logger.info(
            "%s complete: %d rows after %.1f s", table, observed, _monotonic() - started
        )
        return True

    async def _publish_staging(
        self, expected_rows: int, *, max_wait_s: float, poll_s: float
    ) -> bool:
        """Flush the staging load and verify it before the cutover (read-only).

        ILP/HTTP flush() returns after the commit. Checks: WAL, not suspended, writerTxn
        reached, exact count, and name and type of every column (schema_mismatch).
        Returns False without touching the live table; exceptions propagate. There is no
        automatic WAL migration: on not_wal the operator runs either DROP TABLE
        address_clusters_staging (empty outside a refresh, recreated as WAL at the next
        refresh) or ALTER TABLE address_clusters_staging SET TYPE WAL plus a QuestDB
        restart.
        """
        if self._refresh_sender is not None and self._refresh_buffered > 0:
            self._refresh_sender.flush()
            self._refresh_buffered = 0
        self._close_refresh_sender()
        if not await self._wait_table_applied(
            ADDRESS_CLUSTERS_STAGING_TABLE,
            expected_rows,
            max_wait_s=max_wait_s,
            poll_s=poll_s,
            not_wal_hint=ADDRESS_CLUSTERS_NOT_WAL_HINT,
        ):
            return False
        columns = [
            (r[0], r[1])
            for r in await self.fetch(
                'SELECT "column", "type" FROM '
                f"table_columns('{ADDRESS_CLUSTERS_STAGING_TABLE}')"
            )
        ]
        if columns != ADDRESS_CLUSTERS_SCHEMA:
            logger.error(
                "%s not applied (schema_mismatch): found %s, expected %s; live table "
                "left untouched",
                ADDRESS_CLUSTERS_STAGING_TABLE,
                columns,
                ADDRESS_CLUSTERS_SCHEMA,
            )
            return False
        return True

    async def _open_dedicated_connection(self):
        """Fresh PG connection for DDL, never the pool and never used for a fetch (on
        QuestDB 7.4 a fetch followed by an execute on one asyncpg connection breaks it)."""
        if asyncpg is None:
            raise ModuleNotFoundError("asyncpg package is required for the cutover")
        return await asyncpg.connect(
            host=QUESTDB_PG_HOST,
            port=QUESTDB_PG_PORT,
            user=QUESTDB_PG_USER,
            password=QUESTDB_PG_PASSWORD,
            database=QUESTDB_PG_DATABASE,
        )

    def _default_max_wait_s(self, expected_rows: int) -> float:
        return max(
            ADDRESS_CLUSTERS_MIN_WAIT_S,
            expected_rows / ADDRESS_CLUSTERS_MIN_APPLY_ROWS_PER_S,
        )

    async def _observe_catalog(self, prefix: str) -> set[str]:
        """Names of the tables starting with `prefix`: the ONLY read of tables() in the
        refresh path. Any failure is AddressClustersLostError (exit 6) with the manual
        command: a refresh must never decide, or die, on a catalog it could not read."""
        try:
            rows = await self.fetch(
                f"SELECT table_name FROM tables() WHERE table_name LIKE '{prefix}%'"
            )
        except Exception as e:
            raise AddressClustersLostError(
                f"could not observe the tables ({e}): inspect tables(), or "
                f"{ADDRESS_CLUSTERS_REBUILD_COMMAND}"
            ) from e
        return {row[0] for row in rows}

    async def _swap_tables(
        self, conn, live: str, staging: str, old: str, live_exists: bool = True
    ) -> float:
        """RENAME live -> old (when there is a live table), then staging -> live; returns
        the ms the live name was absent. No rollback here: whatever raises, the caller
        decides from the observed tables (a lost acknowledgement does not prove the
        statement was not applied)."""
        if live_exists:
            await conn.execute(f"RENAME TABLE {live} TO {old}")
        absent_since = _monotonic()
        await conn.execute(f"RENAME TABLE {staging} TO {live}")
        return (_monotonic() - absent_since) * 1000.0

    async def _guarded_swap(
        self, conn, live: str, staging: str, old: str, live_exists: bool = True
    ) -> float:
        """_swap_tables in a shielded task: a cancellation while a RENAME is in flight
        waits for the swap to finish, then propagates. What was left is judged from the
        observed tables (_reconcile_tables), never from the exception branch."""
        task = asyncio.ensure_future(
            self._swap_tables(conn, live, staging, old, live_exists)
        )
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await asyncio.gather(task, return_exceptions=True)
            raise

    async def _swap_or_reconcile(
        self, conn, live: str, staging: str, old: str, live_exists: bool = True
    ) -> Optional[float]:
        """The one publication function (first install and cutover alike). After ANY
        failure, at any step, _reconcile_tables decides on the observed tables, never the
        exception branch. Returns the absent window in ms, or None when the refresh did
        not publish (the previous live table is back); BaseException (cancellation) is
        re-raised after reconciling."""
        self._swap_attempted = True
        try:
            return await self._guarded_swap(conn, live, staging, old, live_exists)
        except BaseException as e:
            logger.error(
                "%s swap failed (%r); deciding from the observed tables", live, e
            )
            await self._reconcile_tables(live, live)
            if not isinstance(e, Exception):
                raise
            if staging not in await self._observe_catalog(
                staging
            ):  # live present, staging consumed: the staging RENAME was applied
                logger.warning(
                    "%s: snapshot pubblicato, ack perso, pulizia al prossimo giro "
                    "(rollback copy: %s)",
                    live,
                    old if live_exists else "none, first install",
                )
            return None

    async def _reconcile_tables(self, live: str, prefix: str) -> None:
        """Idempotent repair from the observed state (covers SIGKILL between the RENAMEs).

        live absent + `<prefix>_old_*` present -> RENAME the newest _old to live (ERROR);
        live present -> nothing (a published swap; its _old is the rollback copy and is
        dropped only by the next successful refresh). Any failure to observe or to
        restore, at any moment, is AddressClustersLostError (exit 6) with the manual
        command. The only error-free state with the live table absent: observation
        succeeded, neither live nor _old exists, and no swap was attempted in this
        process (first install).
        """
        old_re = re.compile(rf"^{re.escape(prefix)}_old_[0-9]{{8}}T[0-9]{{6}}Z$")
        catalog = await self._observe_catalog(prefix)
        if live in catalog:
            return
        olds = sorted(name for name in catalog if old_re.match(name))
        if olds:
            try:
                await self._run_ddl(f"RENAME TABLE {olds[-1]} TO {live}")
            except Exception as e:
                raise AddressClustersLostError(
                    f"could not restore {live} ({e}): run "
                    f"`RENAME TABLE {olds[-1]} TO {live}`, or "
                    f"{ADDRESS_CLUSTERS_REBUILD_COMMAND}"
                ) from e
            logger.error("%s was missing: restored from %s", live, olds[-1])
            return
        if self._swap_attempted:
            raise AddressClustersLostError(
                f"no {live} and no {prefix}_old_* copy after a swap: if the staging "
                f"table still exists it holds the verified snapshot (RENAME it to "
                f"{live}), otherwise restore from a backup or "
                f"{ADDRESS_CLUSTERS_REBUILD_COMMAND}"
            )
        logger.info("No %s and no _old copy: first install", live)

    async def reconcile_address_clusters(self, token: RefreshLock) -> None:
        _require_lock(token)
        await self._reconcile_tables(ADDRESS_CLUSTERS_TABLE, ADDRESS_CLUSTERS_TABLE)

    async def _cutover(self) -> bool:
        """Swap the verified staging table in as the live table (RENAME, not INSERT).

        Old copies: the previous live table stays as address_clusters_old_<UTC> for
        rollback. It is deleted only by the NEXT successful refresh, never by the run
        that created it; after a successful cutover at most one _old exists (the one just
        made), older ones are dropped. Staging is recreated empty (WAL). A failing swap
        returns False with the live table restored. A DROP failing AFTER the swap does
        not undo it: OldCopyCleanupError (exit code 5) names the copies left and the next
        refresh retries the cleanup. Without a live table it is a single RENAME.
        """
        old = f"{ADDRESS_CLUSTERS_TABLE}_old_{datetime.utcnow():%Y%m%dT%H%M%SZ}"
        live_exists = ADDRESS_CLUSTERS_TABLE in await self._observe_catalog(
            ADDRESS_CLUSTERS_TABLE
        )
        conn = await self._open_dedicated_connection()
        try:
            window_ms = await self._swap_or_reconcile(
                conn,
                ADDRESS_CLUSTERS_TABLE,
                ADDRESS_CLUSTERS_STAGING_TABLE,
                old,
                live_exists,
            )
            if window_ms is None:
                return False
            logger.info(
                "address_clusters published; %s absent for %.1f ms; previous kept as %s",
                ADDRESS_CLUSTERS_TABLE,
                window_ms,
                old if live_exists else "none (first install)",
            )
            try:
                await conn.execute(ADDRESS_CLUSTERS_STAGING_DDL)
            except Exception as e:
                logger.error(
                    "Could not recreate the empty staging table (the next refresh "
                    "recreates it): %s",
                    e,
                )
            left = []
            for name in sorted(await self._observe_catalog(ADDRESS_CLUSTERS_TABLE)):
                if name != old and _OLD_COPY_RE.match(name):
                    try:
                        await conn.execute(f"DROP TABLE {name}")
                    except Exception:
                        logger.exception(
                            "Swap ok but could not drop the older copy %s; the next "
                            "refresh retries",
                            name,
                        )
                        left.append(name)
            if left:
                raise OldCopyCleanupError(left)
            return True
        finally:
            await close_safely(conn.close, "the cutover connection")

    async def commit_address_clusters_refresh(
        self,
        token: RefreshLock,
        expected_rows: int,
        *,
        max_wait_s: Optional[float] = None,
        poll_s: float = ADDRESS_CLUSTERS_POLL_S,
    ) -> bool:
        """
        Publish a staged address_clusters snapshot after the ILP load completes.

        Needs the live lock token. `expected_rows` is the number of rows sent to
        staging. The staging table is verified (see _publish_staging) and swapped in with
        RENAME (see _cutover). Any failed check aborts, leaving the live table untouched;
        an unexpected exception is logged with its traceback and re-raised so the job
        exits non-zero.
        """
        _require_lock(token)
        try:
            published = await self._publish_staging(
                expected_rows,
                max_wait_s=max_wait_s
                if max_wait_s is not None
                else self._default_max_wait_s(expected_rows),
                poll_s=poll_s,
            )
        except Exception:
            logger.exception("address_clusters staging failed before cutover")
            await self.abort_address_clusters_refresh(token)
            raise
        if not published:
            await self.abort_address_clusters_refresh(token)
            return False
        return await self._cutover()

    async def refresh_address_clusters(
        self,
        producer,
        *,
        max_wait_s: Optional[float] = None,
        poll_s: float = ADDRESS_CLUSTERS_POLL_S,
    ) -> bool:
        """The ONLY place that takes the refresh lock; every refresh goes through here.

        Under the lock, from before the first mutation to commit or abort: reconcile the
        tables, prepare the staging table, run `producer` (an async callable that stages
        the rows and returns how many, or None on failure), commit or abort.
        """
        token = RefreshLock.acquire()
        self._swap_attempted = False
        try:
            return await self._refresh_under_lock(
                token, producer, max_wait_s=max_wait_s, poll_s=poll_s
            )
        finally:
            await close_safely(token.release, "the refresh lock")

    async def _refresh_under_lock(
        self,
        token: RefreshLock,
        producer,
        *,
        max_wait_s: Optional[float],
        poll_s: float,
    ) -> bool:
        try:
            await self.reconcile_address_clusters(token)
            await self.prepare_address_clusters_refresh(token)
            try:
                expected_rows = await producer()
            except Exception:
                await self.abort_address_clusters_refresh(token)
                raise
            if expected_rows is None:
                await self.abort_address_clusters_refresh(token)
                return False
            return await self.commit_address_clusters_refresh(
                token, expected_rows, max_wait_s=max_wait_s, poll_s=poll_s
            )
        except AddressClustersLostError:
            raise
        except Exception:
            if self._swap_attempted:
                # one boundary: the outcome is read from the tables, never inferred from
                # the exception (an unobservable state is exit 6)
                await self._reconcile_tables(
                    ADDRESS_CLUSTERS_TABLE, ADDRESS_CLUSTERS_TABLE
                )
            raise

    async def save_address_clusters_bulk(self, rows: List[Dict[str, Any]]) -> bool:
        """
        Stage and publish a full address_clusters refresh via ILP/HTTP and RENAME.
        """

        async def producer() -> Optional[int]:
            for row in rows:
                if not self.stage_address_cluster(row):
                    return None
            return len(rows)

        return await self.refresh_address_clusters(producer)

    async def get_cluster_for_address(self, address: str) -> Optional[Dict[str, Any]]:
        """Fetch fine-grained cluster info from QuestDB."""
        try:
            # We use PG wire port (8812) for select queries via fetchrow
            query = f"SELECT cluster_id FROM {ADDRESS_CLUSTERS_TABLE} WHERE address = $1 LIMIT 1"
            row = await self.fetchrow(query, address)
            return {"cluster_id": row[0]} if row else None
        except Exception as e:
            logger.error(f"Cluster lookup failed for {address}: {e}")
            return None

    def save_address_cohorts(self, result: AddressCohortsResult) -> bool:
        """
        Save address cohorts via ILP.
        Saves one row per cohort (retail, mid_tier, whale).
        """
        success = True
        created_at = datetime.utcnow()
        cohorts = {
            "retail": result.retail,
            "mid_tier": result.mid_tier,
            "whale": result.whale,
        }
        for cohort_name, metrics in cohorts.items():
            row_success = self._send_row(
                "address_cohorts_daily",
                symbols={
                    "cohort": cohort_name,
                },
                columns={
                    "block_height": result.block_height,
                    "current_price_usd": float(result.current_price_usd),
                    "whale_retail_spread": float(result.whale_retail_spread),
                    "whale_retail_mvrv_ratio": float(result.whale_retail_mvrv_ratio),
                    "total_supply_btc": float(result.total_supply_btc),
                    "total_addresses": int(result.total_addresses),
                    "cost_basis": float(metrics.cost_basis),
                    "supply_btc": float(metrics.supply_btc),
                    "supply_pct": float(metrics.supply_pct),
                    "mvrv": float(metrics.mvrv),
                    "address_count": int(metrics.address_count),
                    "created_at": created_at,
                },
                at=result.timestamp,
            )
            if not row_success:
                success = False
        return success

    def save_cost_basis(self, result: "CostBasisResult") -> bool:
        """
        Save STH/LTH cost basis metrics via ILP.
        """
        created_at = datetime.utcnow()
        return self._send_row(
            "cost_basis_daily",
            symbols={},
            columns={
                "block_height": result.block_height,
                "current_price_usd": float(result.current_price_usd),
                "sth_cost_basis": float(result.sth_cost_basis),
                "lth_cost_basis": float(result.lth_cost_basis),
                "total_cost_basis": float(result.total_cost_basis),
                "sth_mvrv": float(result.sth_mvrv),
                "lth_mvrv": float(result.lth_mvrv),
                "sth_supply_btc": float(result.sth_supply_btc),
                "lth_supply_btc": float(result.lth_supply_btc),
                "confidence": float(result.confidence),
                "created_at": created_at,
            },
            at=result.timestamp,
        )

    def save_urpd_features(self, result: "URPDFeaturesResult") -> bool:
        """
        Save scalar features derived from the URPD / cost-basis distribution.
        """
        if result.availability_timestamp is None:
            # Fail closed: a row without the time it became available cannot be used
            # point-in-time, and defaulting it to now would leak look-ahead into backfills.
            logger.error(
                "Refusing to save urpd_features_daily row for block %s: "
                "availability_timestamp is not set by the producer",
                result.block_height,
            )
            raise ValueError("availability_timestamp is required to save urpd features")
        created_at = datetime.utcnow()
        source_health = dict(result.source_health or {})
        source_freshness_seconds = source_health.get("source_freshness_seconds")

        def optional_float(value):
            return None if value is None else float(value)

        return self._send_row(
            "urpd_features_daily",
            symbols={
                "schema_version": result.schema_version,
            },
            columns={
                "block_height": result.block_height,
                "current_price_usd": optional_float(result.current_price_usd),
                "bucket_size_usd": float(result.bucket_size_usd),
                "total_supply_btc": optional_float(result.total_supply_btc),
                "supply_below_price_pct": optional_float(result.supply_below_price_pct),
                "supply_above_price_pct": optional_float(result.supply_above_price_pct),
                "top_bucket_concentration": optional_float(
                    result.top_bucket_concentration
                ),
                "dominant_bucket_distance_pct": optional_float(
                    result.dominant_bucket_distance_pct
                ),
                "distribution_entropy": optional_float(result.distribution_entropy),
                "confidence": float(result.confidence),
                "availability_timestamp": result.availability_timestamp,
                "source_health_json": json.dumps(source_health, sort_keys=True),
                "source_freshness_seconds": optional_float(source_freshness_seconds),
                "created_at": created_at,
            },
            at=result.timestamp,
        )

    # --- Read Path (PostgreSQL Wire Protocol) ---

    async def fetch(self, query: str, *args) -> List[AsyncpgRecord]:
        """Fetch multiple rows via PG pool."""
        if not self._pool:
            await self.initialize()
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> Optional[AsyncpgRecord]:
        """Fetch a single row via PG pool."""
        if not self._pool:
            await self.initialize()
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def execute(self, query: str, *args) -> str:
        """Execute a command (e.g., UPDATE) via PG pool."""
        if not self._pool:
            await self.initialize()
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def get_latest_price_analysis(self) -> Optional[AsyncpgRecord]:
        """Get latest price analysis entry."""
        return await self.fetchrow(
            "SELECT * FROM price_analysis ORDER BY ts DESC LIMIT 1"
        )

    async def get_latest_live_snapshot_row(self) -> Optional[AsyncpgRecord]:
        """Get latest live snapshot entry."""
        return await self.fetchrow(
            "SELECT * FROM live_snapshots ORDER BY ts DESC LIMIT 1"
        )

    async def get_latest_metrics(self) -> Optional[AsyncpgRecord]:
        """Get the most recent metrics entry."""
        return await self.fetchrow("SELECT * FROM metrics ORDER BY ts DESC LIMIT 1")

    async def get_historical_price_analysis(self, days: int = 7) -> List[AsyncpgRecord]:
        """Get historical price analysis entries."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        return await self.fetch(
            "SELECT * FROM price_analysis WHERE ts > $1 ORDER BY ts ASC", cutoff
        )

    async def update_utxo_spent(
        self, outpoint: str, spend_data: Dict[str, Any]
    ) -> bool:
        """
        Update UTXO record as spent.
        Note: QuestDB supports UPDATE via PG wire protocol.
        """
        try:
            await self.execute(
                """
                UPDATE utxo_lifecycle SET
                    spent_block = $1,
                    spent_timestamp = $2,
                    spent_price_usd = $3,
                    spending_txid = $4,
                    age_blocks = $5,
                    age_days = $6,
                    cohort = $7,
                    sub_cohort = $8,
                    sopr = $9,
                    is_spent = true
                WHERE outpoint = $10
                """,
                spend_data["spent_block"],
                spend_data["spent_timestamp"],
                spend_data["spent_price_usd"],
                spend_data["spending_txid"],
                spend_data["age_blocks"],
                spend_data["age_days"],
                spend_data["cohort"],
                spend_data["sub_cohort"],
                spend_data["sopr"],
                outpoint,
            )
            return True
        except Exception as e:
            logger.error(f"Error updating UTXO {outpoint}: {e}")
            return False

    async def get_utxo(self, outpoint: str) -> Optional[AsyncpgRecord]:
        """Get UTXO by outpoint."""
        return await self.fetchrow(
            "SELECT * FROM utxo_lifecycle WHERE outpoint = $1", outpoint
        )

    async def get_supply_metrics_latest(self) -> Optional[AsyncpgRecord]:
        """Get latest supply metrics from snapshots."""
        return await self.fetchrow(
            "SELECT * FROM utxo_snapshots ORDER BY ts DESC LIMIT 1"
        )

    async def get_metrics_latest(self) -> Optional[AsyncpgRecord]:
        """Get latest general metrics."""
        return await self.fetchrow("SELECT * FROM metrics ORDER BY ts DESC LIMIT 1")

    async def get_cointime_latest(self) -> Optional[AsyncpgRecord]:
        """Get latest cointime metrics."""
        return await self.fetchrow(
            "SELECT * FROM cointime_metrics ORDER BY ts DESC LIMIT 1"
        )

    async def get_exchange_netflow(
        self, window_hours: int = 24
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate exchange netflow using QuestDB's SQL.
        Performance tuning: Use QuestDB's time-series functions.
        """
        # simplified version for migration
        _ = window_hours
        # This would be expanded with actual exchange address filtering
        return None

    async def get_wallet_waves_latest(self) -> List[AsyncpgRecord]:
        """Fetch latest wallet waves snapshot (all bands)."""
        # QuestDB specific: latest row per symbol
        query = """
        SELECT * FROM wallet_waves_daily LATEST ON ts PARTITION BY band;
        """
        return await self.fetch(query)

    async def get_wallet_waves_history(self, days: int = 30) -> List[AsyncpgRecord]:
        """Fetch historical wallet waves."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = """
        SELECT * FROM wallet_waves_daily WHERE ts > $1 ORDER BY ts ASC, band ASC;
        """
        return await self.fetch(query, cutoff)

    async def get_absorption_rates_latest(
        self, window_days: int = 30
    ) -> List[AsyncpgRecord]:
        """Fetch latest absorption rates for a specific window."""
        query = """
        SELECT * FROM absorption_rates_daily 
        WHERE window_days = $1 
        LATEST ON ts PARTITION BY band;
        """
        return await self.fetch(query, window_days)

    async def get_address_cohorts_latest(self) -> List[AsyncpgRecord]:
        """Fetch latest address cohorts (all cohorts)."""
        query = """
        SELECT * FROM address_cohorts_daily LATEST ON ts PARTITION BY cohort;
        """
        return await self.fetch(query)

    async def get_cost_basis_latest(self) -> Optional[AsyncpgRecord]:
        """Fetch the latest STH/LTH cost basis metrics."""
        query = """
        SELECT *
        FROM cost_basis_daily
        ORDER BY ts DESC
        LIMIT 1;
        """
        return await self.fetchrow(query)

    async def get_urpd_features_latest(self) -> Optional[AsyncpgRecord]:
        """Fetch the latest URPD-derived scalar features."""
        query = """
        SELECT *
        FROM urpd_features_daily
        ORDER BY ts DESC, block_height DESC, created_at DESC
        LIMIT 1;
        """
        return await self.fetchrow(query)

    async def get_urpd_features_at_or_before(
        self,
        timestamp: datetime,
    ) -> Optional[AsyncpgRecord]:
        """Fetch the latest URPD-derived scalar features at or before timestamp."""
        query = """
        SELECT *
        FROM urpd_features_daily
        WHERE ts <= $1
        ORDER BY ts DESC, block_height DESC, created_at DESC
        LIMIT 1;
        """
        return await self.fetchrow(query, timestamp)

    async def get_latest_feature_bundle(self, bundle_id: str) -> dict | None:
        query = f"""
        SELECT * FROM btc_feature_bundles 
        WHERE bundle_id = '{bundle_id}'
        ORDER BY sequence_id DESC, produced_at DESC
        LIMIT 1;
        """
        row = await self.fetchrow(query)
        if not row:
            return None
        return dict(row)

    async def get_feature_bundle_history(
        self,
        bundle_id: str,
        limit: int,
        after_sequence_id: int | None = None,
    ) -> list[dict]:
        sequence_filter = (
            f"AND sequence_id > {after_sequence_id}"
            if after_sequence_id is not None
            else ""
        )
        query = f"""
        SELECT * FROM btc_feature_bundles 
        WHERE bundle_id = '{bundle_id}'
        {sequence_filter}
        ORDER BY sequence_id ASC, produced_at ASC
        LIMIT {limit};
        """
        rows = await self.fetch(query)
        return [dict(row) for row in rows]

    async def get_recent_feature_bundle_sequence(
        self,
        bundle_id: str,
        limit: int = 2,
    ) -> list[dict]:
        query = f"""
        SELECT sequence_id, produced_at, bundle_status FROM btc_feature_bundles
        WHERE bundle_id = '{bundle_id}'
        ORDER BY sequence_id DESC, produced_at DESC
        LIMIT {limit};
        """
        rows = await self.fetch(query)
        return [dict(row) for row in rows]

    async def get_latest_signal_snapshot(self) -> dict | None:
        query = """
        SELECT * FROM btc_signal_snapshots 
        WHERE schema_version = 'v1'
        ORDER BY sequence_id DESC, produced_at DESC
        LIMIT 1;
        """
        row = await self.fetchrow(query)
        if not row:
            return None
        return dict(row)

    async def get_signal_snapshot_history(
        self,
        limit: int,
        after_sequence_id: int | None = None,
    ) -> list[dict]:
        sequence_filter = (
            f"AND sequence_id > {after_sequence_id}"
            if after_sequence_id is not None
            else ""
        )
        query = f"""
        SELECT * FROM btc_signal_snapshots
        WHERE schema_version = 'v1'
        {sequence_filter}
        ORDER BY sequence_id ASC, produced_at ASC
        LIMIT {limit};
        """
        rows = await self.fetch(query)
        return [dict(row) for row in rows]

    async def get_recent_signal_sequence(self, limit: int = 2) -> list[dict]:
        query = f"""
        SELECT sequence_id, produced_at, service_status FROM btc_signal_snapshots
        WHERE schema_version = 'v1'
        ORDER BY sequence_id DESC, produced_at DESC
        LIMIT {limit};
        """
        rows = await self.fetch(query)
        return [dict(row) for row in rows]

    async def get_entity_metadata(self, entity_id: str) -> dict | None:
        query = """
        SELECT *
        FROM entity_registry_serving
        WHERE entity_id = $1
        ORDER BY ts DESC
        LIMIT 1;
        """
        row = await self.fetchrow(query, entity_id)
        return dict(row) if row else None

    async def get_entity_provenance(self, entity_id: str) -> dict | None:
        query = """
        SELECT *
        FROM entity_provenance_serving
        WHERE entity_id = $1
        ORDER BY ts DESC
        LIMIT 1;
        """
        row = await self.fetchrow(query, entity_id)
        return dict(row) if row else None

    async def get_entity_flows(
        self,
        *,
        min_value: float = 0.0,
        classification: str | None = None,
        entity_id: str | None = None,
        limit: int = 50,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        after_window_start: datetime | None = None,
    ) -> list[dict]:
        filters = ["ABS(btc_amount) >= $1"]
        args: list[Any] = [float(min_value)]

        if classification is not None:
            filters.append(f"movement_classification = ${len(args) + 1}")
            args.append(classification)

        if entity_id is not None:
            placeholder = len(args) + 1
            filters.append(
                f"(source_entity_id = ${placeholder} OR target_entity_id = ${placeholder})"
            )
            args.append(entity_id)

        if window_start is not None:
            filters.append(f"window_start >= ${len(args) + 1}")
            args.append(window_start)

        if window_end is not None:
            filters.append(f"window_end <= ${len(args) + 1}")
            args.append(window_end)

        if after_window_start is not None:
            filters.append(f"window_start > ${len(args) + 1}")
            args.append(after_window_start)

        args.append(int(limit))
        query = f"""
        SELECT *
        FROM entity_counterparty_edges_daily
        WHERE {" AND ".join(filters)}
        ORDER BY window_start ASC, source_entity_id ASC, target_entity_id ASC
        LIMIT ${len(args)};
        """
        rows = await self.fetch(query, *args)
        return [dict(row) for row in rows]

    async def get_entity_history(
        self,
        entity_id: str,
        limit: int = 50,
        after_date: datetime | None = None,
    ) -> list[dict]:
        filters = ["entity_id = $1"]
        args: list[Any] = [entity_id]
        if after_date is not None:
            filters.append(f"date > ${len(args) + 1}")
            args.append(after_date)
        args.append(int(limit))
        query = f"""
        WITH latest_registry AS (
            SELECT
                registry_status,
                confidence_overall
            FROM entity_registry_serving
            WHERE entity_id = $1
            ORDER BY ts DESC
            LIMIT 1
        ),
        latest_provenance AS (
            SELECT
                primary_source_kind,
                review_status,
                ts AS provenance_ts
            FROM entity_provenance_serving
            WHERE entity_id = $1
            ORDER BY ts DESC
            LIMIT 1
        )
        SELECT
            b.entity_id,
            b.date AS as_of,
            b.balance_btc,
            r.registry_status,
            r.confidence_overall,
            p.primary_source_kind,
            p.review_status,
            p.provenance_ts
        FROM entity_balance_snapshots_daily AS b
        LEFT JOIN latest_registry AS r ON TRUE
        LEFT JOIN latest_provenance AS p ON TRUE
        WHERE {" AND ".join(f"b.{f}" if f.startswith("date") else f for f in filters)}
        ORDER BY b.date ASC, b.entity_id ASC
        LIMIT ${len(args)};
        """
        rows = await self.fetch(query, *args)
        return [dict(row) for row in rows]
