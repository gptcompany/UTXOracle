#!/usr/bin/env python3
"""Diagnose why /v1/streams/health reports DEGRADED.

Audits each of the 13 contractual streams against:

1. Whether the backing QuestDB table exists.
2. Whether it has any rows (MISSING vs STALE).
3. Whether its DuckDB source (when applicable) is fresh enough to
   produce new rows.

Useful when the operator sees DEGRADED and wants a one-shot report of
which producers are silent vs which streams are simply behind tip.

Usage:
    uv run python -m scripts.diagnose_streams_health
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
_REGISTRY_PATH = REPO_ROOT / "docs" / "contracts" / "stream_registry.yaml"


def _bitcoin_tip() -> int | None:
    try:
        return int(
            subprocess.check_output(
                ["bitcoin-cli", "getblockcount"], text=True, timeout=10
            ).strip()
        )
    except Exception:
        return None


async def _questdb_state(table: str, timestamp_column: str | None) -> dict:
    """Return per-table state: row count + max timestamp (when applicable)."""
    import asyncpg

    try:
        conn = await asyncio.wait_for(
            asyncpg.connect(
                host=os.getenv("QUESTDB_PG_HOST", "localhost"),
                port=int(os.getenv("QUESTDB_PG_PORT", 8812)),
                user=os.getenv("QUESTDB_PG_USER", "admin"),
                password=os.getenv("QUESTDB_PG_PASSWORD", "quest"),
                database=os.getenv("QUESTDB_PG_DATABASE", "qdb"),
            ),
            timeout=3,
        )
    except Exception as exc:
        return {"error": f"connect: {exc}"}

    try:
        result: dict = {}
        try:
            cnt = await asyncio.wait_for(
                conn.fetchval(f"SELECT count(*) FROM {table}"), timeout=60
            )
        except asyncio.TimeoutError:
            return {"error": "count(*) timed out after 60s (table likely huge)"}
        except Exception as exc:
            msg = str(exc).strip()
            tag = "missing" if "does not exist" in msg.lower() else "unreadable"
            return {"error": f"table {tag}: {msg or type(exc).__name__}"}
        result["count"] = int(cnt or 0)
        if timestamp_column and cnt:
            try:
                ts = await asyncio.wait_for(
                    conn.fetchval(f"SELECT max({timestamp_column}) FROM {table}"),
                    timeout=60,
                )
                result["max_ts"] = ts.isoformat() if ts else None
            except Exception as exc:
                result["max_ts_error"] = str(exc) or type(exc).__name__
        return result
    finally:
        await conn.close()


async def _duckdb_freshness() -> dict:
    """Best-effort read of the producer-side DuckDB tables for daily metrics."""
    try:
        import duckdb
    except Exception as exc:
        return {"error": f"duckdb import: {exc}"}

    duck_path = REPO_ROOT / "data" / "utxoracle.duckdb"
    if not duck_path.exists():
        return {"error": f"missing {duck_path}"}

    def _query():
        result: dict = {}
        try:
            conn = duckdb.connect(str(duck_path), read_only=True)
        except Exception as exc:
            result["error"] = f"duckdb open: {exc}"
            return result
        try:
            try:
                row = conn.execute(
                    "SELECT min(timestamp), max(timestamp), count(*) "
                    "FROM block_heights"
                ).fetchone()
                if row:
                    result["block_heights"] = {
                        "count": int(row[2]),
                        "min_ts": datetime.fromtimestamp(
                            int(row[0]), tz=timezone.utc
                        ).isoformat() if row[0] is not None else None,
                        "max_ts": datetime.fromtimestamp(
                            int(row[1]), tz=timezone.utc
                        ).isoformat() if row[1] is not None else None,
                    }
            except Exception as exc:
                result["block_heights_error"] = str(exc)
            try:
                row = conn.execute(
                    "SELECT min(date), max(date), count(*) FROM daily_prices"
                ).fetchone()
                if row:
                    result["daily_prices"] = {
                        "count": int(row[2]),
                        "min_date": str(row[0]) if row[0] else None,
                        "max_date": str(row[1]) if row[1] else None,
                    }
            except Exception as exc:
                result["daily_prices_error"] = str(exc)
        finally:
            conn.close()
        return result

    # Run in thread to avoid blocking the event loop.
    return await asyncio.to_thread(_query)


async def main() -> int:
    registry = yaml.safe_load(_REGISTRY_PATH.read_text())
    streams = registry["streams"]
    tip = _bitcoin_tip()

    print(f"Bitcoin tip: {tip}")
    print()
    print("-- Per-stream QuestDB state --")
    print(f"{'stream':<25} {'rows':>15} {'max_ts / max_block':<30}")
    print("-" * 75)

    rollup_missing: list[str] = []
    rollup_stale: list[str] = []

    for s in streams:
        name = s["name"]
        table = s["table"]
        strategy = s["freshness_strategy"]
        ts_col = s.get("timestamp_column") if strategy == "max_ts" else None
        state = await _questdb_state(table, ts_col)

        cnt = state.get("count", "?")
        if "error" in state:
            print(f"  {name:<23} ERROR: {state['error'][:50]}")
            rollup_missing.append(name)
            continue

        if cnt == 0:
            print(f"  {name:<23} {cnt:>15} (empty -> MISSING)")
            rollup_missing.append(name)
            continue

        if strategy == "tip_lag_blocks":
            # Probe both columns for diagnostic completeness.
            from scripts.bootstrap.tip_spent_backfill_via_rpc import _open_questdb_pg  # noqa

            block_cols = s.get("block_columns") or [s.get("block_column", "spent_block")]
            with _open_questdb_pg() as pg:
                with pg.cursor() as cur:
                    parts = []
                    for c in block_cols:
                        cur.execute(f"SELECT max({c}) FROM utxo_lifecycle")
                        row = cur.fetchone()
                        parts.append(f"{c}={row[0] if row else None}")
            tip_str = f"tip={tip} | " + " ".join(parts)
            print(f"  {name:<23} {cnt:>15} {tip_str}")
            if tip is not None and block_cols:
                worst_lag_blocks = None
                with _open_questdb_pg() as pg:
                    with pg.cursor() as cur:
                        for c in block_cols:
                            cur.execute(f"SELECT max({c}) FROM utxo_lifecycle")
                            row = cur.fetchone()
                            if row and row[0] is not None:
                                lag = tip - int(row[0])
                                worst_lag_blocks = lag if worst_lag_blocks is None else max(worst_lag_blocks, lag)
                sla = int(s["sla_seconds"])
                if worst_lag_blocks is not None and worst_lag_blocks * 600 > sla:
                    rollup_stale.append(
                        f"{name} (lag={worst_lag_blocks}b={worst_lag_blocks*600}s > sla={sla}s)"
                    )
            continue

        max_ts = state.get("max_ts")
        print(f"  {name:<23} {cnt:>15} {max_ts}")
        if max_ts:
            try:
                dt = datetime.fromisoformat(max_ts)
                lag = (datetime.now(timezone.utc) - dt).total_seconds()
                if lag > int(s["sla_seconds"]):
                    rollup_stale.append(f"{name} (lag={int(lag)}s > sla={s['sla_seconds']}s)")
            except Exception:
                pass

    print()
    print("-- DuckDB upstream producer freshness --")
    duck = await _duckdb_freshness()
    if "error" in duck:
        print(f"  ERROR: {duck['error']}")
    else:
        if "block_heights" in duck:
            print(f"  block_heights: {duck['block_heights']}")
        if "daily_prices" in duck:
            print(f"  daily_prices: {duck['daily_prices']}")

    print()
    print("-- Rollup --")
    print(f"  MISSING ({len(rollup_missing)}): {rollup_missing}")
    print(f"  STALE   ({len(rollup_stale)}): {rollup_stale}")
    print(
        f"  Implied overall: "
        f"{'OK' if not rollup_missing and not rollup_stale else 'DEGRADED'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
