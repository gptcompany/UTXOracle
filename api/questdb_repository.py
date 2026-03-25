"""
Repository for interacting with QuestDB.
"""

import os
import logging
from questdb.ingress import Sender
import asyncpg
from api.models.data import WhaleTransaction, NetFlowMetrics, Alert
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

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


QUESTDB_POOL_MIN_SIZE = int(os.getenv("QUESTDB_POOL_MIN_SIZE", "5"))
QUESTDB_POOL_MAX_SIZE = int(os.getenv("QUESTDB_POOL_MAX_SIZE", "20"))


async def create_tables_if_not_exist():
    """
    Creates the necessary tables in QuestDB if they do not already exist.
    """
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
                is_valid BOOLEAN,
                created_at TIMESTAMP
            ) timestamp(ts) PARTITION BY DAY;
            """
        )

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
            ) timestamp(ts) PARTITION BY DAY;
            """
        )

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
            ) timestamp(ts) PARTITION BY YEAR;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mvrv_daily (
                ts TIMESTAMP,
                mvrv DOUBLE,
                mvrv_z DOUBLE,
                market_cap DOUBLE,
                realized_cap DOUBLE,
                created_at TIMESTAMP
            ) timestamp(ts) PARTITION BY YEAR;
            """
        )

        # Entity Clustering
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS address_clusters (
                address STRING,
                cluster_id STRING,
                ts TIMESTAMP,
                last_seen TIMESTAMP,
                is_exchange_likely BOOLEAN,
                label SYMBOL
            ) timestamp(ts) PARTITION BY YEAR;
            """
        )

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

    _pool: Optional[asyncpg.Pool] = None

    def __init__(self):
        """
        Initializes the QuestDB repository.
        """
        import time
        self.ilp_host = QUESTDB_ILP_HOST
        self.ilp_port = QUESTDB_ILP_PORT
        # The Sender is thread-safe and intended to be long-lived.
        self.sender = Sender('tcp', self.ilp_host, self.ilp_port)
        self._unflushed_rows = 0
        self._last_flush_time = time.time()
        self._flush_batch_size = 100
        self._flush_interval_seconds = 5.0

    async def initialize(self):
        """
        Initializes the database by creating tables and establishing a connection pool.
        """
        await create_tables_if_not_exist()
        
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
                )
                logger.info(f"QuestDB PG pool initialized (min={QUESTDB_POOL_MIN_SIZE}, max={QUESTDB_POOL_MAX_SIZE})")
            except Exception as e:
                logger.critical(f"Failed to create QuestDB PG connection pool: {e}")
                raise

    async def close(self):
        """Closes the connection pool and flushes pending data."""
        # Flush ILP sender before closing
        try:
            await self.async_flush_ingestion()
        except Exception as e:
            logger.error(f"Error flushing ILP sender on shutdown: {e}")

        if QuestDBRepository._pool:
            try:
                await QuestDBRepository._pool.close()
            except Exception as e:
                logger.error(f"Error closing QuestDB connection pool: {e}")
            finally:
                QuestDBRepository._pool = None

    # --- Write Path (ILP Ingestion) ---

    def _send_row(self, table: str, symbols: Dict[str, Any], columns: Dict[str, Any], at: Optional[Union[datetime, int]] = None, flush: bool = False):
        """
        Helper to send a row via ILP.
        Performance optimization: flush is False by default to allow buffering, but an automatic flush is triggered if batch size or time interval is exceeded.
        """
        import time
        try:
            self.sender.row(table, symbols=symbols, columns=columns, at=at)
            self._unflushed_rows += 1
            now = time.time()
            
            if flush or self._unflushed_rows >= self._flush_batch_size or (now - self._last_flush_time) >= self._flush_interval_seconds:
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
        try:
            if self._unflushed_rows > 0:
                self.sender.flush()
                self._unflushed_rows = 0
                self._last_flush_time = time.time()
            return True
        except Exception as e:
            logger.error(f"Failed to flush QuestDB sender: {e}")
            return False

    async def async_send_row(self, table: str, symbols: Dict[str, Any], columns: Dict[str, Any], at: Optional[Union[datetime, int]] = None, flush: bool = False):
        """Async wrapper for _send_row using run_in_executor to prevent event loop blocking."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, 
            lambda: self._send_row(table, symbols, columns, at, flush)
        )

    async def async_flush_ingestion(self):
        """Async wrapper for flush_ingestion."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.flush_ingestion)

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
                "predicted_confirmation_block": data.get("predicted_confirmation_block"),
                "exchange_addresses": str(data.get("exchange_addresses", "")),
                "confidence_score": float(data.get("confidence_score", 0.0)) if data.get("confidence_score") is not None else None,
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
                "largest_tx_btc": float(metrics.largest_tx_btc) if metrics.largest_tx_btc else None,
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
            at=ts
        )

    # --- Read Path (PostgreSQL Wire Protocol) ---

    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        """Fetch multiple rows via PG pool."""
        if not self._pool:
            await self.initialize()
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
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

    async def get_latest_price_analysis(self) -> Optional[asyncpg.Record]:
        """Get latest price analysis entry."""
        return await self.fetchrow("SELECT * FROM price_analysis ORDER BY ts DESC LIMIT 1")

    async def get_latest_metrics(self) -> Optional[asyncpg.Record]:
        """Get the most recent metrics entry."""
        return await self.fetchrow("SELECT * FROM metrics ORDER BY ts DESC LIMIT 1")

    async def get_historical_price_analysis(self, days: int = 7) -> List[asyncpg.Record]:
        """Get historical price analysis entries."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        return await self.fetch(
            "SELECT * FROM price_analysis WHERE ts > $1 ORDER BY ts ASC",
            cutoff
        )

    async def update_utxo_spent(self, outpoint: str, spend_data: Dict[str, Any]) -> bool:
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
                outpoint
            )
            return True
        except Exception as e:
            logger.error(f"Error updating UTXO {outpoint}: {e}")
            return False

    async def get_utxo(self, outpoint: str) -> Optional[asyncpg.Record]:
        """Get UTXO by outpoint."""
        return await self.fetchrow("SELECT * FROM utxo_lifecycle WHERE outpoint = $1", outpoint)

    async def get_supply_metrics_latest(self) -> Optional[asyncpg.Record]:
        """Get latest supply metrics from snapshots."""
        return await self.fetchrow("SELECT * FROM utxo_snapshots ORDER BY ts DESC LIMIT 1")

    async def get_metrics_latest(self) -> Optional[asyncpg.Record]:
        """Get latest general metrics."""
        return await self.fetchrow("SELECT * FROM metrics ORDER BY ts DESC LIMIT 1")

    async def get_cointime_latest(self) -> Optional[asyncpg.Record]:
        """Get latest cointime metrics."""
        return await self.fetchrow("SELECT * FROM cointime_metrics ORDER BY ts DESC LIMIT 1")

    async def get_exchange_netflow(self, window_hours: int = 24) -> Optional[Dict[str, Any]]:
        """
        Calculate exchange netflow using QuestDB's SQL.
        Performance tuning: Use QuestDB's time-series functions.
        """
        # simplified version for migration
        cutoff = datetime.utcnow() - timedelta(hours=window_hours)
        query = """
        SELECT sum(btc_value) as inflow
        FROM utxo_lifecycle u
        WHERE u.ts > $1
        """
        # This would be expanded with actual exchange address filtering
        return None
