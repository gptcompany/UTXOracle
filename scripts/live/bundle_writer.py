from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from api.models.questdb import (
    AbsorptionRateMetricsResponse,
    AbsorptionRatesResponse,
    ActiveAddressesResponse,
    AddressCohortsResponse,
    CohortMetricsResponse,
    CostBasisResponse,
    MetricsLatestResponse,
    MonteCarloFusionResponse,
    TxVolumeResponse,
    WalletBandMetricsResponse,
    WalletWavesResponse,
)
from api.questdb_repository import QuestDBRepository
from scripts.live.models import LiveSnapshot

logger = logging.getLogger(__name__)

CORE_BUNDLE_ID = "btc_core_live.v1"
FLOW_BUNDLE_ID = "btc_flow.v1"
MACRO_BUNDLE_ID = "btc_macro.v1"
COHORT_BUNDLE_ID = "btc_cohort.v1"

DEFAULT_FLOW_WINDOW_HOURS = int(os.getenv("BTC_FLOW_WINDOW_HOURS", "1"))
DEFAULT_FLOW_SUMMARY_HOURS = int(os.getenv("BTC_FLOW_SUMMARY_HOURS", "24"))
DEFAULT_ABSORPTION_WINDOW_DAYS = int(os.getenv("BTC_BUNDLE_ABSORPTION_WINDOW_DAYS", "30"))
WAVE1_STALE_AFTER = timedelta(hours=48)
BRK_STALE_AFTER = timedelta(hours=24)


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _as_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return None


def _is_stale(value: Any, threshold: timedelta, *, now: datetime) -> bool:
    ts = _as_utc(value)
    if ts is None:
        return False
    return now - ts > threshold


def _parse_exchange_addresses(raw_addresses: str | None) -> list[str]:
    if not raw_addresses:
        return []
    return [
        address
        for address in {part.strip() for part in raw_addresses.split(",")}
        if address
    ]


class BundleWriter:
    def __init__(
        self,
        repo: QuestDBRepository,
        *,
        flow_window_hours: int = DEFAULT_FLOW_WINDOW_HOURS,
        flow_summary_hours: int = DEFAULT_FLOW_SUMMARY_HOURS,
        absorption_window_days: int = DEFAULT_ABSORPTION_WINDOW_DAYS,
    ) -> None:
        self.repo = repo
        self.flow_window_hours = max(flow_window_hours, 1)
        self.flow_summary_hours = max(flow_summary_hours, 1)
        self.absorption_window_days = max(absorption_window_days, 1)

    async def write_bundles(self, snapshot: LiveSnapshot) -> list[str]:
        produced_at = datetime.now(timezone.utc)
        bundle_rows = await self._build_bundle_rows(snapshot, produced_at=produced_at)
        written_bundle_ids: list[str] = []

        for bundle_id, payload in bundle_rows:
            metadata = payload["metadata"]
            success = await self.repo.async_send_row(
                "btc_feature_bundles",
                symbols={
                    "bundle_id": bundle_id,
                    "bundle_status": metadata["bundle_status"],
                },
                columns={
                    "sequence_id": metadata["sequence_id"],
                    "produced_at": produced_at,
                    "degraded_reasons": json.dumps(
                        metadata["degraded_reasons"], sort_keys=True
                    ),
                    "payload_json": json.dumps(payload, sort_keys=True),
                    "ts": produced_at,
                },
                at=produced_at,
            )
            if success:
                written_bundle_ids.append(bundle_id)
            else:
                logger.error("Failed to write feature bundle %s", bundle_id)

        if written_bundle_ids:
            await self.repo.async_flush_ingestion()
        return written_bundle_ids

    async def _build_bundle_rows(
        self,
        snapshot: LiveSnapshot,
        *,
        produced_at: datetime,
    ) -> list[tuple[str, dict[str, Any]]]:
        core_payload = await self._build_core_bundle(snapshot, produced_at=produced_at)
        flow_payload = await self._build_flow_bundle(produced_at=produced_at)
        macro_payload = await self._build_macro_bundle(snapshot, produced_at=produced_at)
        cohort_payload = await self._build_cohort_bundle(produced_at=produced_at)

        return [
            (CORE_BUNDLE_ID, core_payload),
            (FLOW_BUNDLE_ID, flow_payload),
            (MACRO_BUNDLE_ID, macro_payload),
            (COHORT_BUNDLE_ID, cohort_payload),
        ]

    async def _build_core_bundle(
        self,
        snapshot: LiveSnapshot,
        *,
        produced_at: datetime,
    ) -> dict[str, Any]:
        now = produced_at
        degraded_reasons: list[str] = []
        stale = False

        metrics_row = await self.repo.get_latest_metrics()
        metrics_payload: dict[str, Any] = {}
        if metrics_row:
            metrics_payload = MetricsLatestResponse(
                timestamp=metrics_row["ts"],
                monte_carlo=MonteCarloFusionResponse(
                    signal_mean=metrics_row["signal_mean"],
                    signal_std=metrics_row["signal_std"],
                    ci_lower=metrics_row["ci_lower"],
                    ci_upper=metrics_row["ci_upper"],
                    action=metrics_row["action"],
                    action_confidence=metrics_row["action_confidence"],
                    n_samples=metrics_row["n_samples"],
                    distribution_type=metrics_row["distribution_type"],
                ),
                active_addresses=ActiveAddressesResponse(
                    block_height=metrics_row["block_height"],
                    active_addresses_block=metrics_row["active_addresses_block"],
                    active_addresses_24h=metrics_row["active_addresses_24h"],
                    unique_senders=metrics_row["unique_senders"],
                    unique_receivers=metrics_row["unique_receivers"],
                    is_anomaly=metrics_row["is_anomaly"],
                ),
                tx_volume=TxVolumeResponse(
                    tx_count=metrics_row["tx_count"],
                    tx_volume_btc=metrics_row["tx_volume_btc"],
                    tx_volume_usd=metrics_row["tx_volume_usd"],
                    utxoracle_price_used=metrics_row["utxoracle_price_used"],
                    low_confidence=metrics_row["low_confidence"],
                ),
            ).model_dump(mode="json")

        for source_name, health in snapshot.source_health.items():
            if health.status == "stale":
                stale = True
            elif health.status in {"degraded", "unavailable"}:
                degraded_reasons.append(f"{source_name} source is {health.status}")

        has_live_snapshot = (
            snapshot.block_height is not None or snapshot.utxoracle_price is not None
        )
        status = self._resolve_bundle_status(
            has_any_data=has_live_snapshot or bool(metrics_payload),
            degraded_reasons=degraded_reasons,
            stale=stale,
        )

        payload = {
            "metadata": await self._build_metadata(
                bundle_id=CORE_BUNDLE_ID,
                produced_at=produced_at,
                bundle_status=status,
                degraded_reasons=degraded_reasons,
            ),
            "live_snapshot": {
                "timestamp": snapshot.timestamp.isoformat(),
                "block_height": snapshot.block_height,
                "utxoracle_price": snapshot.utxoracle_price,
                "utxoracle_confidence": snapshot.utxoracle_confidence,
                "mempool_exchange_price": snapshot.mempool_exchange_price,
                "hyperliquid_oracle_price": snapshot.hyperliquid_oracle_price,
                "hyperliquid_mark_price": snapshot.hyperliquid_mark_price,
                "comparison": snapshot.comparison.model_dump(mode="json"),
                "source_health": {
                    source_name: health.model_dump(mode="json")
                    for source_name, health in snapshot.source_health.items()
                },
                "source_timestamps": {
                    source_name: _isoformat(value)
                    for source_name, value in snapshot.source_timestamps.items()
                },
            },
            "metrics_latest": metrics_payload,
        }
        return payload

    async def _build_flow_bundle(self, *, produced_at: datetime) -> dict[str, Any]:
        now = produced_at
        degraded_reasons: list[str] = []
        stale = False

        whale_summary = await self._build_whale_summary(now=now)
        recent_whale_window = await self._build_recent_whale_window(now=now)
        absorption_payload, _absorption_ts = await self._build_flow_absorption_copy()

        has_any_data = bool(whale_summary) or bool(absorption_payload)
        status = self._resolve_bundle_status(
            has_any_data=has_any_data,
            degraded_reasons=degraded_reasons,
            stale=stale,
        )

        return {
            "metadata": await self._build_metadata(
                bundle_id=FLOW_BUNDLE_ID,
                produced_at=produced_at,
                bundle_status=status,
                degraded_reasons=degraded_reasons,
            ),
            "whale_summary": whale_summary,
            "recent_whale_window": recent_whale_window,
            "absorption_rates": absorption_payload,
        }

    async def _build_macro_bundle(
        self,
        snapshot: LiveSnapshot,
        *,
        produced_at: datetime,
    ) -> dict[str, Any]:
        now = produced_at
        degraded_reasons: list[str] = []
        missing_metrics: list[str] = []
        brk_health = snapshot.source_health.get("brk")
        brk_timestamp = snapshot.source_timestamps.get("brk")
        stale = False

        macro_metrics = {
            "realized_price_usd": snapshot.features.brk_realized_price,
            "liveliness": snapshot.features.brk_liveliness,
            "reserve_risk": snapshot.features.brk_reserve_risk,
            "nupl": snapshot.features.brk_nupl,
            "sopr": snapshot.features.brk_sopr,
        }
        for metric_name, value in macro_metrics.items():
            if value is None:
                missing_metrics.append(metric_name)

        if brk_health is None:
            degraded_reasons.append("BRK source health unavailable")
        else:
            if brk_health.status == "stale":
                stale = True
            elif brk_health.status in {"degraded", "unavailable"}:
                degraded_reasons.append(f"BRK source is {brk_health.status}")

        if _is_stale(brk_timestamp, BRK_STALE_AFTER, now=now):
            stale = True
            degraded_reasons.append("BRK source timestamp is stale")

        if missing_metrics:
            degraded_reasons.append(
                "missing BRK metrics: " + ", ".join(sorted(missing_metrics))
            )

        status = self._resolve_bundle_status(
            has_any_data=any(value is not None for value in macro_metrics.values()),
            degraded_reasons=degraded_reasons,
            stale=stale,
        )

        return {
            "metadata": await self._build_metadata(
                bundle_id=MACRO_BUNDLE_ID,
                produced_at=produced_at,
                bundle_status=status,
                degraded_reasons=degraded_reasons,
            ),
            "macro_metrics": macro_metrics,
            "source_metadata": {
                "source": "BRK",
                "source_timestamp": _isoformat(brk_timestamp),
                "source_health": brk_health.model_dump(mode="json")
                if brk_health is not None
                else None,
                "missing_metrics": missing_metrics,
            },
        }

    async def _build_cohort_bundle(self, *, produced_at: datetime) -> dict[str, Any]:
        now = produced_at
        degraded_reasons: list[str] = []
        stale = False

        address_cohorts_payload, address_cohorts_ts = await self._safe_component_build(
            "address_cohorts",
            self._build_address_cohorts,
            degraded_reasons,
            blocking=False,
        )
        wallet_waves_payload, wallet_waves_ts = await self._safe_component_build(
            "wallet_waves",
            self._build_wallet_waves,
            degraded_reasons,
            blocking=False,
        )
        absorption_payload, absorption_ts = await self._safe_component_build(
            "absorption_rates",
            self._build_absorption_rates,
            degraded_reasons,
            blocking=False,
        )
        cost_basis_payload, cost_basis_ts = await self._safe_component_build(
            "cost_basis",
            self._build_cost_basis,
            degraded_reasons,
        )

        for component_name, payload, component_ts in (
            ("address_cohorts", address_cohorts_payload, address_cohorts_ts),
            ("wallet_waves", wallet_waves_payload, wallet_waves_ts),
            ("absorption_rates", absorption_payload, absorption_ts),
            ("cost_basis", cost_basis_payload, cost_basis_ts),
        ):
            if not payload:
                if component_name == "cost_basis" and f"{component_name} unavailable" not in degraded_reasons:
                    degraded_reasons.append(f"{component_name} unavailable")
                continue
            if _is_stale(component_ts, WAVE1_STALE_AFTER, now=now):
                if component_name == "cost_basis":
                    stale = True
                    if f"{component_name} is stale" not in degraded_reasons:
                        degraded_reasons.append(f"{component_name} is stale")

        status = self._resolve_bundle_status(
            has_any_data=bool(cost_basis_payload)
            or any(
                bool(payload)
                for payload in (
                    address_cohorts_payload,
                    wallet_waves_payload,
                    absorption_payload,
                )
            ),
            degraded_reasons=degraded_reasons,
            stale=stale,
        )

        return {
            "metadata": await self._build_metadata(
                bundle_id=COHORT_BUNDLE_ID,
                produced_at=produced_at,
                bundle_status=status,
                degraded_reasons=degraded_reasons,
            ),
            "address_cohorts": address_cohorts_payload,
            "wallet_waves": wallet_waves_payload,
            "absorption_rates": absorption_payload,
            "cost_basis": cost_basis_payload,
        }

    async def _build_metadata(
        self,
        *,
        bundle_id: str,
        produced_at: datetime,
        bundle_status: str,
        degraded_reasons: list[str],
    ) -> dict[str, Any]:
        sequence_id = await self._next_sequence_id(bundle_id)
        return {
            "schema_version": "v1",
            "bundle_id": bundle_id,
            "sequence_id": sequence_id,
            "produced_at": produced_at.isoformat(),
            "bundle_status": bundle_status,
            "degraded_reasons": degraded_reasons,
        }

    async def _next_sequence_id(self, bundle_id: str) -> int:
        latest_row = await self.repo.get_latest_feature_bundle(bundle_id)
        if not latest_row:
            return 1
        return int(latest_row.get("sequence_id", 0)) + 1

    @staticmethod
    def _resolve_bundle_status(
        *,
        has_any_data: bool,
        degraded_reasons: list[str],
        stale: bool,
    ) -> str:
        if not has_any_data:
            return "empty"
        if stale:
            return "stale"
        if degraded_reasons:
            return "degraded"
        return "healthy"

    async def _build_whale_summary(self, *, now: datetime) -> dict[str, Any]:
        cutoff = (now - timedelta(hours=self.flow_summary_hours)).replace(tzinfo=None)
        row = await self.repo.fetchrow(
            """
            SELECT
                COUNT(*) AS total_transactions,
                SUM(btc_value) AS total_btc_volume,
                AVG(urgency_score) AS avg_urgency_score,
                SUM(CASE WHEN urgency_score >= 0.7 THEN 1 ELSE 0 END) AS high_urgency_count,
                SUM(CASE WHEN rbf_enabled = TRUE THEN 1 ELSE 0 END) AS rbf_enabled_count
            FROM mempool_predictions
            WHERE ts >= $1
            """,
            cutoff,
        )
        summary = dict(row) if row else {}
        return {
            "total_transactions": int(summary.get("total_transactions") or 0),
            "total_btc_volume": round(float(summary.get("total_btc_volume") or 0.0), 2),
            "avg_urgency_score": round(
                float(summary.get("avg_urgency_score") or 0.0),
                3,
            ),
            "high_urgency_count": int(summary.get("high_urgency_count") or 0),
            "rbf_enabled_count": int(summary.get("rbf_enabled_count") or 0),
            "entity_enrichment_mode": "best_effort_optional",
            "window_hours": self.flow_summary_hours,
        }

    async def _build_recent_whale_window(self, *, now: datetime) -> dict[str, Any]:
        cutoff = (now - timedelta(hours=self.flow_window_hours)).replace(tzinfo=None)
        rows = await self.repo.fetch(
            """
            SELECT
                ts AS detection_timestamp,
                btc_value,
                flow_type,
                exchange_addresses
            FROM mempool_predictions
            WHERE ts >= $1
            ORDER BY ts DESC
            LIMIT 250
            """,
            cutoff,
        )
        if not rows:
            return {
                "window_hours": self.flow_window_hours,
                "total_transactions": 0,
                "total_btc_volume": 0.0,
                "inflow_btc": 0.0,
                "outflow_btc": 0.0,
                "internal_btc": 0.0,
                "net_flow_btc": 0.0,
                "enriched_event_count": 0,
                "non_enriched_event_count": 0,
                "last_event_timestamp": None,
            }

        all_addresses = sorted(
            {
                address
                for row in rows
                for address in _parse_exchange_addresses(row["exchange_addresses"])
            }
        )
        cluster_rows_by_address = await self._fetch_cluster_rows(all_addresses)

        inflow_btc = 0.0
        outflow_btc = 0.0
        internal_btc = 0.0
        enriched_event_count = 0
        non_enriched_event_count = 0

        for row in rows:
            btc_value = float(row["btc_value"] or 0.0)
            flow_type = str(row["flow_type"] or "unknown").lower()
            if flow_type == "inflow":
                inflow_btc += btc_value
            elif flow_type == "outflow":
                outflow_btc += btc_value
            elif flow_type == "internal":
                internal_btc += btc_value

            exchange_addresses = _parse_exchange_addresses(row["exchange_addresses"])
            if self._has_unambiguous_cluster(exchange_addresses, cluster_rows_by_address):
                enriched_event_count += 1
            else:
                non_enriched_event_count += 1

        last_event_timestamp = max(row["detection_timestamp"] for row in rows)
        return {
            "window_hours": self.flow_window_hours,
            "total_transactions": len(rows),
            "total_btc_volume": round(sum(float(row["btc_value"] or 0.0) for row in rows), 2),
            "inflow_btc": round(inflow_btc, 8),
            "outflow_btc": round(outflow_btc, 8),
            "internal_btc": round(internal_btc, 8),
            "net_flow_btc": round(outflow_btc - inflow_btc, 8),
            "enriched_event_count": enriched_event_count,
            "non_enriched_event_count": non_enriched_event_count,
            "last_event_timestamp": _isoformat(last_event_timestamp),
        }

    async def _fetch_cluster_rows(self, addresses: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not addresses:
            return {}

        placeholders = ", ".join(f"${idx}" for idx in range(1, len(addresses) + 1))
        rows = await self.repo.fetch(
            f"""
            SELECT
                address,
                cluster_id,
                label
            FROM address_clusters
            WHERE address IN ({placeholders})
            """,
            *addresses,
        )
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["address"], []).append(dict(row))
        return grouped

    @staticmethod
    def _has_unambiguous_cluster(
        exchange_addresses: list[str],
        cluster_rows_by_address: dict[str, list[dict[str, Any]]],
    ) -> bool:
        if not exchange_addresses:
            return False
        cluster_ids = {
            row["cluster_id"]
            for address in exchange_addresses
            for row in cluster_rows_by_address.get(address, [])
            if row.get("cluster_id")
        }
        return len(cluster_ids) == 1

    async def _safe_component_build(
        self,
        component_name: str,
        builder,
        degraded_reasons: list[str],
        *,
        blocking: bool = True,
    ) -> tuple[dict[str, Any], Any]:
        try:
            return await builder()
        except Exception as exc:
            logger.warning("Failed to build %s bundle component: %s", component_name, exc)
            if blocking:
                degraded_reasons.append(f"{component_name} unavailable")
            return {}, None

    async def _build_flow_absorption_copy(self) -> tuple[dict[str, Any], Any]:
        rows = await self.repo.get_absorption_rates_latest(self.absorption_window_days)
        if not rows:
            return {}, None
        first = rows[0]
        return (
            {
                "window_days": first["window_days"],
                "dominant_absorber": first["dominant_absorber"],
                "retail_absorption": first["retail_absorption"],
                "institutional_absorption": first["institutional_absorption"],
                "confidence": first["confidence"],
                "has_historical_data": bool(first.get("has_historical_data", True)),
            },
            first["ts"],
        )

    async def _build_address_cohorts(self) -> tuple[dict[str, Any], Any]:
        rows = await self.repo.get_address_cohorts_latest()
        if not rows:
            return {}, None
        heights = {row["block_height"] for row in rows}
        if len(heights) > 1:
            max_height = max(heights)
            rows = [row for row in rows if row["block_height"] == max_height]
        if len(rows) < 3:
            raise ValueError("address_cohorts snapshot is partial")

        first = rows[0]
        cohorts = {
            row["cohort"]: CohortMetricsResponse(
                cohort=row["cohort"],
                cost_basis=row["cost_basis"],
                supply_btc=row["supply_btc"],
                supply_pct=row["supply_pct"],
                mvrv=row["mvrv"],
                address_count=row["address_count"],
            )
            for row in rows
        }
        payload = AddressCohortsResponse(
            timestamp=first["ts"],
            block_height=first["block_height"],
            current_price_usd=first["current_price_usd"],
            cohorts=cohorts,
            whale_retail_spread=first["whale_retail_spread"],
            whale_retail_mvrv_ratio=first["whale_retail_mvrv_ratio"],
            total_supply_btc=first["total_supply_btc"],
            total_addresses=first["total_addresses"],
        ).model_dump(mode="json")
        return payload, first["ts"]

    async def _build_wallet_waves(self) -> tuple[dict[str, Any], Any]:
        rows = await self.repo.get_wallet_waves_latest()
        if not rows:
            return {}, None
        heights = {row["block_height"] for row in rows}
        if len(heights) > 1:
            max_height = max(heights)
            rows = [row for row in rows if row["block_height"] == max_height]
        if len(rows) < 6:
            raise ValueError("wallet_waves snapshot is partial")

        first = rows[0]
        payload = WalletWavesResponse(
            timestamp=first["ts"],
            block_height=first["block_height"],
            total_supply_btc=first["total_supply_btc"],
            bands=[
                WalletBandMetricsResponse(
                    band=row["band"],
                    supply_btc=row["supply_btc"],
                    supply_pct=row["supply_pct"],
                    address_count=row["address_count"],
                    avg_balance=row["avg_balance"],
                )
                for row in rows
            ],
            retail_supply_pct=first["retail_supply_pct"],
            institutional_supply_pct=first["institutional_supply_pct"],
            address_count_total=first["address_count_total"],
            null_address_btc=first["null_address_btc"],
            confidence=first["confidence"],
        ).model_dump(mode="json")
        return payload, first["ts"]

    async def _build_absorption_rates(self) -> tuple[dict[str, Any], Any]:
        rows = await self.repo.get_absorption_rates_latest(self.absorption_window_days)
        if not rows:
            return {}, None
        heights = {row["block_height"] for row in rows}
        if len(heights) > 1:
            max_height = max(heights)
            rows = [row for row in rows if row["block_height"] == max_height]
        if len(rows) < 6:
            raise ValueError("absorption_rates snapshot is partial")

        first = rows[0]
        payload = AbsorptionRatesResponse(
            timestamp=first["ts"],
            block_height=first["block_height"],
            window_days=first["window_days"],
            mined_supply_btc=first["mined_supply_btc"],
            bands=[
                AbsorptionRateMetricsResponse(
                    band=row["band"],
                    absorption_rate=row["absorption_rate"],
                    supply_delta_btc=row["supply_delta_btc"],
                    supply_start_btc=row["supply_start_btc"],
                    supply_end_btc=row["supply_end_btc"],
                )
                for row in rows
            ],
            dominant_absorber=first["dominant_absorber"],
            retail_absorption=first["retail_absorption"],
            institutional_absorption=first["institutional_absorption"],
            confidence=first["confidence"],
            has_historical_data=bool(first.get("has_historical_data", True)),
        ).model_dump(mode="json")
        return payload, first["ts"]

    async def _build_cost_basis(self) -> tuple[dict[str, Any], Any]:
        row = await self.repo.get_cost_basis_latest()
        if not row:
            return {}, None
        payload = CostBasisResponse(
            timestamp=row["ts"],
            block_height=row["block_height"],
            current_price_usd=row["current_price_usd"],
            total_cost_basis=row["total_cost_basis"],
            sth_cost_basis=row["sth_cost_basis"],
            lth_cost_basis=row["lth_cost_basis"],
            sth_mvrv=row["sth_mvrv"],
            lth_mvrv=row["lth_mvrv"],
            sth_supply_btc=row["sth_supply_btc"],
            lth_supply_btc=row["lth_supply_btc"],
            confidence=row["confidence"],
        ).model_dump(mode="json")
        return payload, row["ts"]
