"""
Tests for Cointime Economics Framework (spec-018).

TDD test suite for:
- Coinblocks calculation (created/destroyed)
- Liveliness and Vaultedness ratios
- Active/Vaulted Supply split
- True Market Mean and AVIV ratio
- Signal generation and fusion integration
"""

import pytest

from scripts.metrics.cointime import (
    # Coinblocks functions
    calculate_coinblocks_destroyed,
    calculate_coinblocks_created,
    update_cumulative_coinblocks,
    # Liveliness functions
    calculate_liveliness,
    calculate_vaultedness,
    calculate_rolling_liveliness,
    # Supply functions
    calculate_active_supply,
    calculate_vaulted_supply,
    # Valuation functions
    calculate_true_market_mean,
    calculate_aviv,
    classify_valuation_zone,
    # Signal functions
    calculate_confidence,
    generate_cointime_signal,
)


# =============================================================================
# Phase 3: Coinblocks Tracking (US1) Tests
# =============================================================================


class TestCoinblocksDestroyed:
    """Tests for calculate_coinblocks_destroyed (T010)."""

    def test_coinblocks_destroyed_basic(self):
        """Given 1 BTC spent after 100 blocks, destroyed = 100."""
        result = calculate_coinblocks_destroyed(
            spent_btc=1.0, blocks_since_creation=100
        )
        assert result == 100.0

    def test_coinblocks_destroyed_zero_btc(self):
        """Zero BTC spent = zero destroyed."""
        result = calculate_coinblocks_destroyed(
            spent_btc=0.0, blocks_since_creation=100
        )
        assert result == 0.0

    def test_coinblocks_destroyed_zero_blocks(self):
        """Zero blocks = zero destroyed (same-block spend)."""
        result = calculate_coinblocks_destroyed(spent_btc=1.0, blocks_since_creation=0)
        assert result == 0.0

    def test_coinblocks_destroyed_large_values(self):
        """Large values should calculate correctly."""
        result = calculate_coinblocks_destroyed(
            spent_btc=1000.0, blocks_since_creation=100000
        )
        assert result == 100_000_000.0

    def test_coinblocks_destroyed_negative_btc_raises(self):
        """Negative BTC should raise ValueError."""
        with pytest.raises(ValueError, match="spent_btc must be >= 0"):
            calculate_coinblocks_destroyed(spent_btc=-1.0, blocks_since_creation=100)

    def test_coinblocks_destroyed_negative_blocks_raises(self):
        """Negative blocks should raise ValueError."""
        with pytest.raises(ValueError, match="blocks_since_creation must be >= 0"):
            calculate_coinblocks_destroyed(spent_btc=1.0, blocks_since_creation=-100)


class TestCoinblocksCreated:
    """Tests for calculate_coinblocks_created (T011)."""

    def test_coinblocks_created_basic(self):
        """Given 1 BTC held for 1 block, created = 1."""
        result = calculate_coinblocks_created(btc_amount=1.0, blocks_held=1)
        assert result == 1.0

    def test_coinblocks_created_default_blocks(self):
        """Default blocks_held is 1."""
        result = calculate_coinblocks_created(btc_amount=5.0)
        assert result == 5.0

    def test_coinblocks_created_multiple_blocks(self):
        """Multiple blocks held multiplies correctly."""
        result = calculate_coinblocks_created(btc_amount=2.0, blocks_held=50)
        assert result == 100.0

    def test_coinblocks_created_zero_btc(self):
        """Zero BTC = zero created."""
        result = calculate_coinblocks_created(btc_amount=0.0, blocks_held=100)
        assert result == 0.0

    def test_coinblocks_created_negative_btc_raises(self):
        """Negative BTC should raise ValueError."""
        with pytest.raises(ValueError, match="btc_amount must be >= 0"):
            calculate_coinblocks_created(btc_amount=-1.0)


class TestCumulativeTracking:
    """Tests for cumulative coinblocks tracking (T012)."""

    def test_cumulative_update_basic(self):
        """Update cumulative totals correctly."""
        new_created, new_destroyed = update_cumulative_coinblocks(
            previous_created=1000.0,
            previous_destroyed=300.0,
            block_created=100.0,
            block_destroyed=50.0,
        )
        assert new_created == 1100.0
        assert new_destroyed == 350.0

    def test_cumulative_from_zero(self):
        """Start from zero cumulative."""
        new_created, new_destroyed = update_cumulative_coinblocks(
            previous_created=0.0,
            previous_destroyed=0.0,
            block_created=1000.0,
            block_destroyed=0.0,
        )
        assert new_created == 1000.0
        assert new_destroyed == 0.0


# =============================================================================
# Phase 4: Liveliness (US2) Tests
# =============================================================================


class TestLivelinessCalculation:
    """Tests for calculate_liveliness (T017)."""

    def test_liveliness_basic(self):
        """Given destroyed=3B, created=10B, liveliness=0.3."""
        result = calculate_liveliness(
            cumulative_destroyed=3_000_000_000.0,
            cumulative_created=10_000_000_000.0,
        )
        assert result == pytest.approx(0.3, rel=1e-6)

    def test_liveliness_zero_destroyed(self):
        """Zero destroyed = zero liveliness."""
        result = calculate_liveliness(
            cumulative_destroyed=0.0, cumulative_created=1000.0
        )
        assert result == 0.0

    def test_liveliness_equal_destroyed_created(self):
        """Equal destroyed and created = liveliness 1.0."""
        result = calculate_liveliness(
            cumulative_destroyed=1000.0, cumulative_created=1000.0
        )
        assert result == 1.0

    def test_liveliness_zero_created_raises(self):
        """Zero cumulative_created should raise ValueError."""
        with pytest.raises(ValueError, match="cumulative_created must be > 0"):
            calculate_liveliness(cumulative_destroyed=100.0, cumulative_created=0.0)


class TestVaultednessCalculation:
    """Tests for calculate_vaultedness (T018)."""

    def test_vaultedness_basic(self):
        """Given liveliness=0.3, vaultedness=0.7."""
        result = calculate_vaultedness(liveliness=0.3)
        assert result == pytest.approx(0.7, rel=1e-6)

    def test_vaultedness_zero_liveliness(self):
        """Liveliness 0 = vaultedness 1."""
        result = calculate_vaultedness(liveliness=0.0)
        assert result == 1.0

    def test_vaultedness_full_liveliness(self):
        """Liveliness 1 = vaultedness 0."""
        result = calculate_vaultedness(liveliness=1.0)
        assert result == 0.0

    def test_vaultedness_out_of_bounds_raises(self):
        """Liveliness out of [0,1] should raise ValueError."""
        with pytest.raises(ValueError, match="liveliness must be in"):
            calculate_vaultedness(liveliness=1.5)


class TestLivelinessBounds:
    """Tests for liveliness bounds validation (T019)."""

    def test_liveliness_clamped_to_max(self):
        """Liveliness should be clamped to max 1.0."""
        # Edge case: destroyed > created (shouldn't happen in practice)
        result = calculate_liveliness(
            cumulative_destroyed=1100.0, cumulative_created=1000.0
        )
        assert result == 1.0

    def test_liveliness_clamped_to_min(self):
        """Liveliness should be clamped to min 0.0."""
        result = calculate_liveliness(
            cumulative_destroyed=0.0, cumulative_created=1000.0
        )
        assert result == 0.0


# =============================================================================
# Phase 4b: Rolling Liveliness (FR-006) Tests
# =============================================================================


class TestRollingLiveliness7d:
    """Tests for 7-day rolling liveliness (T023a)."""

    def test_rolling_7d_basic(self):
        """Calculate 7-day rolling liveliness."""
        # 7 days × 144 blocks = 1008 blocks
        destroyed = [10.0] * 1008
        created = [100.0] * 1008
        result = calculate_rolling_liveliness(destroyed, created, window_days=7)
        assert result == pytest.approx(0.1, rel=1e-6)

    def test_rolling_7d_insufficient_data(self):
        """Return None if insufficient data."""
        destroyed = [10.0] * 500
        created = [100.0] * 500
        result = calculate_rolling_liveliness(destroyed, created, window_days=7)
        assert result is None


class TestRollingLiveliness30d:
    """Tests for 30-day rolling liveliness (T023b)."""

    def test_rolling_30d_basic(self):
        """Calculate 30-day rolling liveliness."""
        # 30 days × 144 blocks = 4320 blocks
        destroyed = [20.0] * 4320
        created = [100.0] * 4320
        result = calculate_rolling_liveliness(destroyed, created, window_days=30)
        assert result == pytest.approx(0.2, rel=1e-6)


class TestRollingLiveliness90d:
    """Tests for 90-day rolling liveliness (T023c)."""

    def test_rolling_90d_basic(self):
        """Calculate 90-day rolling liveliness."""
        # 90 days × 144 blocks = 12960 blocks
        destroyed = [30.0] * 12960
        created = [100.0] * 12960
        result = calculate_rolling_liveliness(destroyed, created, window_days=90)
        assert result == pytest.approx(0.3, rel=1e-6)


# =============================================================================
# Phase 5: Supply Split (US3) Tests
# =============================================================================


class TestActiveSupply:
    """Tests for calculate_active_supply (T024)."""

    def test_active_supply_basic(self):
        """Given supply=19.5M, liveliness=0.3, active=5.85M."""
        result = calculate_active_supply(total_supply_btc=19_500_000.0, liveliness=0.3)
        assert result == pytest.approx(5_850_000.0, rel=1e-6)

    def test_active_supply_zero_liveliness(self):
        """Zero liveliness = zero active supply."""
        result = calculate_active_supply(total_supply_btc=19_500_000.0, liveliness=0.0)
        assert result == 0.0

    def test_active_supply_full_liveliness(self):
        """Full liveliness = all supply active."""
        result = calculate_active_supply(total_supply_btc=19_500_000.0, liveliness=1.0)
        assert result == 19_500_000.0


class TestVaultedSupply:
    """Tests for calculate_vaulted_supply (T025)."""

    def test_vaulted_supply_basic(self):
        """Given supply=19.5M, vaultedness=0.7, vaulted=13.65M."""
        result = calculate_vaulted_supply(
            total_supply_btc=19_500_000.0, vaultedness=0.7
        )
        assert result == pytest.approx(13_650_000.0, rel=1e-6)

    def test_vaulted_supply_zero_vaultedness(self):
        """Zero vaultedness = zero vaulted supply."""
        result = calculate_vaulted_supply(
            total_supply_btc=19_500_000.0, vaultedness=0.0
        )
        assert result == 0.0


class TestSupplySum:
    """Tests for supply conservation law (T026)."""

    def test_supply_sum_equals_total(self):
        """Active + Vaulted should equal Total Supply."""
        total = 19_500_000.0
        liveliness = 0.3
        vaultedness = 1.0 - liveliness

        active = calculate_active_supply(total, liveliness)
        vaulted = calculate_vaulted_supply(total, vaultedness)

        assert active + vaulted == pytest.approx(total, rel=1e-6)

    def test_supply_sum_various_liveliness(self):
        """Test conservation across various liveliness values."""
        total = 21_000_000.0
        for liveliness in [0.0, 0.25, 0.5, 0.75, 1.0]:
            vaultedness = 1.0 - liveliness
            active = calculate_active_supply(total, liveliness)
            vaulted = calculate_vaulted_supply(total, vaultedness)
            assert active + vaulted == pytest.approx(total, rel=1e-6)


# =============================================================================
# Phase 6: AVIV Ratio (US4) Tests
# =============================================================================


class TestTrueMarketMean:
    """Tests for calculate_true_market_mean (T030)."""

    def test_true_market_mean_basic(self):
        """Calculate true market mean."""
        # Market cap $1T, active supply 5M BTC = $200K TMM
        result = calculate_true_market_mean(
            market_cap_usd=1_000_000_000_000.0, active_supply_btc=5_000_000.0
        )
        assert result == pytest.approx(200_000.0, rel=1e-6)

    def test_true_market_mean_zero_active_raises(self):
        """Zero active supply should raise ValueError."""
        with pytest.raises(ValueError, match="active_supply_btc must be > 0"):
            calculate_true_market_mean(
                market_cap_usd=1_000_000.0, active_supply_btc=0.0
            )


class TestAvivRatio:
    """Tests for calculate_aviv (T031)."""

    def test_aviv_basic(self):
        """Given price=$100K, TMM=$50K, AVIV=2.0."""
        result = calculate_aviv(
            current_price_usd=100_000.0, true_market_mean_usd=50_000.0
        )
        assert result == pytest.approx(2.0, rel=1e-6)

    def test_aviv_undervalued(self):
        """Price below TMM = AVIV < 1."""
        result = calculate_aviv(
            current_price_usd=40_000.0, true_market_mean_usd=50_000.0
        )
        assert result == pytest.approx(0.8, rel=1e-6)

    def test_aviv_zero_tmm_raises(self):
        """Zero TMM should raise ValueError."""
        with pytest.raises(ValueError, match="true_market_mean_usd must be > 0"):
            calculate_aviv(current_price_usd=100_000.0, true_market_mean_usd=0.0)


class TestAvivZones:
    """Tests for classify_valuation_zone (T032)."""

    def test_zone_undervalued(self):
        """AVIV < 1.0 = UNDERVALUED."""
        result = classify_valuation_zone(aviv_ratio=0.8)
        assert result == "UNDERVALUED"

    def test_zone_fair(self):
        """AVIV 1.0-2.5 = FAIR."""
        result = classify_valuation_zone(aviv_ratio=1.5)
        assert result == "FAIR"

    def test_zone_overvalued(self):
        """AVIV > 2.5 = OVERVALUED."""
        result = classify_valuation_zone(aviv_ratio=3.0)
        assert result == "OVERVALUED"

    def test_zone_boundary_undervalued(self):
        """AVIV exactly 1.0 = FAIR (not undervalued)."""
        result = classify_valuation_zone(aviv_ratio=1.0)
        assert result == "FAIR"

    def test_zone_boundary_overvalued(self):
        """AVIV exactly 2.5 = FAIR (not overvalued)."""
        result = classify_valuation_zone(aviv_ratio=2.5)
        assert result == "FAIR"

    def test_zone_custom_thresholds(self):
        """Custom thresholds should work."""
        result = classify_valuation_zone(
            aviv_ratio=1.5, undervalued_threshold=0.8, overvalued_threshold=2.0
        )
        assert result == "FAIR"


# =============================================================================
# Phase 7: Fusion Integration (US5) Tests
# =============================================================================


class TestCointimeSignalGeneration:
    """Tests for generate_cointime_signal (T037)."""

    def test_signal_bullish(self):
        """Undervalued + dormant = bullish signal."""
        signal = generate_cointime_signal(
            liveliness=0.1,
            liveliness_7d_change=-0.02,
            liveliness_30d_change=-0.05,
            aviv_ratio=0.7,
            active_supply_btc=5_000_000.0,
        )
        assert signal["cointime_vote"] > 0.5
        assert signal["valuation_zone"] == "UNDERVALUED"
        assert signal["extreme_dormancy"] is True

    def test_signal_bearish(self):
        """Overvalued + active = bearish signal."""
        signal = generate_cointime_signal(
            liveliness=0.5,
            liveliness_7d_change=0.03,
            liveliness_30d_change=0.1,
            aviv_ratio=3.0,
            active_supply_btc=10_000_000.0,
        )
        assert signal["cointime_vote"] < -0.5
        assert signal["valuation_zone"] == "OVERVALUED"
        assert signal["distribution_warning"] is True

    def test_signal_neutral(self):
        """Fair value + stable = neutral signal."""
        signal = generate_cointime_signal(
            liveliness=0.25,
            liveliness_7d_change=0.0,
            liveliness_30d_change=0.0,
            aviv_ratio=1.5,
            active_supply_btc=5_000_000.0,
        )
        assert -0.3 < signal["cointime_vote"] < 0.3
        assert signal["valuation_zone"] == "FAIR"

    def test_signal_supply_squeeze(self):
        """Detect supply squeeze when active supply declining."""
        signal = generate_cointime_signal(
            liveliness=0.2,
            liveliness_7d_change=-0.01,
            liveliness_30d_change=-0.03,
            aviv_ratio=1.2,
            active_supply_btc=4_000_000.0,
            previous_active_supply_btc=5_000_000.0,
        )
        assert signal["supply_squeeze"] is True

    def test_confidence_calculation(self):
        """Test confidence ranges."""
        confidence = calculate_confidence(
            cointime_vote=0.8, aviv_ratio=0.5, extreme_dormancy=True
        )
        assert 0.5 <= confidence <= 1.0
        # High vote + extreme zone + dormancy = high confidence
        assert confidence >= 0.8


# =============================================================================
# Phase 7: Fusion Integration (US5) Tests - T038
# =============================================================================


class TestFusionWithCointime:
    """Tests for Cointime integration with enhanced_fusion (T038)."""

    def test_fusion_accepts_cointime_vote(self):
        """T038a: enhanced_fusion accepts cointime_vote parameter."""
        from scripts.metrics.monte_carlo_fusion import enhanced_fusion

        result = enhanced_fusion(
            whale_vote=0.5,
            whale_conf=0.8,
            cointime_vote=0.7,
            cointime_conf=0.9,
        )

        assert result.cointime_vote == 0.7
        assert "cointime" in result.components_used
        assert result.components_available == 2

    def test_fusion_cointime_weight_applied(self):
        """T038b: Cointime weight is properly applied in fusion."""
        from scripts.metrics.monte_carlo_fusion import enhanced_fusion, ENHANCED_WEIGHTS

        # Verify cointime weight exists and is 0.14 (spec-019: increased from 0.12)
        assert "cointime" in ENHANCED_WEIGHTS
        assert ENHANCED_WEIGHTS["cointime"] == 0.14

        # Test fusion with only cointime
        result = enhanced_fusion(cointime_vote=1.0, cointime_conf=1.0)

        # With only cointime, weight should be renormalized to 1.0
        assert result.cointime_weight == 1.0
        assert result.signal_mean > 0  # Should be positive from positive vote

    def test_fusion_all_9_components(self):
        """T038c: Fusion with all 9 components produces valid result."""
        from scripts.metrics.monte_carlo_fusion import enhanced_fusion

        result = enhanced_fusion(
            whale_vote=0.8,
            whale_conf=0.9,
            utxo_vote=0.6,
            utxo_conf=0.8,
            funding_vote=0.3,
            oi_vote=0.2,
            power_law_vote=0.5,
            symbolic_vote=0.7,
            fractal_vote=0.4,
            wasserstein_vote=0.3,
            cointime_vote=0.6,
            cointime_conf=0.85,
        )

        assert result.components_available == 9
        assert len(result.components_used) == 9
        assert "cointime" in result.components_used
        assert result.cointime_vote == 0.6
        assert result.signal_mean > 0  # All positive votes
        assert result.action in ["BUY", "SELL", "HOLD"]

    def test_fusion_weights_sum_to_one(self):
        """T038d: ENHANCED_WEIGHTS must sum to 1.0."""
        from scripts.metrics.monte_carlo_fusion import ENHANCED_WEIGHTS

        total = sum(ENHANCED_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"Weights sum to {total}, expected 1.0"

    def test_fusion_cointime_missing(self):
        """T038e: Fusion works without cointime (backward compatible)."""
        from scripts.metrics.monte_carlo_fusion import enhanced_fusion

        result = enhanced_fusion(
            whale_vote=0.8,
            whale_conf=0.9,
            utxo_vote=0.6,
            utxo_conf=0.8,
        )

        assert result.cointime_vote is None
        assert result.cointime_weight == 0.0
        assert "cointime" not in result.components_used
        assert result.components_available == 2
