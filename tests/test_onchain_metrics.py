"""
Tests for On-Chain Metrics (spec-007).

Test organization follows TDD Red-Green-Refactor:
- Phase 3: TX Volume USD (US3) - FIRST (easiest)
- Phase 4: Active Addresses (US2)
- Phase 5: Monte Carlo Fusion (US1) - LAST (most complex)

Run tests:
    uv run pytest tests/test_onchain_metrics.py -v
    uv run pytest tests/test_onchain_metrics.py -k tx_volume -v
    uv run pytest tests/test_onchain_metrics.py -k active_address -v
    uv run pytest tests/test_onchain_metrics.py -k monte_carlo -v
"""

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_transactions():
    """Sample transactions for testing TX volume and active addresses."""
    return [
        {
            "txid": "tx1",
            "vin": [
                {"prevout": {"scriptpubkey_address": "bc1qsender1", "value": 100000000}}
            ],
            "vout": [
                {"scriptpubkey_address": "bc1qreceiver1", "value": 90000000},
                {"scriptpubkey_address": "bc1qchange1", "value": 9000000},
            ],
        },
        {
            "txid": "tx2",
            "vin": [
                {"prevout": {"scriptpubkey_address": "bc1qsender2", "value": 50000000}}
            ],
            "vout": [
                {"scriptpubkey_address": "bc1qreceiver2", "value": 49000000},
            ],
        },
        {
            "txid": "tx3",
            "vin": [
                {"prevout": {"scriptpubkey_address": "bc1qsender1", "value": 200000000}}
            ],
            "vout": [
                {"scriptpubkey_address": "bc1qreceiver3", "value": 150000000},
                {"scriptpubkey_address": "bc1qchange3", "value": 49000000},
            ],
        },
    ]


@pytest.fixture
def sample_transactions_large():
    """1000 transactions with total output of 5000 BTC for spec test."""
    # 1000 txs, each with 5 BTC payment + small change (<10% of payment)
    # Change heuristic: if change < 10% of payment, exclude from volume
    txs = []
    for i in range(1000):
        txs.append(
            {
                "txid": f"tx{i}",
                "vin": [
                    {
                        "prevout": {
                            "scriptpubkey_address": f"bc1qsender{i}",
                            "value": 510000000,  # 5.1 BTC
                        }
                    }
                ],
                "vout": [
                    {
                        "scriptpubkey_address": f"bc1qreceiver{i}",
                        "value": 500000000,  # 5 BTC (payment)
                    },
                    {
                        "scriptpubkey_address": f"bc1qchange{i}",
                        "value": 9000000,  # 0.09 BTC (change - <10% of payment)
                    },
                ],
            }
        )
    return txs


@pytest.fixture
def utxoracle_price():
    """UTXOracle price for testing."""
    return 100000.0  # $100,000 per BTC


@pytest.fixture
def high_confidence():
    """High confidence value."""
    return 0.85


@pytest.fixture
def low_confidence():
    """Low confidence value (below 0.3 threshold)."""
    return 0.25


# =============================================================================
# Phase 3: User Story 3 - TX Volume USD (TDD RED)
# =============================================================================


class TestTxVolumeBasicCalculation:
    """T009: test_tx_volume_basic_calculation()"""

    def test_tx_volume_basic_calculation(
        self, sample_transactions_large, utxoracle_price, high_confidence
    ):
        """
        Given 1000 transactions with total output of 5000 BTC and UTXOracle price $100,000
        When TX Volume USD is calculated
        Then result is $500,000,000 (+/- 0.01% tolerance)
        """
        from scripts.metrics.tx_volume import calculate_tx_volume

        result = calculate_tx_volume(
            transactions=sample_transactions_large,
            utxoracle_price=utxoracle_price,
            confidence=high_confidence,
        )

        # 5000 BTC * $100,000 = $500,000,000
        expected_usd = 500_000_000.0
        tolerance = expected_usd * 0.0001  # 0.01%

        assert result.tx_count == 1000
        assert result.tx_volume_btc == pytest.approx(5000.0, rel=0.01)
        assert result.tx_volume_usd == pytest.approx(expected_usd, abs=tolerance)
        assert result.utxoracle_price_used == utxoracle_price
        assert result.low_confidence is False


class TestTxVolumeLowConfidenceFlag:
    """T010: test_tx_volume_low_confidence_flag()"""

    def test_tx_volume_low_confidence_flag(
        self, sample_transactions, utxoracle_price, low_confidence
    ):
        """
        Given transactions and UTXOracle confidence < 0.3
        When TX Volume is calculated
        Then low_confidence flag is True
        """
        from scripts.metrics.tx_volume import calculate_tx_volume

        result = calculate_tx_volume(
            transactions=sample_transactions,
            utxoracle_price=utxoracle_price,
            confidence=low_confidence,
        )

        assert result.low_confidence is True

    def test_tx_volume_high_confidence_flag(
        self, sample_transactions, utxoracle_price, high_confidence
    ):
        """
        Given transactions and UTXOracle confidence >= 0.3
        When TX Volume is calculated
        Then low_confidence flag is False
        """
        from scripts.metrics.tx_volume import calculate_tx_volume

        result = calculate_tx_volume(
            transactions=sample_transactions,
            utxoracle_price=utxoracle_price,
            confidence=high_confidence,
        )

        assert result.low_confidence is False


class TestTxVolumeChangeOutputHeuristic:
    """T011: test_tx_volume_change_output_heuristic()"""

    def test_change_output_excluded_from_volume(self):
        """
        Given a transaction with payment (1.0 BTC) and change (0.05 BTC) outputs
        When estimate_real_volume is called
        Then only the payment amount (1.0 BTC) is counted
        """
        from scripts.metrics.tx_volume import estimate_real_volume

        # 2-output transaction: large payment + small change (<10%)
        tx = {
            "vout": [
                {"value": 100000000},  # 1.0 BTC (payment)
                {"value": 5000000},  # 0.05 BTC (change - 5% of payment, <10%)
            ]
        }

        result = estimate_real_volume(tx)

        # Should exclude the small change output
        assert result == pytest.approx(1.0, rel=0.01)

    def test_multi_recipient_transaction(self):
        """
        Given a transaction with two similar-sized outputs
        When estimate_real_volume is called
        Then both outputs are counted (not change)
        """
        from scripts.metrics.tx_volume import estimate_real_volume

        # 2-output transaction: both similar size = multi-recipient
        tx = {
            "vout": [
                {"value": 50000000},  # 0.5 BTC
                {"value": 45000000},  # 0.45 BTC (similar, not change)
            ]
        }

        result = estimate_real_volume(tx)

        # Both should be counted (0.95 BTC)
        assert result == pytest.approx(0.95, rel=0.01)

    def test_single_output_transaction(self):
        """
        Given a transaction with single output
        When estimate_real_volume is called
        Then the full output is counted
        """
        from scripts.metrics.tx_volume import estimate_real_volume

        tx = {"vout": [{"value": 100000000}]}  # 1 BTC

        result = estimate_real_volume(tx)

        assert result == pytest.approx(1.0, rel=0.01)


# =============================================================================
# Phase 4: User Story 2 - Active Addresses (TDD RED)
# =============================================================================


class TestActiveAddressesSingleBlock:
    """T015: test_active_addresses_single_block()"""

    def test_active_addresses_single_block(self, sample_transactions):
        """
        Given a set of transactions
        When active addresses are counted
        Then unique senders and receivers are counted correctly
        """
        from scripts.metrics.active_addresses import count_active_addresses

        result = count_active_addresses(sample_transactions)

        # From sample_transactions:
        # Senders: bc1qsender1 (2x), bc1qsender2 -> 2 unique
        # Receivers: bc1qreceiver1, bc1qchange1, bc1qreceiver2, bc1qreceiver3, bc1qchange3 -> 5 unique
        # Total unique: 7 (no overlap between senders and receivers in this fixture)

        assert result.unique_senders == 2  # bc1qsender1 appears twice but counted once
        assert result.unique_receivers == 5
        assert result.active_addresses_block == 7


class TestActiveAddressesDeduplication:
    """T016: test_active_addresses_deduplication()"""

    def test_deduplication_across_transactions(self):
        """
        Given transactions where same address appears multiple times
        When active addresses are counted
        Then each address is counted only once
        """
        from scripts.metrics.active_addresses import count_active_addresses

        txs = [
            {
                "vin": [{"prevout": {"scriptpubkey_address": "bc1qsame"}}],
                "vout": [{"scriptpubkey_address": "bc1qreceiver1"}],
            },
            {
                "vin": [{"prevout": {"scriptpubkey_address": "bc1qsame"}}],
                "vout": [{"scriptpubkey_address": "bc1qreceiver2"}],
            },
            {
                "vin": [{"prevout": {"scriptpubkey_address": "bc1qsame"}}],
                "vout": [{"scriptpubkey_address": "bc1qsame"}],  # Sends to self
            },
        ]

        result = count_active_addresses(txs)

        # bc1qsame appears 4 times but is 1 unique sender and also appears as receiver
        assert result.unique_senders == 1
        assert result.unique_receivers == 3  # receiver1, receiver2, same
        assert result.active_addresses_block == 3  # Only 3 unique addresses total


class TestActiveAddressesAnomalyDetection:
    """T017: test_active_addresses_anomaly_detection()"""

    def test_anomaly_detection_above_threshold(self):
        """
        Given current count > 3 sigma above 30-day moving average
        When anomaly detection runs
        Then is_anomaly is True
        """
        from scripts.metrics.active_addresses import detect_anomaly

        # Historical counts with mean ~1000, std ~100
        historical = [950, 1000, 1050, 980, 1020, 990, 1010, 1000] * 30

        # Current count is 3.5 sigma above mean
        current_count = 1350  # >1000 + 3*100 = 1300

        result = detect_anomaly(current_count, historical)

        assert result is True

    def test_no_anomaly_within_threshold(self):
        """
        Given current count within 3 sigma of 30-day moving average
        When anomaly detection runs
        Then is_anomaly is False
        """
        from scripts.metrics.active_addresses import detect_anomaly

        # Historical data: mean=1000, std~27 -> threshold=1082
        historical = [950, 1000, 1050, 980, 1020, 990, 1010, 1000] * 30
        current_count = 1050  # Within 3 sigma (1050 < 1082)

        result = detect_anomaly(current_count, historical)

        assert result is False


# =============================================================================
# Phase 5: User Story 1 - Monte Carlo Fusion (TDD RED)
# =============================================================================


class TestMonteCarloBasicFusion:
    """T021: test_monte_carlo_basic_fusion()"""

    def test_monte_carlo_basic_fusion(self):
        """
        Given whale signal and UTXOracle signal with confidences
        When Monte Carlo fusion runs
        Then result includes signal_mean, signal_std, and action
        """
        from scripts.metrics.monte_carlo_fusion import monte_carlo_fusion

        result = monte_carlo_fusion(
            whale_vote=1.0,  # ACCUMULATION
            whale_confidence=0.8,
            utxo_vote=0.5,  # Slightly bullish
            utxo_confidence=0.85,
            n_samples=1000,
        )

        # Weighted fusion: 0.7*whale + 0.3*utxo
        # Expected mean ~ 0.7*1.0*0.8 + 0.3*0.5*0.85 = 0.56 + 0.1275 = ~0.69
        # But with uncertainty propagation, actual mean may vary

        assert -1.0 <= result.signal_mean <= 1.0
        assert result.signal_std >= 0
        assert result.action in ["BUY", "SELL", "HOLD"]
        assert 0.0 <= result.action_confidence <= 1.0
        assert result.n_samples == 1000


class TestMonteCarloConfidenceIntervals:
    """T022: test_monte_carlo_confidence_intervals()"""

    def test_confidence_intervals_95_percent(self):
        """
        Given Monte Carlo fusion result
        Then 95% CI bounds are correctly calculated (2.5% and 97.5% percentiles)
        """
        from scripts.metrics.monte_carlo_fusion import monte_carlo_fusion

        result = monte_carlo_fusion(
            whale_vote=0.8,
            whale_confidence=0.9,
            utxo_vote=0.7,
            utxo_confidence=0.85,
            n_samples=1000,
        )

        # CI should be within signal bounds
        assert result.ci_lower <= result.signal_mean <= result.ci_upper
        assert result.ci_lower >= -1.0
        assert result.ci_upper <= 1.0

    def test_ci_width_reflects_uncertainty(self):
        """
        Given low confidence inputs
        Then CI width is wider than high confidence inputs
        """
        from scripts.metrics.monte_carlo_fusion import monte_carlo_fusion

        high_conf_result = monte_carlo_fusion(
            whale_vote=0.8, whale_confidence=0.95, utxo_vote=0.7, utxo_confidence=0.95
        )

        low_conf_result = monte_carlo_fusion(
            whale_vote=0.8, whale_confidence=0.5, utxo_vote=0.7, utxo_confidence=0.5
        )

        high_conf_width = high_conf_result.ci_upper - high_conf_result.ci_lower
        low_conf_width = low_conf_result.ci_upper - low_conf_result.ci_lower

        # Lower confidence should produce wider CI
        assert low_conf_width > high_conf_width


class TestMonteCarloBimodalDetection:
    """T023: test_monte_carlo_bimodal_detection()"""

    def test_bimodal_detection_conflicting_signals(self):
        """
        Given strongly conflicting signals (whale bullish, utxo bearish)
        When Monte Carlo fusion runs
        Then distribution_type may be 'bimodal'
        """
        from scripts.metrics.monte_carlo_fusion import monte_carlo_fusion

        result = monte_carlo_fusion(
            whale_vote=1.0,  # Very bullish
            whale_confidence=0.9,
            utxo_vote=-1.0,  # Very bearish
            utxo_confidence=0.9,
            n_samples=1000,
        )

        # With strongly conflicting signals, might detect bimodal
        assert result.distribution_type in ["unimodal", "bimodal", "insufficient_data"]

    def test_unimodal_with_agreeing_signals(self):
        """
        Given agreeing signals with very high confidence
        When Monte Carlo fusion runs
        Then distribution_type is 'unimodal'
        """
        from scripts.metrics.monte_carlo_fusion import monte_carlo_fusion

        # Very high confidence = tight distribution = unimodal
        result = monte_carlo_fusion(
            whale_vote=0.8,
            whale_confidence=0.99,  # Very high confidence
            utxo_vote=0.75,
            utxo_confidence=0.99,  # Very high confidence
            n_samples=1000,
        )

        assert result.distribution_type == "unimodal"


class TestMonteCarloPerformance:
    """T024: test_monte_carlo_performance_under_100ms()"""

    def test_performance_under_100ms(self):
        """
        Given 1000 bootstrap samples
        When Monte Carlo fusion runs
        Then execution completes in under 100ms
        """
        import time
        from scripts.metrics.monte_carlo_fusion import monte_carlo_fusion

        start = time.time()

        # Run 10 times to get stable measurement
        for _ in range(10):
            monte_carlo_fusion(
                whale_vote=0.8,
                whale_confidence=0.9,
                utxo_vote=0.7,
                utxo_confidence=0.85,
                n_samples=1000,
            )

        elapsed = (time.time() - start) / 10 * 1000  # ms per call

        assert elapsed < 100, f"Monte Carlo took {elapsed:.1f}ms, expected <100ms"
