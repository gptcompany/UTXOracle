from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from scripts.live.models import LiveComparison, LiveFeatureSet, LiveSnapshot, SourceHealth
from scripts.nautilus_live.adapter import AdapterMode, NautilusLiveAdapter
from scripts.nautilus_live.client import LiveSnapshotPollingClient
from scripts.nautilus_live.contract import TradableSnapshot, normalize_live_snapshot
from scripts.nautilus_live.gates import (
    GateConfig,
    GateDecision,
    GateState,
    NautilusSafetyGate,
)


def _build_snapshot(
    *,
    timestamp: datetime,
    block_height: int = 941456,
    utxoracle_price: float = 84211.52,
    confidence: float | None = 0.82,
    mempool_price: float | None = 84225.0,
    utxo_vs_mempool_bps: float | None = -18.0,
    electrs_status: str = "healthy",
    utxoracle_status: str = "healthy",
    mempool_status: str = "healthy",
) -> LiveSnapshot:
    return LiveSnapshot(
        timestamp=timestamp,
        block_height=block_height,
        utxoracle_price=utxoracle_price,
        utxoracle_confidence=confidence,
        mempool_exchange_price=mempool_price,
        hyperliquid_oracle_price=utxoracle_price + 15.0,
        hyperliquid_mark_price=utxoracle_price + 18.0,
        comparison=LiveComparison(
            utxo_vs_mempool_bps=utxo_vs_mempool_bps,
            utxo_vs_hl_oracle_bps=-22.0,
            utxo_vs_hl_mark_bps=-26.0,
        ),
        features=LiveFeatureSet(
            brk_realized_price=54311.39,
            brk_liveliness=0.6380666186,
            brk_reserve_risk=4.100239e-06,
        ),
        source_health={
            "electrs": SourceHealth(status=electrs_status, last_success=timestamp, observed_height=block_height),
            "utxoracle": SourceHealth(status=utxoracle_status, last_success=timestamp, observed_height=block_height),
            "mempool_api": SourceHealth(status=mempool_status, last_success=timestamp, observed_height=block_height),
            "hyperliquid": SourceHealth(status="stale", last_success=timestamp, observed_height=block_height),
            "brk": SourceHealth(status="healthy", last_success=timestamp, observed_height=block_height),
        },
        source_timestamps={
            "electrs": timestamp,
            "utxoracle": timestamp,
            "mempool_api": timestamp,
            "hyperliquid": timestamp,
            "brk": timestamp,
        },
    )


def _default_config() -> GateConfig:
    return GateConfig(
        ok_max_age_seconds=15.0,
        liquidate_only_max_age_seconds=30.0,
        ok_min_confidence=0.75,
        liquidate_only_min_confidence=0.60,
        ok_max_spread_bps=100.0,
        liquidate_only_max_spread_bps=250.0,
        required_sources=("electrs", "utxoracle", "mempool_api"),
        liquidate_only_recovery_streak=3,
    )


def test_normalize_live_snapshot_returns_only_admitted_tradable_fields():
    snapshot = _build_snapshot(timestamp=datetime.now(timezone.utc))

    normalized = normalize_live_snapshot(snapshot)

    assert isinstance(normalized, TradableSnapshot)
    assert normalized.schema_version == "v1"
    assert normalized.timestamp == snapshot.timestamp
    assert normalized.block_height == snapshot.block_height
    assert normalized.utxoracle_price == snapshot.utxoracle_price
    assert normalized.utxoracle_confidence == snapshot.utxoracle_confidence
    assert normalized.mempool_exchange_price == snapshot.mempool_exchange_price
    assert normalized.utxo_vs_mempool_bps == snapshot.comparison.utxo_vs_mempool_bps
    assert normalized.source_spread_bps == abs(snapshot.comparison.utxo_vs_mempool_bps)
    assert normalized.required_source_statuses == {
        "electrs": "healthy",
        "utxoracle": "healthy",
        "mempool_api": "healthy",
    }
    assert normalized.required_source_timestamps == {
        "electrs": snapshot.timestamp,
        "utxoracle": snapshot.timestamp,
        "mempool_api": snapshot.timestamp,
    }
    assert not hasattr(normalized, "hyperliquid_oracle_price")
    assert not hasattr(normalized, "brk_realized_price")


def test_normalize_live_snapshot_rejects_missing_mempool_comparison_field():
    snapshot = _build_snapshot(
        timestamp=datetime.now(timezone.utc),
        utxo_vs_mempool_bps=None,
    )

    with pytest.raises(ValueError, match="utxo_vs_mempool_bps"):
        normalize_live_snapshot(snapshot)


def test_gate_accepts_healthy_fresh_snapshot_as_status_ok():
    now = datetime.now(timezone.utc)
    gate = NautilusSafetyGate(config=_default_config())
    normalized = normalize_live_snapshot(_build_snapshot(timestamp=now))

    decision = gate.evaluate(normalized, now=now)

    assert isinstance(decision, GateDecision)
    assert decision.state == GateState.STATUS_OK
    assert decision.accepted is True
    assert decision.reason == "ok"


def test_gate_downgrades_to_liquidate_only_when_snapshot_is_borderline_stale():
    now = datetime.now(timezone.utc)
    gate = NautilusSafetyGate(config=_default_config())
    normalized = normalize_live_snapshot(_build_snapshot(timestamp=now - timedelta(seconds=20)))

    decision = gate.evaluate(normalized, now=now)

    assert decision.state == GateState.STATUS_LIQUIDATE_ONLY
    assert decision.accepted is True
    assert decision.reason == "snapshot_stale_borderline"


def test_gate_halts_when_required_source_is_degraded():
    now = datetime.now(timezone.utc)
    gate = NautilusSafetyGate(config=_default_config())
    normalized = normalize_live_snapshot(
        _build_snapshot(timestamp=now, mempool_status="stale")
    )

    decision = gate.evaluate(normalized, now=now)

    assert decision.state == GateState.STATUS_HALT
    assert decision.reason == "required_source_unhealthy:mempool_api"


def test_gate_halts_when_source_spread_bps_exceeds_hard_limit():
    now = datetime.now(timezone.utc)
    gate = NautilusSafetyGate(config=_default_config())
    normalized = normalize_live_snapshot(
        _build_snapshot(timestamp=now, utxo_vs_mempool_bps=310.0)
    )

    decision = gate.evaluate(normalized, now=now)

    assert decision.state == GateState.STATUS_HALT
    assert decision.reason == "spread_bps_too_high"


def test_gate_halts_when_timestamp_moves_backward():
    now = datetime.now(timezone.utc)
    gate = NautilusSafetyGate(config=_default_config())
    first = normalize_live_snapshot(_build_snapshot(timestamp=now, block_height=941456))
    second = normalize_live_snapshot(_build_snapshot(timestamp=now - timedelta(seconds=1), block_height=941457))

    first_decision = gate.evaluate(first, now=now)
    second_decision = gate.evaluate(second, now=now)

    assert first_decision.state == GateState.STATUS_OK
    assert second_decision.state == GateState.STATUS_HALT
    assert second_decision.reason == "timestamp_not_monotonic"


def test_gate_halts_when_block_height_moves_backward_by_default():
    now = datetime.now(timezone.utc)
    gate = NautilusSafetyGate(config=_default_config())
    first = normalize_live_snapshot(_build_snapshot(timestamp=now, block_height=941456))
    second = normalize_live_snapshot(
        _build_snapshot(timestamp=now + timedelta(seconds=1), block_height=941455)
    )

    gate.evaluate(first, now=now)
    second_decision = gate.evaluate(second, now=now + timedelta(seconds=1))

    assert second_decision.state == GateState.STATUS_HALT
    assert second_decision.reason == "block_height_moved_backward"


def test_gate_halts_when_kill_switch_is_enabled():
    now = datetime.now(timezone.utc)
    gate = NautilusSafetyGate(config=_default_config(), kill_switch_enabled=True)
    normalized = normalize_live_snapshot(_build_snapshot(timestamp=now))

    decision = gate.evaluate(normalized, now=now)

    assert decision.state == GateState.STATUS_HALT
    assert decision.reason == "operator_kill_switch"


def test_gate_requires_manual_reset_after_halt_before_accepting_healthy_snapshots():
    now = datetime.now(timezone.utc)
    gate = NautilusSafetyGate(config=_default_config())
    bad = normalize_live_snapshot(
        _build_snapshot(timestamp=now, utxo_vs_mempool_bps=310.0)
    )
    healthy = normalize_live_snapshot(
        _build_snapshot(timestamp=now + timedelta(seconds=1), block_height=941457)
    )

    first = gate.evaluate(bad, now=now)
    second = gate.evaluate(healthy, now=now + timedelta(seconds=1))
    gate.reset()
    third = gate.evaluate(healthy, now=now + timedelta(seconds=1))

    assert first.state == GateState.STATUS_HALT
    assert first.reason == "spread_bps_too_high"
    assert second.state == GateState.STATUS_HALT
    assert second.reason == "manual_reset_required"
    assert third.state == GateState.STATUS_OK
    assert third.reason == "ok"


def test_gate_recovers_from_liquidate_only_after_three_consecutive_healthy_snapshots():
    now = datetime.now(timezone.utc)
    gate = NautilusSafetyGate(config=_default_config())

    borderline = normalize_live_snapshot(
        _build_snapshot(timestamp=now, confidence=0.70)
    )
    healthy_1 = normalize_live_snapshot(
        _build_snapshot(timestamp=now + timedelta(seconds=1), block_height=941457, confidence=0.82)
    )
    healthy_2 = normalize_live_snapshot(
        _build_snapshot(timestamp=now + timedelta(seconds=2), block_height=941458, confidence=0.83)
    )
    healthy_3 = normalize_live_snapshot(
        _build_snapshot(timestamp=now + timedelta(seconds=3), block_height=941459, confidence=0.84)
    )

    first = gate.evaluate(borderline, now=now)
    second = gate.evaluate(healthy_1, now=now + timedelta(seconds=1))
    third = gate.evaluate(healthy_2, now=now + timedelta(seconds=2))
    fourth = gate.evaluate(healthy_3, now=now + timedelta(seconds=3))

    assert first.state == GateState.STATUS_LIQUIDATE_ONLY
    assert second.state == GateState.STATUS_LIQUIDATE_ONLY
    assert second.reason == "recovery_in_progress:1_of_3"
    assert third.state == GateState.STATUS_LIQUIDATE_ONLY
    assert third.reason == "recovery_in_progress:2_of_3"
    assert fourth.state == GateState.STATUS_OK
    assert fourth.reason == "ok"


@pytest.mark.asyncio
async def test_polling_client_reads_live_snapshot_from_8011_contract():
    snapshot = _build_snapshot(timestamp=datetime.now(timezone.utc))

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/live/snapshot"
        return httpx.Response(200, json=snapshot.model_dump(mode="json"))

    client = LiveSnapshotPollingClient(
        base_url="http://live.local",
        transport=httpx.MockTransport(handler),
    )
    result = await client.fetch_snapshot()
    await client.aclose()

    assert isinstance(result, LiveSnapshot)
    assert result.timestamp == snapshot.timestamp
    assert result.utxoracle_price == snapshot.utxoracle_price


@pytest.mark.asyncio
async def test_polling_client_reads_recent_live_history():
    now = datetime.now(timezone.utc)
    first = _build_snapshot(timestamp=now - timedelta(minutes=2), block_height=941454)
    second = _build_snapshot(timestamp=now - timedelta(minutes=1), block_height=941455)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/live/history"
        assert request.url.params["minutes"] == "15"
        return httpx.Response(200, json=[first.model_dump(mode="json"), second.model_dump(mode="json")])

    client = LiveSnapshotPollingClient(
        base_url="http://live.local",
        transport=httpx.MockTransport(handler),
    )
    result = await client.fetch_history(minutes=15)
    await client.aclose()

    assert [item.block_height for item in result] == [941454, 941455]


@pytest.mark.asyncio
async def test_adapter_poll_once_returns_liquidate_only_snapshot_and_logs_decision():
    now = datetime.now(timezone.utc)
    snapshot = _build_snapshot(timestamp=now - timedelta(seconds=20))
    events: list[dict[str, object]] = []

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=snapshot.model_dump(mode="json"))

    def capture(event: dict[str, object]) -> None:
        events.append(event)

    adapter = NautilusLiveAdapter(
        client=LiveSnapshotPollingClient(
            base_url="http://live.local",
            transport=httpx.MockTransport(handler),
        ),
        gate=NautilusSafetyGate(config=_default_config()),
        mode=AdapterMode.SHADOW_READ,
        decision_logger=capture,
    )

    result = await adapter.poll_once(now=now)
    await adapter.aclose()

    assert result is not None
    normalized, decision = result
    assert normalized.source_spread_bps == abs(snapshot.comparison.utxo_vs_mempool_bps)
    assert decision.state == GateState.STATUS_LIQUIDATE_ONLY
    assert decision.accepted is True
    assert decision.reason == "snapshot_stale_borderline"
    assert events == [
        {
            "timestamp": snapshot.timestamp.isoformat(),
            "block_height": snapshot.block_height,
            "mode": "shadow_read",
            "state": "STATUS_LIQUIDATE_ONLY",
            "accepted": True,
            "reason": "snapshot_stale_borderline",
        }
    ]


@pytest.mark.asyncio
async def test_adapter_poll_once_returns_none_and_logs_error_when_snapshot_cannot_normalize():
    now = datetime.now(timezone.utc)
    snapshot = _build_snapshot(timestamp=now, utxo_vs_mempool_bps=None)
    events: list[dict[str, object]] = []

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=snapshot.model_dump(mode="json"))

    adapter = NautilusLiveAdapter(
        client=LiveSnapshotPollingClient(
            base_url="http://live.local",
            transport=httpx.MockTransport(handler),
        ),
        gate=NautilusSafetyGate(config=_default_config()),
        mode=AdapterMode.SHADOW_READ,
        decision_logger=events.append,
    )

    result = await adapter.poll_once(now=now)
    await adapter.aclose()

    assert result is None
    assert events == [
        {
            "mode": "shadow_read",
            "state": "STATUS_HALT",
            "accepted": False,
            "reason": "normalization_failed:utxo_vs_mempool_bps is required",
        }
    ]


@pytest.mark.asyncio
async def test_adapter_replay_recent_history_normalizes_and_evaluates_snapshots_in_order():
    now = datetime.now(timezone.utc)
    first = _build_snapshot(timestamp=now - timedelta(seconds=10), block_height=941456, confidence=0.70)
    second = _build_snapshot(timestamp=now - timedelta(seconds=5), block_height=941457, confidence=0.82)
    third = _build_snapshot(timestamp=now - timedelta(seconds=1), block_height=941458, confidence=0.83)
    events: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/live/history"
        assert request.url.params["minutes"] == "5"
        return httpx.Response(
            200,
            json=[
                first.model_dump(mode="json"),
                second.model_dump(mode="json"),
                third.model_dump(mode="json"),
            ],
        )

    adapter = NautilusLiveAdapter(
        client=LiveSnapshotPollingClient(
            base_url="http://live.local",
            transport=httpx.MockTransport(handler),
        ),
        gate=NautilusSafetyGate(config=_default_config()),
        mode=AdapterMode.PAPER_TRADE,
        decision_logger=events.append,
    )

    results = await adapter.replay_recent_history(minutes=5, now=now)
    await adapter.aclose()

    assert len(results) == 3
    assert [item[0].block_height for item in results] == [941456, 941457, 941458]
    assert [item[1].state for item in results] == [
        GateState.STATUS_LIQUIDATE_ONLY,
        GateState.STATUS_LIQUIDATE_ONLY,
        GateState.STATUS_LIQUIDATE_ONLY,
    ]
    assert events[0]["mode"] == "paper_trade"
    assert events[-1]["reason"] == "recovery_in_progress:2_of_3"


@pytest.mark.asyncio
async def test_adapter_operator_kill_switch_fails_closed_before_gate_evaluation():
    now = datetime.now(timezone.utc)
    snapshot = _build_snapshot(timestamp=now)
    events: list[dict[str, object]] = []

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=snapshot.model_dump(mode="json"))

    adapter = NautilusLiveAdapter(
        client=LiveSnapshotPollingClient(
            base_url="http://live.local",
            transport=httpx.MockTransport(handler),
        ),
        gate=NautilusSafetyGate(config=_default_config()),
        mode=AdapterMode.SHADOW_READ,
        decision_logger=events.append,
        kill_switch_check=lambda: True,
    )

    result = await adapter.poll_once(now=now)
    await adapter.aclose()

    assert result is None
    assert events == [
        {
            "mode": "shadow_read",
            "state": "STATUS_HALT",
            "accepted": False,
            "reason": "operator_kill_switch",
        }
    ]


@pytest.mark.asyncio
async def test_adapter_end_to_end_modes_cover_shadow_poll_paper_poll_and_replay_paths():
    now = datetime.now(timezone.utc)
    shadow_snapshot = _build_snapshot(timestamp=now)
    paper_snapshot = _build_snapshot(
        timestamp=now - timedelta(seconds=20),
        block_height=941457,
        confidence=0.70,
    )
    replay_first = _build_snapshot(
        timestamp=now - timedelta(seconds=10),
        block_height=941458,
        confidence=0.82,
    )
    replay_second = _build_snapshot(
        timestamp=now - timedelta(seconds=5),
        block_height=941459,
        confidence=0.83,
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/live/snapshot":
            if request.url.host == "shadow.local":
                return httpx.Response(200, json=shadow_snapshot.model_dump(mode="json"))
            if request.url.host == "paper.local":
                return httpx.Response(200, json=paper_snapshot.model_dump(mode="json"))
        if request.url.path == "/api/v1/live/history" and request.url.host == "paper.local":
            return httpx.Response(
                200,
                json=[
                    replay_first.model_dump(mode="json"),
                    replay_second.model_dump(mode="json"),
                ],
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    shadow_events: list[dict[str, object]] = []
    paper_events: list[dict[str, object]] = []

    shadow_adapter = NautilusLiveAdapter(
        client=LiveSnapshotPollingClient(base_url="http://shadow.local", transport=transport),
        gate=NautilusSafetyGate(config=_default_config()),
        mode=AdapterMode.SHADOW_READ,
        decision_logger=shadow_events.append,
    )
    paper_adapter = NautilusLiveAdapter(
        client=LiveSnapshotPollingClient(base_url="http://paper.local", transport=transport),
        gate=NautilusSafetyGate(config=_default_config()),
        mode=AdapterMode.PAPER_TRADE,
        decision_logger=paper_events.append,
    )

    shadow_result = await shadow_adapter.poll_once(now=now)
    paper_result = await paper_adapter.poll_once(now=now)
    replay_results = await paper_adapter.replay_recent_history(minutes=5, now=now)
    await shadow_adapter.aclose()
    await paper_adapter.aclose()

    assert shadow_result is not None
    assert shadow_result[1].state == GateState.STATUS_OK
    assert shadow_events[-1]["mode"] == "shadow_read"
    assert shadow_events[-1]["reason"] == "ok"

    assert paper_result is not None
    assert paper_result[1].state == GateState.STATUS_LIQUIDATE_ONLY
    assert paper_events[0]["mode"] == "paper_trade"
    assert paper_events[0]["reason"] == "snapshot_stale_borderline"

    assert [item[0].block_height for item in replay_results] == [941458, 941459]
    assert [item[1].state for item in replay_results] == [
        GateState.STATUS_LIQUIDATE_ONLY,
        GateState.STATUS_LIQUIDATE_ONLY,
    ]
    assert paper_events[-1]["reason"] == "recovery_in_progress:2_of_3"
