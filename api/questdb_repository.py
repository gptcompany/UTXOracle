"""
Repository for interacting with QuestDB.
"""

import os
import logging
from api.models.data import WhaleTransaction, NetFlowMetrics, Alert
from scripts.models.metrics_models import (
    WalletWavesResult,
    AbsorptionRatesResult,
    AddressCohortsResult,
)
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta

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


QUESTDB_POOL_MIN_SIZE = int(os.getenv("QUESTDB_POOL_MIN_SIZE", "5"))
QUESTDB_POOL_MAX_SIZE = int(os.getenv("QUESTDB_POOL_MAX_SIZE", "20"))


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
                created_at TIMESTAMP
            ) timestamp(ts) PARTITION BY DAY;
            """
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
                label SYMBOL,
                confidence DOUBLE
            ) timestamp(ts) PARTITION BY YEAR;
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS address_clusters_staging (
                address STRING,
                cluster_id STRING,
                ts TIMESTAMP,
                last_seen TIMESTAMP,
                is_exchange_likely BOOLEAN,
                label SYMBOL,
                confidence DOUBLE
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

    def _build_sender(self):
        if Sender is None:
            raise ModuleNotFoundError(
                "questdb package is required for ILP ingestion; install project dependencies "
                "or monkeypatch QuestDBRepository._build_sender in tests"
            )
        sender = Sender("tcp", self.ilp_host, self.ilp_port)
        sender.establish()
        return sender

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
                logger.critical(f"Failed to create QuestDB PG connection pool: {e}")
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

    def _send_row(self, table: str, symbols: Dict[str, Any], columns: Dict[str, Any], at: Optional[Union[datetime, int]] = None, flush: bool = False):
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
                logger.warning("QuestDB sender was closed; recreating sender and retrying once")
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
            logger.warning("Skipping QuestDB sender flush because ingestion was aborted")
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

    async def async_send_row(self, table: str, symbols: Dict[str, Any], columns: Dict[str, Any], at: Optional[Union[datetime, int]] = None, flush: bool = False):
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
                    "absorption_rate": float(band_metrics.absorption_rate) if band_metrics.absorption_rate is not None else None,
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

        return self._send_row(
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

    async def prepare_address_clusters_refresh(self) -> bool:
        """
        Clear the staging table before loading a new full-refresh snapshot.

        The live table is left untouched until commit succeeds.
        """
        try:
            await self.execute(f"TRUNCATE TABLE {ADDRESS_CLUSTERS_STAGING_TABLE}")
            logger.info("Prepared QuestDB address_clusters staging table.")
            return True
        except Exception as e:
            logger.error(f"Failed to prepare address_clusters staging table: {e}")
            return False

    async def _truncate_address_clusters_table(self, table: str, *, reason: str) -> None:
        try:
            await self.execute(f"TRUNCATE TABLE {table}")
        except Exception as e:
            logger.error("Failed to truncate %s during %s: %s", table, reason, e)

    async def abort_address_clusters_refresh(self, *, clear_target: bool = False) -> None:
        """
        Abort a staged refresh and clean up any staged rows.

        `clear_target=True` is used only after a cutover failure to avoid serving a
        partially rebuilt snapshot.
        """
        self.abort_ingestion()
        await self._truncate_address_clusters_table(
            ADDRESS_CLUSTERS_STAGING_TABLE,
            reason="address_clusters refresh abort",
        )
        if clear_target:
            await self._truncate_address_clusters_table(
                ADDRESS_CLUSTERS_TABLE,
                reason="address_clusters cutover recovery",
            )

    async def commit_address_clusters_refresh(self) -> bool:
        """
        Publish a staged address_clusters snapshot after the ILP load completes.
        """
        if not await self.async_flush_ingestion():
            logger.error("Failed to flush staged address_clusters rows before cutover.")
            await self.abort_address_clusters_refresh()
            return False

        try:
            await self.execute(f"TRUNCATE TABLE {ADDRESS_CLUSTERS_TABLE}")
            await self.execute(
                f"""
                INSERT INTO {ADDRESS_CLUSTERS_TABLE}
                SELECT
                    address,
                    cluster_id,
                    ts,
                    last_seen,
                    is_exchange_likely,
                    label,
                    confidence
                FROM {ADDRESS_CLUSTERS_STAGING_TABLE}
                """
            )
            await self.execute(f"TRUNCATE TABLE {ADDRESS_CLUSTERS_STAGING_TABLE}")
            logger.info("Committed staged address_clusters refresh in QuestDB.")
            return True
        except Exception as e:
            logger.error(f"Failed to commit staged address_clusters refresh: {e}")
            await self.abort_address_clusters_refresh(clear_target=True)
            return False

    async def save_address_clusters_bulk(self, rows: List[Dict[str, Any]]) -> bool:
        """
        Stage and publish a full address_clusters refresh via ILP and PG cutover.
        """
        if not await self.prepare_address_clusters_refresh():
            return False

        for row in rows:
            row_success = self.stage_address_cluster(row)
            if not row_success:
                await self.abort_address_clusters_refresh()
                return False

        return await self.commit_address_clusters_refresh()

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
        return await self.fetchrow("SELECT * FROM price_analysis ORDER BY ts DESC LIMIT 1")

    async def get_latest_metrics(self) -> Optional[AsyncpgRecord]:
        """Get the most recent metrics entry."""
        return await self.fetchrow("SELECT * FROM metrics ORDER BY ts DESC LIMIT 1")

    async def get_historical_price_analysis(self, days: int = 7) -> List[AsyncpgRecord]:
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

    async def get_utxo(self, outpoint: str) -> Optional[AsyncpgRecord]:
        """Get UTXO by outpoint."""
        return await self.fetchrow("SELECT * FROM utxo_lifecycle WHERE outpoint = $1", outpoint)

    async def get_supply_metrics_latest(self) -> Optional[AsyncpgRecord]:
        """Get latest supply metrics from snapshots."""
        return await self.fetchrow("SELECT * FROM utxo_snapshots ORDER BY ts DESC LIMIT 1")

    async def get_metrics_latest(self) -> Optional[AsyncpgRecord]:
        """Get latest general metrics."""
        return await self.fetchrow("SELECT * FROM metrics ORDER BY ts DESC LIMIT 1")

    async def get_cointime_latest(self) -> Optional[AsyncpgRecord]:
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

    async def get_absorption_rates_latest(self, window_days: int = 30) -> List[AsyncpgRecord]:
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
        SELECT * FROM cost_basis_daily LATEST ON ts;
        """
        return await self.fetch_row(query)
