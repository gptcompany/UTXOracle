import json
from datetime import datetime, timezone

import pytest

from scripts.live.bundle_writer import (
    COHORT_BUNDLE_ID,
    CORE_BUNDLE_ID,
    FLOW_BUNDLE_ID,
    MACRO_BUNDLE_ID,
    BundleWriter,
)
from scripts.live.models import LiveComparison, LiveFeatureSet, LiveSnapshot, SourceHealth


def _build_snapshot() -> LiveSnapshot:
    ts = datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc)
    return LiveSnapshot(
        timestamp=ts,
        block_height=840_000,
        utxoracle_price=84_250.0,
        utxoracle_confidence=0.82,
        mempool_exchange_price=84_300.0,
        hyperliquid_oracle_price=84_260.0,
        hyperliquid_mark_price=84_275.0,
        comparison=LiveComparison(
            utxo_vs_mempool_bps=-5.93,
            utxo_vs_hl_oracle_bps=-1.19,
            utxo_vs_hl_mark_bps=-2.96,
        ),
        features=LiveFeatureSet(
            brk_realized_price=54_311.39,
            brk_liveliness=0.63,
            brk_reserve_risk=0.003,
            brk_nupl=0.55,
            brk_sopr=1.02,
        ),
        source_health={
            "utxoracle": SourceHealth(status="healthy", last_success=ts),
            "mempool_api": SourceHealth(status="healthy", last_success=ts),
            "hyperliquid": SourceHealth(status="healthy", last_success=ts),
            "brk": SourceHealth(status="healthy", last_success=ts),
        },
        source_timestamps={
            "utxoracle": ts,
            "mempool_api": ts,
            "hyperliquid": ts,
            "brk": ts,
        },
    )


class FakeBundleRepo:
    def __init__(self) -> None:
        self.latest_feature_bundles: dict[str, dict] = {}
        self.sent_rows: list[tuple[str, dict, dict]] = []
        self.flush_calls = 0

    async def get_latest_feature_bundle(self, bundle_id: str):
        return self.latest_feature_bundles.get(bundle_id)

    async def get_latest_metrics(self):
        ts = datetime(2026, 4, 7, 11, 55, tzinfo=timezone.utc)
        return {
            "ts": ts,
            "signal_mean": 0.15,
            "signal_std": 0.05,
            "ci_lower": 0.05,
            "ci_upper": 0.25,
            "action": "BUY",
            "action_confidence": 0.85,
            "n_samples": 1000,
            "distribution_type": "unimodal",
            "block_height": 840_000,
            "active_addresses_block": 15_000,
            "active_addresses_24h": 850_000,
            "unique_senders": 8_000,
            "unique_receivers": 7_000,
            "is_anomaly": False,
            "tx_count": 450_000,
            "tx_volume_btc": 12_000.5,
            "tx_volume_usd": 1_020_042_500.0,
            "utxoracle_price_used": 84_250.0,
            "low_confidence": False,
        }

    async def get_address_cohorts_latest(self):
        ts = datetime(2026, 4, 7, 0, 0, tzinfo=timezone.utc)
        return [
            {
                "cohort": cohort,
                "ts": ts,
                "block_height": 840_000,
                "current_price_usd": 84_250.0,
                "whale_retail_spread": 1.0,
                "whale_retail_mvrv_ratio": 1.0,
                "total_supply_btc": 1770.0,
                "total_addresses": 3,
                "cost_basis": 45_000.0,
                "supply_btc": supply_btc,
                "supply_pct": supply_pct,
                "mvrv": 1.0,
                "address_count": 1,
            }
            for cohort, supply_btc, supply_pct in (
                ("retail", 5.0, 0.25),
                ("mid_tier", 65.0, 3.0),
                ("whale", 1700.0, 80.0),
            )
        ]

    async def get_wallet_waves_latest(self):
        ts = datetime(2026, 4, 7, 0, 0, tzinfo=timezone.utc)
        return [
            {
                "band": band,
                "ts": ts,
                "block_height": 840_000,
                "supply_btc": 1.0,
                "supply_pct": 1.0,
                "address_count": 1,
                "avg_balance": 1.0,
                "total_supply_btc": 6.0,
                "retail_supply_pct": 50.0,
                "institutional_supply_pct": 50.0,
                "address_count_total": 6,
                "null_address_btc": 0.0,
                "confidence": 0.9,
            }
            for band in ("shrimp", "crab", "fish", "shark", "whale", "humpback")
        ]

    async def get_absorption_rates_latest(self, window_days: int = 30):
        ts = datetime(2026, 4, 7, 0, 0, tzinfo=timezone.utc)
        return [
            {
                "band": band,
                "ts": ts,
                "block_height": 840_000,
                "absorption_rate": 0.45,
                "supply_delta_btc": 1.0,
                "supply_start_btc": 0.5,
                "supply_end_btc": 1.5,
                "window_days": window_days,
                "mined_supply_btc": 10.0,
                "dominant_absorber": "whale",
                "retail_absorption": 0.5,
                "institutional_absorption": 0.5,
                "confidence": 0.9,
                "has_historical_data": True,
            }
            for band in ("shrimp", "crab", "fish", "shark", "whale", "humpback")
        ]

    async def get_cost_basis_latest(self):
        ts = datetime(2026, 4, 7, 0, 0, tzinfo=timezone.utc)
        return {
            "ts": ts,
            "block_height": 840_000,
            "current_price_usd": 84_250.0,
            "total_cost_basis": 50_000.0,
            "sth_cost_basis": 65_000.0,
            "lth_cost_basis": 35_000.0,
            "sth_mvrv": 0.8,
            "lth_mvrv": 0.9,
            "sth_supply_btc": 100.0,
            "lth_supply_btc": 200.0,
            "confidence": 0.9,
        }

    async def fetchrow(self, query: str, *args):
        if "FROM mempool_predictions" in query:
            return {
                "total_transactions": 3,
                "total_btc_volume": 37.5,
                "avg_urgency_score": 0.65,
                "high_urgency_count": 1,
                "rbf_enabled_count": 1,
            }
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fetch(self, query: str, *args):
        if "FROM mempool_predictions" in query:
            return [
                {
                    "detection_timestamp": datetime(2026, 4, 7, 11, 59, tzinfo=timezone.utc),
                    "btc_value": 10.0,
                    "flow_type": "inflow",
                    "exchange_addresses": "addr_in",
                },
                {
                    "detection_timestamp": datetime(2026, 4, 7, 11, 58, tzinfo=timezone.utc),
                    "btc_value": 22.5,
                    "flow_type": "outflow",
                    "exchange_addresses": "addr_out",
                },
                {
                    "detection_timestamp": datetime(2026, 4, 7, 11, 57, tzinfo=timezone.utc),
                    "btc_value": 5.0,
                    "flow_type": "internal",
                    "exchange_addresses": None,
                },
            ]
        if "FROM address_clusters" in query:
            return [
                {"address": "addr_in", "cluster_id": "cluster_001", "label": "Binance"},
                {"address": "addr_out", "cluster_id": "cluster_002", "label": "Coinbase"},
            ]
        raise AssertionError(f"unexpected fetch query: {query}")

    async def async_send_row(self, table: str, symbols: dict, columns: dict, at=None):
        self.sent_rows.append((table, symbols, columns))
        if table == "btc_feature_bundles":
            self.latest_feature_bundles[symbols["bundle_id"]] = {
                "sequence_id": columns["sequence_id"],
                "produced_at": columns["produced_at"],
                "bundle_status": symbols["bundle_status"],
                "payload_json": columns["payload_json"],
            }
        return True

    async def async_flush_ingestion(self):
        self.flush_calls += 1
        return True


class MissingMetricsRepo(FakeBundleRepo):
    async def get_latest_metrics(self):
        return None


class CostBasisOnlyRepo(FakeBundleRepo):
    async def get_address_cohorts_latest(self):
        return []

    async def get_wallet_waves_latest(self):
        return []

    async def get_absorption_rates_latest(self, window_days: int = 30):
        return []

    async def get_cost_basis_latest(self):
        row = await super().get_cost_basis_latest()
        if row is None:
            return None
        return {
            **row,
            "ts": datetime.now(timezone.utc),
        }


class LegacyAbsorptionRepo(FakeBundleRepo):
    async def get_absorption_rates_latest(self, window_days: int = 30):
        rows = await super().get_absorption_rates_latest(window_days)
        return [{k: v for k, v in row.items() if k != "has_historical_data"} for row in rows]


@pytest.mark.asyncio
async def test_bundle_writer_materializes_all_four_bundle_families():
    repo = FakeBundleRepo()
    writer = BundleWriter(repo)

    written = await writer.write_bundles(_build_snapshot())

    assert written == [
        CORE_BUNDLE_ID,
        FLOW_BUNDLE_ID,
        MACRO_BUNDLE_ID,
        COHORT_BUNDLE_ID,
    ]
    assert repo.flush_calls == 1

    core_payload = json.loads(repo.latest_feature_bundles[CORE_BUNDLE_ID]["payload_json"])
    flow_payload = json.loads(repo.latest_feature_bundles[FLOW_BUNDLE_ID]["payload_json"])
    macro_payload = json.loads(repo.latest_feature_bundles[MACRO_BUNDLE_ID]["payload_json"])
    cohort_payload = json.loads(repo.latest_feature_bundles[COHORT_BUNDLE_ID]["payload_json"])

    assert core_payload["metadata"]["sequence_id"] == 1
    assert core_payload["metrics_latest"]["monte_carlo"]["action"] == "BUY"
    assert flow_payload["recent_whale_window"]["net_flow_btc"] == pytest.approx(12.5)
    assert flow_payload["recent_whale_window"]["enriched_event_count"] == 2
    assert macro_payload["macro_metrics"]["nupl"] == pytest.approx(0.55)
    assert macro_payload["source_metadata"]["missing_metrics"] == []
    assert cohort_payload["cost_basis"]["total_cost_basis"] == pytest.approx(50_000.0)


@pytest.mark.asyncio
async def test_bundle_writer_increments_sequence_ids_per_bundle_family():
    repo = FakeBundleRepo()
    writer = BundleWriter(repo)
    snapshot = _build_snapshot()

    await writer.write_bundles(snapshot)
    await writer.write_bundles(snapshot)

    core_payload = json.loads(repo.latest_feature_bundles[CORE_BUNDLE_ID]["payload_json"])
    flow_payload = json.loads(repo.latest_feature_bundles[FLOW_BUNDLE_ID]["payload_json"])

    assert core_payload["metadata"]["sequence_id"] == 2
    assert flow_payload["metadata"]["sequence_id"] == 2


@pytest.mark.asyncio
async def test_bundle_writer_keeps_core_healthy_when_metrics_latest_is_missing():
    repo = MissingMetricsRepo()
    writer = BundleWriter(repo)

    await writer.write_bundles(_build_snapshot())

    core_payload = json.loads(repo.latest_feature_bundles[CORE_BUNDLE_ID]["payload_json"])

    assert core_payload["metadata"]["bundle_status"] == "healthy"
    assert core_payload["metadata"]["degraded_reasons"] == []
    assert core_payload["metrics_latest"] == {}


@pytest.mark.asyncio
async def test_bundle_writer_keeps_flow_and_cohort_healthy_with_only_required_inputs():
    repo = CostBasisOnlyRepo()
    writer = BundleWriter(repo)

    await writer.write_bundles(_build_snapshot())

    flow_payload = json.loads(repo.latest_feature_bundles[FLOW_BUNDLE_ID]["payload_json"])
    cohort_payload = json.loads(repo.latest_feature_bundles[COHORT_BUNDLE_ID]["payload_json"])

    assert flow_payload["metadata"]["bundle_status"] == "healthy"
    assert flow_payload["metadata"]["degraded_reasons"] == []
    assert flow_payload["absorption_rates"] == {}

    assert cohort_payload["metadata"]["bundle_status"] == "healthy"
    assert cohort_payload["metadata"]["degraded_reasons"] == []
    assert cohort_payload["address_cohorts"] == {}
    assert cohort_payload["wallet_waves"] == {}
    assert cohort_payload["absorption_rates"] == {}
    assert cohort_payload["cost_basis"]["total_cost_basis"] == pytest.approx(50_000.0)


@pytest.mark.asyncio
async def test_bundle_writer_degrades_cohort_when_cost_basis_is_missing():
    class MissingCostBasisRepo(FakeBundleRepo):
        async def get_cost_basis_latest(self):
            return None

    repo = MissingCostBasisRepo()
    writer = BundleWriter(repo)

    await writer.write_bundles(_build_snapshot())

    cohort_payload = json.loads(repo.latest_feature_bundles[COHORT_BUNDLE_ID]["payload_json"])

    assert cohort_payload["metadata"]["bundle_status"] == "degraded"
    assert "cost_basis unavailable" in cohort_payload["metadata"]["degraded_reasons"]


@pytest.mark.asyncio
async def test_bundle_writer_accepts_legacy_absorption_rows_without_has_historical_data():
    repo = LegacyAbsorptionRepo()
    writer = BundleWriter(repo)

    await writer.write_bundles(_build_snapshot())

    flow_payload = json.loads(repo.latest_feature_bundles[FLOW_BUNDLE_ID]["payload_json"])
    cohort_payload = json.loads(repo.latest_feature_bundles[COHORT_BUNDLE_ID]["payload_json"])

    assert flow_payload["metadata"]["bundle_status"] == "healthy"
    assert flow_payload["absorption_rates"]["has_historical_data"] is True
    assert cohort_payload["absorption_rates"]["has_historical_data"] is True
