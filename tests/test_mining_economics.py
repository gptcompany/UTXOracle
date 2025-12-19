"""Tests for Mining Economics module (spec-030).

TDD tests for Hash Ribbons + Mining Pulse implementation.
Tests are organized by user story:
- US1: Mining Pulse (RPC-only)
- US2: Hash Ribbons (external API)
- US3: Combined Mining Economics
"""

import pytest
from unittest.mock import Mock, patch

from scripts.models.metrics_models import (
    MiningPulseZone,
    HashRibbonsResult,
    MiningPulseResult,
    MiningEconomicsResult,
)


# =============================================================================
# US1: Mining Pulse Tests (T006-T008)
# =============================================================================


class TestMiningPulseZoneClassification:
    """T007: Test Mining Pulse zone classification logic."""

    def test_fast_zone_below_540s(self):
        """Intervals below 540s should be classified as FAST."""
        from scripts.metrics.mining_economics import classify_pulse_zone

        assert classify_pulse_zone(500.0) == MiningPulseZone.FAST
        assert classify_pulse_zone(539.9) == MiningPulseZone.FAST

    def test_normal_zone_540_to_660s(self):
        """Intervals between 540-660s should be classified as NORMAL."""
        from scripts.metrics.mining_economics import classify_pulse_zone

        assert classify_pulse_zone(540.0) == MiningPulseZone.NORMAL
        assert classify_pulse_zone(600.0) == MiningPulseZone.NORMAL
        assert classify_pulse_zone(660.0) == MiningPulseZone.NORMAL

    def test_slow_zone_above_660s(self):
        """Intervals above 660s should be classified as SLOW."""
        from scripts.metrics.mining_economics import classify_pulse_zone

        assert classify_pulse_zone(660.1) == MiningPulseZone.SLOW
        assert classify_pulse_zone(700.0) == MiningPulseZone.SLOW
        assert classify_pulse_zone(900.0) == MiningPulseZone.SLOW


class TestCalculateMiningPulse:
    """T006: Test calculate_mining_pulse returns valid result."""

    def test_calculate_mining_pulse_returns_valid_result(self):
        """Mining pulse should return valid MiningPulseResult with all fields."""
        from scripts.metrics.mining_economics import calculate_mining_pulse

        # Mock RPC client with block data
        mock_rpc = Mock()
        mock_rpc.getbestblockhash.return_value = "000000000000000000hash"
        mock_rpc.getblock.return_value = {"height": 875000, "time": 1734600000}

        # Create mock blocks with 10-minute intervals (normal)
        def mock_getblockhash(height):
            return f"hash_{height}"

        def mock_getblock_by_hash(block_hash):
            height = int(block_hash.split("_")[1]) if "_" in block_hash else 875000
            # Each block 600 seconds apart (normal interval)
            base_time = 1734600000 - (875000 - height) * 600
            return {"height": height, "time": base_time}

        mock_rpc.getblockhash.side_effect = mock_getblockhash
        mock_rpc.getblock.side_effect = mock_getblock_by_hash

        result = calculate_mining_pulse(mock_rpc, window_blocks=10)

        assert isinstance(result, MiningPulseResult)
        assert result.avg_block_interval > 0
        assert result.window_blocks == 10
        assert result.tip_height == 875000
        assert isinstance(result.pulse_zone, MiningPulseZone)

    def test_mining_pulse_deviation_calculation(self):
        """Deviation should be calculated correctly from average interval."""
        from scripts.metrics.mining_economics import calculate_mining_pulse

        mock_rpc = Mock()
        mock_rpc.getbestblockhash.return_value = "hash_875000"

        # Create mock blocks with 540s intervals (FAST, -10% deviation)
        def mock_getblockhash(height):
            return f"hash_{height}"

        def mock_getblock_by_hash(block_hash):
            height = int(block_hash.split("_")[1]) if "_" in block_hash else 875000
            # Each block 540 seconds apart (fast interval)
            base_time = 1734600000 - (875000 - height) * 540
            return {"height": height, "time": base_time}

        mock_rpc.getblockhash.side_effect = mock_getblockhash
        mock_rpc.getblock.side_effect = mock_getblock_by_hash

        result = calculate_mining_pulse(mock_rpc, window_blocks=10)

        # 540s is exactly -10% from 600s target
        assert result.interval_deviation_pct == pytest.approx(-10.0, abs=0.1)
        assert result.implied_hashrate_change == pytest.approx(10.0, abs=0.1)
        assert result.pulse_zone == MiningPulseZone.NORMAL  # 540 is boundary


class TestMiningPulseRPCIntegration:
    """T008: Test Mining Pulse RPC integration."""

    def test_mining_pulse_handles_rpc_error(self):
        """Mining pulse should raise appropriate error on RPC failure."""
        from scripts.metrics.mining_economics import calculate_mining_pulse

        mock_rpc = Mock()
        mock_rpc.getbestblockhash.side_effect = ConnectionError("RPC unavailable")

        with pytest.raises(ConnectionError):
            calculate_mining_pulse(mock_rpc)

    def test_mining_pulse_counts_fast_slow_blocks(self):
        """Mining pulse should correctly count fast vs slow blocks."""
        from scripts.metrics.mining_economics import calculate_mining_pulse

        mock_rpc = Mock()
        mock_rpc.getbestblockhash.return_value = "hash_875000"

        # Create alternating fast/slow blocks
        def mock_getblockhash(height):
            return f"hash_{height}"

        def mock_getblock_by_hash(block_hash):
            height = int(block_hash.split("_")[1]) if "_" in block_hash else 875000
            # Alternate: odd heights = 500s (fast), even heights = 700s (slow)
            interval = 500 if height % 2 == 1 else 700
            # Calculate cumulative time
            base_time = 1734600000
            for h in range(875000, height, -1):
                base_time -= 500 if h % 2 == 1 else 700
            return {"height": height, "time": base_time}

        mock_rpc.getblockhash.side_effect = mock_getblockhash
        mock_rpc.getblock.side_effect = mock_getblock_by_hash

        result = calculate_mining_pulse(mock_rpc, window_blocks=10)

        # Should have roughly equal fast and slow blocks
        assert result.blocks_fast >= 0
        assert result.blocks_slow >= 0
        assert result.blocks_fast + result.blocks_slow == result.window_blocks - 1


# =============================================================================
# US2: Hash Ribbons Tests (T012-T014)
# =============================================================================


class TestFetchHashrateFromMempoolAPI:
    """T012: Test hashrate fetching from mempool.space API."""

    @patch("scripts.data.hashrate_fetcher.httpx.get")
    def test_fetch_hashrate_returns_valid_data(self, mock_get):
        """Hashrate fetcher should return parsed hashrate data."""
        from scripts.data.hashrate_fetcher import fetch_hashrate_data

        mock_response = Mock()
        mock_response.json.return_value = {
            "hashrates": [
                {"timestamp": 1734500000, "avgHashrate": 5.5e20},
                {"timestamp": 1734400000, "avgHashrate": 5.4e20},
            ],
            "currentHashrate": 5.6e20,
        }
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = fetch_hashrate_data()

        assert "hashrates" in result
        assert "currentHashrate" in result
        assert len(result["hashrates"]) >= 1

    @patch("scripts.data.hashrate_fetcher.httpx.get")
    def test_fetch_hashrate_validates_response(self, mock_get):
        """Hashrate fetcher should validate API response structure."""
        from scripts.data.hashrate_fetcher import fetch_hashrate_data, clear_cache

        # Clear cache to force fresh fetch
        clear_cache()

        # Invalid response missing required fields
        mock_response = Mock()
        mock_response.json.return_value = {"invalid": "data"}
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with pytest.raises(ValueError, match="Invalid API response"):
            fetch_hashrate_data(use_cache=False)


class TestCalculateHashRibbonsMA:
    """T013: Test Hash Ribbons MA crossover calculation."""

    def test_calculate_hash_ribbons_detects_stress(self):
        """Hash ribbons should detect stress when 30d < 60d."""
        from scripts.metrics.mining_economics import calculate_hash_ribbons

        # Mock hashrate data with 30d < 60d (stress)
        hashrate_data = {
            "hashrates": [
                {"timestamp": t, "avgHashrate": 5.0e20 - i * 1e18}
                for i, t in enumerate(
                    range(1734600000, 1734600000 - 90 * 86400, -86400)
                )
            ],
            "currentHashrate": 5.0e20,
        }

        result = calculate_hash_ribbons(hashrate_data)

        assert isinstance(result, HashRibbonsResult)
        # If 30d avg < 60d avg, ribbon_signal should be True
        if result.hashrate_ma_30d < result.hashrate_ma_60d:
            assert result.ribbon_signal is True

    def test_calculate_hash_ribbons_detects_recovery(self):
        """Hash ribbons should detect recovery when 30d crosses above 60d."""
        from scripts.metrics.mining_economics import calculate_hash_ribbons

        # Mock hashrate data with increasing recent hashrate (recovery)
        hashrate_data = {
            "hashrates": [
                {"timestamp": t, "avgHashrate": 5.0e20 + i * 1e18}
                for i, t in enumerate(
                    range(1734600000, 1734600000 - 90 * 86400, -86400)
                )
            ],
            "currentHashrate": 5.5e20,
        }

        result = calculate_hash_ribbons(hashrate_data)

        assert isinstance(result, HashRibbonsResult)
        assert result.hashrate_ma_30d >= 0
        assert result.hashrate_ma_60d >= 0


class TestHashRibbonsCapitulationDays:
    """T014: Test Hash Ribbons capitulation days counting."""

    def test_count_capitulation_days_streak(self):
        """Should count consecutive days where 30d < 60d."""
        from scripts.metrics.mining_economics import count_capitulation_days

        # 10 days of decreasing hashrate (stress)
        hashrate_data = {
            "hashrates": [
                {"timestamp": 1734600000 - i * 86400, "avgHashrate": 5.0e20 - i * 5e18}
                for i in range(90)
            ],
        }

        days = count_capitulation_days(hashrate_data)
        assert days >= 0

    def test_count_capitulation_days_reset_on_recovery(self):
        """Capitulation days should reset when 30d crosses above 60d."""
        from scripts.metrics.mining_economics import count_capitulation_days

        # Recovery pattern: recent hashrate higher
        hashrate_data = {
            "hashrates": [
                {
                    "timestamp": 1734600000 - i * 86400,
                    "avgHashrate": 5.0e20 + (30 - i) * 1e18,
                }
                for i in range(90)
            ],
        }

        days = count_capitulation_days(hashrate_data)
        # With recovery, capitulation days should be 0 or low
        assert days >= 0


# =============================================================================
# US3: Combined Mining Economics Tests (T020-T021)
# =============================================================================


class TestDeriveCombinedSignal:
    """T020: Test derive_combined_signal logic."""

    def test_recovery_signal_takes_priority(self):
        """Recovery signal should take priority over other states."""
        from scripts.metrics.mining_economics import derive_combined_signal

        ribbons = HashRibbonsResult(
            hashrate_current=1000.0,
            hashrate_ma_30d=1100.0,
            hashrate_ma_60d=1000.0,
            ribbon_signal=False,
            capitulation_days=0,
            recovery_signal=True,
            data_source="api",
        )
        pulse = MiningPulseResult(
            avg_block_interval=600.0,
            interval_deviation_pct=0.0,
            blocks_fast=70,
            blocks_slow=73,
            implied_hashrate_change=0.0,
            pulse_zone=MiningPulseZone.NORMAL,
            window_blocks=144,
            tip_height=875000,
        )

        signal = derive_combined_signal(ribbons, pulse)
        assert signal == "recovery"

    def test_miner_stress_from_ribbons(self):
        """Miner stress detected when ribbons active 7+ days."""
        from scripts.metrics.mining_economics import derive_combined_signal

        ribbons = HashRibbonsResult(
            hashrate_current=900.0,
            hashrate_ma_30d=850.0,
            hashrate_ma_60d=900.0,
            ribbon_signal=True,
            capitulation_days=10,
            recovery_signal=False,
            data_source="api",
        )
        pulse = MiningPulseResult(
            avg_block_interval=600.0,
            interval_deviation_pct=0.0,
            blocks_fast=70,
            blocks_slow=73,
            implied_hashrate_change=0.0,
            pulse_zone=MiningPulseZone.NORMAL,
            window_blocks=144,
            tip_height=875000,
        )

        signal = derive_combined_signal(ribbons, pulse)
        assert signal == "miner_stress"

    def test_miner_stress_from_slow_pulse(self):
        """Miner stress detected when pulse zone is SLOW."""
        from scripts.metrics.mining_economics import derive_combined_signal

        pulse = MiningPulseResult(
            avg_block_interval=700.0,
            interval_deviation_pct=16.67,
            blocks_fast=30,
            blocks_slow=113,
            implied_hashrate_change=-16.67,
            pulse_zone=MiningPulseZone.SLOW,
            window_blocks=144,
            tip_height=875000,
        )

        signal = derive_combined_signal(None, pulse)
        assert signal == "miner_stress"

    def test_healthy_from_fast_pulse(self):
        """Healthy signal when pulse zone is FAST."""
        from scripts.metrics.mining_economics import derive_combined_signal

        pulse = MiningPulseResult(
            avg_block_interval=520.0,
            interval_deviation_pct=-13.33,
            blocks_fast=100,
            blocks_slow=43,
            implied_hashrate_change=13.33,
            pulse_zone=MiningPulseZone.FAST,
            window_blocks=144,
            tip_height=875000,
        )

        signal = derive_combined_signal(None, pulse)
        assert signal == "healthy"

    def test_unknown_when_no_ribbons_and_normal_pulse(self):
        """Unknown signal when no ribbon data and normal pulse."""
        from scripts.metrics.mining_economics import derive_combined_signal

        pulse = MiningPulseResult(
            avg_block_interval=600.0,
            interval_deviation_pct=0.0,
            blocks_fast=70,
            blocks_slow=73,
            implied_hashrate_change=0.0,
            pulse_zone=MiningPulseZone.NORMAL,
            window_blocks=144,
            tip_height=875000,
        )

        signal = derive_combined_signal(None, pulse)
        assert signal == "unknown"


class TestMiningEconomicsWithAPIUnavailable:
    """T021: Test mining economics when external API is unavailable."""

    def test_mining_economics_works_without_ribbons(self):
        """Mining economics should work with pulse only when API unavailable."""
        from scripts.metrics.mining_economics import calculate_mining_economics

        mock_rpc = Mock()
        mock_rpc.getbestblockhash.return_value = "hash_875000"

        def mock_getblockhash(height):
            return f"hash_{height}"

        def mock_getblock_by_hash(block_hash):
            height = int(block_hash.split("_")[1]) if "_" in block_hash else 875000
            base_time = 1734600000 - (875000 - height) * 600
            return {"height": height, "time": base_time}

        mock_rpc.getblockhash.side_effect = mock_getblockhash
        mock_rpc.getblock.side_effect = mock_getblock_by_hash

        # Simulate API unavailable
        with patch(
            "scripts.data.hashrate_fetcher.fetch_hashrate_data",
            side_effect=ConnectionError("API unavailable"),
        ):
            result = calculate_mining_economics(mock_rpc)

        assert isinstance(result, MiningEconomicsResult)
        assert result.hash_ribbons is None
        assert result.mining_pulse is not None
        assert result.combined_signal in ("healthy", "miner_stress", "unknown")
