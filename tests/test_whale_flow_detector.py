"""
Unit tests for Whale Flow Detector

TDD Approach: These tests are written BEFORE implementation.
They define the expected behavior of the whale flow detection system.

Test Coverage:
- CSV loading and validation
- Address parsing from transactions
- Transaction classification (inflow/outflow/internal/unrelated)
- Net flow calculation
- Direction determination (ACCUMULATION/DISTRIBUTION/NEUTRAL)
- Signal validation and integrity
"""

import pytest
import json
import csv
from pathlib import Path

# Import will fail initially (RED phase) - this is expected
try:
    from scripts.whale_flow_detector import WhaleFlowDetector
except ImportError:
    WhaleFlowDetector = None

# Import contract from specs directory (add to path if needed)
import sys

specs_contracts_path = Path(
    "/media/sam/1TB/UTXOracle/specs/004-whale-flow-detection/contracts"
)
if str(specs_contracts_path) not in sys.path:
    sys.path.insert(0, str(specs_contracts_path))

from whale_flow_detector_interface import WhaleFlowSignal


# Fixtures
@pytest.fixture
def exchange_addresses_csv():
    """Path to exchange addresses CSV."""
    return "/media/sam/1TB/UTXOracle/data/exchange_addresses.csv"


@pytest.fixture
def exchange_addresses_set(exchange_addresses_csv):
    """Load exchange addresses into a set (O(1) lookup)."""
    addresses = set()
    with open(exchange_addresses_csv, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            addresses.add(row["address"])
    return addresses


@pytest.fixture
def whale_transactions_sample():
    """Load sample transactions from fixtures."""
    fixture_path = Path(
        "/media/sam/1TB/UTXOracle/tests/fixtures/whale_transactions_sample.json"
    )
    with open(fixture_path, "r") as f:
        return json.load(f)


# T016: test_load_exchange_addresses_csv()
def test_load_exchange_addresses_csv(exchange_addresses_csv):
    """
    Test loading exchange addresses from CSV into a set.

    Success Criteria:
    - CSV file loads without errors
    - Returns a set for O(1) lookup
    - Contains expected exchange addresses (10 for MVP)
    - Known addresses (1F1tAaz5x1HUXrCNLbtMDqcw6o5GNn4xqX) are present
    """
    if WhaleFlowDetector is None:
        pytest.skip("WhaleFlowDetector not implemented yet (RED phase)")

    detector = WhaleFlowDetector(exchange_addresses_csv)

    # Verify exchange addresses loaded
    address_count = detector.get_exchange_address_count()
    assert address_count > 0, "No exchange addresses loaded"
    assert address_count >= 10, f"Expected at least 10 addresses, got {address_count}"

    # Verify known Binance address is present
    addresses = detector._exchange_addresses
    assert "1F1tAaz5x1HUXrCNLbtMDqcw6o5GNn4xqX" in addresses, (
        "Known Binance address not found"
    )


# T017: test_parse_addresses_from_transaction()
def test_parse_addresses_from_transaction(whale_transactions_sample):
    """
    Test extracting input/output addresses from transaction JSON.

    Success Criteria:
    - Correctly parses input addresses from vin[].prevout.scriptpubkey_address
    - Correctly parses output addresses from vout[].scriptpubkey_address
    - Handles missing addresses gracefully (OP_RETURN, coinbase)
    - Returns lists of addresses
    """
    if WhaleFlowDetector is None:
        pytest.skip("WhaleFlowDetector not implemented yet (RED phase)")

    # Test with INFLOW transaction (index 0)
    tx = whale_transactions_sample[0]
    detector = WhaleFlowDetector("/media/sam/1TB/UTXOracle/data/exchange_addresses.csv")

    input_addrs, output_addrs = detector._parse_addresses(tx)

    # Verify parsing
    assert len(input_addrs) == 1, f"Expected 1 input address, got {len(input_addrs)}"
    assert len(output_addrs) == 1, f"Expected 1 output address, got {len(output_addrs)}"
    assert (
        input_addrs[0] == "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
    )  # Personal wallet (fixed)
    assert output_addrs[0] == "1F1tAaz5x1HUXrCNLbtMDqcw6o5GNn4xqX"  # Binance exchange


# T018: test_classify_transaction_inflow()
def test_classify_transaction_inflow(whale_transactions_sample, exchange_addresses_set):
    """
    Test classification of INFLOW transactions (personal → exchange).

    Success Criteria:
    - Returns flow_type="inflow"
    - Returns direction_multiplier=1 (bearish)
    """
    if WhaleFlowDetector is None:
        pytest.skip("WhaleFlowDetector not implemented yet (RED phase)")

    tx = whale_transactions_sample[0]  # INFLOW example
    detector = WhaleFlowDetector("/media/sam/1TB/UTXOracle/data/exchange_addresses.csv")

    input_addrs, output_addrs = detector._parse_addresses(tx)
    flow_type, multiplier = detector._classify_transaction(input_addrs, output_addrs)

    assert flow_type == "inflow", f"Expected 'inflow', got '{flow_type}'"
    assert multiplier == 1, f"Expected multiplier=1, got {multiplier}"


# T019: test_classify_transaction_outflow()
def test_classify_transaction_outflow(
    whale_transactions_sample, exchange_addresses_set
):
    """
    Test classification of OUTFLOW transactions (exchange → personal).

    Success Criteria:
    - Returns flow_type="outflow"
    - Returns direction_multiplier=-1 (bullish)
    """
    if WhaleFlowDetector is None:
        pytest.skip("WhaleFlowDetector not implemented yet (RED phase)")

    tx = whale_transactions_sample[1]  # OUTFLOW example
    detector = WhaleFlowDetector("/media/sam/1TB/UTXOracle/data/exchange_addresses.csv")

    input_addrs, output_addrs = detector._parse_addresses(tx)
    flow_type, multiplier = detector._classify_transaction(input_addrs, output_addrs)

    assert flow_type == "outflow", f"Expected 'outflow', got '{flow_type}'"
    assert multiplier == -1, f"Expected multiplier=-1, got {multiplier}"


# T020: test_classify_transaction_internal()
def test_classify_transaction_internal(
    whale_transactions_sample, exchange_addresses_set
):
    """
    Test classification of INTERNAL transactions (exchange → exchange).

    Success Criteria:
    - Returns flow_type="internal"
    - Returns direction_multiplier=0 (neutral)
    """
    if WhaleFlowDetector is None:
        pytest.skip("WhaleFlowDetector not implemented yet (RED phase)")

    tx = whale_transactions_sample[2]  # INTERNAL example
    detector = WhaleFlowDetector("/media/sam/1TB/UTXOracle/data/exchange_addresses.csv")

    input_addrs, output_addrs = detector._parse_addresses(tx)
    flow_type, multiplier = detector._classify_transaction(input_addrs, output_addrs)

    assert flow_type == "internal", f"Expected 'internal', got '{flow_type}'"
    assert multiplier == 0, f"Expected multiplier=0, got {multiplier}"


# T021: test_calculate_net_flow()
def test_calculate_net_flow(whale_transactions_sample):
    """
    Test net flow calculation (inflow - outflow) for a block.

    Success Criteria:
    - Correctly sums inflow BTC (personal → exchange)
    - Correctly sums outflow BTC (exchange → personal)
    - Ignores internal transfers (exchange → exchange)
    - Returns net_flow = inflow - outflow
    """
    if WhaleFlowDetector is None:
        pytest.skip("WhaleFlowDetector not implemented yet (RED phase)")

    # Use first 3 transactions: inflow (50.1 BTC), outflow (25.5 BTC), internal (100 BTC)
    detector = WhaleFlowDetector("/media/sam/1TB/UTXOracle/data/exchange_addresses.csv")

    # Mock transaction processing
    test_txs = whale_transactions_sample[:3]
    inflow_btc, outflow_btc, internal_btc, _ = detector._calculate_net_flow(test_txs)

    # Verify calculations (values in satoshis in fixture, converted to BTC)
    assert abs(inflow_btc - 50.1) < 0.1, f"Expected ~50.1 BTC inflow, got {inflow_btc}"
    assert abs(outflow_btc - 25.5) < 0.1, (
        f"Expected ~25.5 BTC outflow, got {outflow_btc}"
    )
    assert abs(internal_btc - 100.0) < 0.1, (
        f"Expected ~100 BTC internal, got {internal_btc}"
    )


# T022: test_determine_direction_accumulation()
def test_determine_direction_accumulation():
    """
    Test direction classification for ACCUMULATION (net outflow > 100 BTC).

    Success Criteria:
    - net_flow < -100 → direction="ACCUMULATION" (bullish)
    """
    if WhaleFlowDetector is None:
        pytest.skip("WhaleFlowDetector not implemented yet (RED phase)")

    detector = WhaleFlowDetector("/media/sam/1TB/UTXOracle/data/exchange_addresses.csv")

    # Simulate large outflow (whales withdrawing)
    net_flow_btc = -150.0  # 150 BTC outflow
    direction = detector._determine_direction(net_flow_btc)

    assert direction == "ACCUMULATION", f"Expected 'ACCUMULATION', got '{direction}'"


# T023: test_determine_direction_distribution()
def test_determine_direction_distribution():
    """
    Test direction classification for DISTRIBUTION (net inflow > 100 BTC).

    Success Criteria:
    - net_flow > 100 → direction="DISTRIBUTION" (bearish)
    """
    if WhaleFlowDetector is None:
        pytest.skip("WhaleFlowDetector not implemented yet (RED phase)")

    detector = WhaleFlowDetector("/media/sam/1TB/UTXOracle/data/exchange_addresses.csv")

    # Simulate large inflow (whales depositing to sell)
    net_flow_btc = 150.0  # 150 BTC inflow
    direction = detector._determine_direction(net_flow_btc)

    assert direction == "DISTRIBUTION", f"Expected 'DISTRIBUTION', got '{direction}'"


# T024: test_determine_direction_neutral()
def test_determine_direction_neutral():
    """
    Test direction classification for NEUTRAL (net flow between -100 and +100 BTC).

    Success Criteria:
    - -100 < net_flow < 100 → direction="NEUTRAL"
    """
    if WhaleFlowDetector is None:
        pytest.skip("WhaleFlowDetector not implemented yet (RED phase)")

    detector = WhaleFlowDetector("/media/sam/1TB/UTXOracle/data/exchange_addresses.csv")

    # Simulate small net flow
    for net_flow in [0, 50, -50, 99, -99]:
        direction = detector._determine_direction(net_flow)
        assert direction == "NEUTRAL", (
            f"Expected 'NEUTRAL' for net_flow={net_flow}, got '{direction}'"
        )


# T025: test_analyze_block_with_mock_data()
def test_analyze_block_with_mock_data(whale_transactions_sample):
    """
    Test full block analysis with mock transaction data.

    Success Criteria:
    - Returns WhaleFlowSignal with all required fields
    - Correctly calculates net_flow_btc
    - Correctly determines direction
    - Confidence score is between 0.0 and 1.0
    """
    if WhaleFlowDetector is None:
        pytest.skip("WhaleFlowDetector not implemented yet (RED phase)")

    detector = WhaleFlowDetector("/media/sam/1TB/UTXOracle/data/exchange_addresses.csv")

    # Mock analyze_block to use fixture data instead of API call
    # (Integration tests will test real API)
    signal = detector._analyze_transactions(
        whale_transactions_sample[:10], block_height=922000, timestamp=1730000000
    )

    # Verify signal structure
    assert isinstance(signal, WhaleFlowSignal), "Should return WhaleFlowSignal instance"
    assert signal.block_height == 922000
    assert signal.timestamp == 1730000000
    assert 0.0 <= signal.confidence <= 1.0, (
        f"Confidence out of range: {signal.confidence}"
    )
    assert signal.direction in ["ACCUMULATION", "DISTRIBUTION", "NEUTRAL"]
    assert signal.tx_count_total == 10
    assert signal.tx_count_relevant > 0


# T026: test_whale_flow_signal_validation()
def test_whale_flow_signal_validation():
    """
    Test WhaleFlowSignal dataclass validation logic.

    Success Criteria:
    - Accepts valid signals
    - Rejects invalid direction values
    - Rejects confidence outside [0.0, 1.0]
    - Validates net_flow = inflow - outflow
    """
    # Valid signal
    valid_signal = WhaleFlowSignal(
        net_flow_btc=50.0,
        direction="DISTRIBUTION",
        confidence=0.75,
        inflow_btc=100.0,
        outflow_btc=50.0,
        internal_btc=200.0,
        tx_count_total=2500,
        tx_count_relevant=320,
        block_height=922000,
        timestamp=1730000000,
    )
    assert valid_signal.direction == "DISTRIBUTION"

    # Invalid direction
    with pytest.raises(ValueError, match="Invalid direction"):
        WhaleFlowSignal(
            net_flow_btc=50.0,
            direction="INVALID",  # Wrong!
            confidence=0.75,
            inflow_btc=100.0,
            outflow_btc=50.0,
            internal_btc=0,
            tx_count_total=100,
            tx_count_relevant=10,
            block_height=922000,
            timestamp=1730000000,
        )

    # Invalid confidence
    with pytest.raises(ValueError, match="Confidence must be between"):
        WhaleFlowSignal(
            net_flow_btc=50.0,
            direction="NEUTRAL",
            confidence=1.5,  # Out of range!
            inflow_btc=100.0,
            outflow_btc=50.0,
            internal_btc=0,
            tx_count_total=100,
            tx_count_relevant=10,
            block_height=922000,
            timestamp=1730000000,
        )

    # Inconsistent net flow
    with pytest.raises(ValueError, match="doesn't match inflow - outflow"):
        WhaleFlowSignal(
            net_flow_btc=999.0,  # Wrong! Should be 100 - 50 = 50
            direction="NEUTRAL",
            confidence=0.5,
            inflow_btc=100.0,
            outflow_btc=50.0,
            internal_btc=0,
            tx_count_total=100,
            tx_count_relevant=10,
            block_height=922000,
            timestamp=1730000000,
        )


# ===== Phase 4: Signal Fusion Tests (T045-T048) =====


# T045: test_signal_fusion_buy_scenario()
def test_signal_fusion_buy_scenario():
    """
    Test signal fusion for BUY scenario (whale bullish + UTXOracle confident).

    Scenario:
    - Whale signal: ACCUMULATION (net_flow < -100 BTC) → whale_vote = 1.0 (bullish)
    - UTXOracle confidence: 0.8 → utxo_vote = 1.0 (confident in price)
    - Combined signal: 0.7 * 1.0 + 0.3 * 1.0 = 1.0
    - Action: BUY (combined_signal > 0.5)

    Success Criteria:
    - whale_vote = 1.0
    - utxo_vote = 1.0
    - combined_signal = 1.0
    - action = "BUY"
    """
    # Import signal fusion helpers (will fail initially - RED phase)
    try:
        from scripts.daily_analysis import (
            _calculate_whale_vote,
            _calculate_utxo_vote,
            _fuse_signals,
            _determine_action,
        )
    except ImportError:
        pytest.skip("Signal fusion methods not implemented yet (RED phase)")

    # Whale signal: ACCUMULATION (-150 BTC net outflow)
    whale_vote = _calculate_whale_vote(net_flow_btc=-150.0, direction="ACCUMULATION")
    assert whale_vote == 1.0, f"Expected whale_vote=1.0 (bullish), got {whale_vote}"

    # UTXOracle: High confidence (0.8)
    utxo_vote = _calculate_utxo_vote(confidence=0.8)
    assert utxo_vote == 1.0, f"Expected utxo_vote=1.0 (confident), got {utxo_vote}"

    # Combined signal: 70% whale + 30% utxo
    combined_signal = _fuse_signals(whale_vote, utxo_vote)
    assert abs(combined_signal - 1.0) < 0.01, (
        f"Expected combined_signal=1.0, got {combined_signal}"
    )

    # Action: BUY (signal > 0.5)
    action = _determine_action(combined_signal)
    assert action == "BUY", f"Expected action='BUY', got '{action}'"


# T046: test_signal_fusion_sell_scenario()
def test_signal_fusion_sell_scenario():
    """
    Test signal fusion for SELL scenario (whale bearish + UTXOracle confident).

    Scenario:
    - Whale signal: DISTRIBUTION (net_flow > +100 BTC) → whale_vote = -1.0 (bearish)
    - UTXOracle confidence: 0.7 → utxo_vote = 1.0 (confident)
    - Combined signal: 0.7 * (-1.0) + 0.3 * 1.0 = -0.4
    - Action: HOLD (signal between -0.5 and 0.5)

    However, if whale signal is VERY bearish (e.g., +500 BTC inflow):
    - whale_vote = -1.0
    - utxo_vote = 1.0
    - Combined signal: 0.7 * (-1.0) + 0.3 * 1.0 = -0.4 (still HOLD)

    For SELL, we need weak UTXOracle OR very strong whale signal.
    Let's test: whale -1.0, utxo 0.0 (low confidence)
    - Combined: 0.7 * (-1.0) + 0.3 * 0.0 = -0.7
    - Action: SELL (signal < -0.5)

    Success Criteria:
    - whale_vote = -1.0
    - utxo_vote = 0.0 (low confidence → neutral)
    - combined_signal = -0.7
    - action = "SELL"
    """
    try:
        from scripts.daily_analysis import (
            _calculate_whale_vote,
            _calculate_utxo_vote,
            _fuse_signals,
            _determine_action,
        )
    except ImportError:
        pytest.skip("Signal fusion methods not implemented yet (RED phase)")

    # Whale signal: DISTRIBUTION (+200 BTC net inflow)
    whale_vote = _calculate_whale_vote(net_flow_btc=200.0, direction="DISTRIBUTION")
    assert whale_vote == -1.0, f"Expected whale_vote=-1.0 (bearish), got {whale_vote}"

    # UTXOracle: Low confidence (0.2) → neutral vote
    utxo_vote = _calculate_utxo_vote(confidence=0.2)
    assert utxo_vote == 0.0, f"Expected utxo_vote=0.0 (low confidence), got {utxo_vote}"

    # Combined signal: 70% whale + 30% utxo
    combined_signal = _fuse_signals(whale_vote, utxo_vote)
    assert abs(combined_signal - (-0.7)) < 0.01, (
        f"Expected combined_signal=-0.7, got {combined_signal}"
    )

    # Action: SELL (signal < -0.5)
    action = _determine_action(combined_signal)
    assert action == "SELL", f"Expected action='SELL', got '{action}'"


# T047: test_signal_fusion_hold_scenario()
def test_signal_fusion_hold_scenario():
    """
    Test signal fusion for HOLD scenario (neutral signals).

    Scenario:
    - Whale signal: NEUTRAL (net_flow between -100 and +100 BTC) → whale_vote = 0.0
    - UTXOracle confidence: 0.5 → utxo_vote = 1.0 (moderate confidence)
    - Combined signal: 0.7 * 0.0 + 0.3 * 1.0 = 0.3
    - Action: HOLD (signal between -0.5 and 0.5)

    Success Criteria:
    - whale_vote = 0.0
    - utxo_vote = 1.0
    - combined_signal = 0.3
    - action = "HOLD"
    """
    try:
        from scripts.daily_analysis import (
            _calculate_whale_vote,
            _calculate_utxo_vote,
            _fuse_signals,
            _determine_action,
        )
    except ImportError:
        pytest.skip("Signal fusion methods not implemented yet (RED phase)")

    # Whale signal: NEUTRAL (+50 BTC net inflow)
    whale_vote = _calculate_whale_vote(net_flow_btc=50.0, direction="NEUTRAL")
    assert whale_vote == 0.0, f"Expected whale_vote=0.0 (neutral), got {whale_vote}"

    # UTXOracle: Moderate confidence (0.5)
    utxo_vote = _calculate_utxo_vote(confidence=0.5)
    assert utxo_vote == 1.0, (
        f"Expected utxo_vote=1.0 (moderate confidence), got {utxo_vote}"
    )

    # Combined signal: 70% whale + 30% utxo
    combined_signal = _fuse_signals(whale_vote, utxo_vote)
    assert abs(combined_signal - 0.3) < 0.01, (
        f"Expected combined_signal=0.3, got {combined_signal}"
    )

    # Action: HOLD (signal between -0.5 and 0.5)
    action = _determine_action(combined_signal)
    assert action == "HOLD", f"Expected action='HOLD', got '{action}'"


# T048: test_signal_fusion_conflict_scenario()
def test_signal_fusion_conflict_scenario():
    """
    Test signal fusion when whale and UTXOracle conflict.

    Scenario:
    - Whale signal: ACCUMULATION (bullish, -150 BTC) → whale_vote = 1.0
    - UTXOracle confidence: LOW (0.2) → utxo_vote = 0.0 (don't trust price)
    - Combined signal: 0.7 * 1.0 + 0.3 * 0.0 = 0.7
    - Action: BUY (whale signal dominates with 70% weight)

    Alternative conflict:
    - Whale DISTRIBUTION (bearish, +150 BTC) → whale_vote = -1.0
    - UTXOracle high confidence (0.8) → utxo_vote = 1.0
    - Combined: 0.7 * (-1.0) + 0.3 * 1.0 = -0.4
    - Action: HOLD (conflicting signals cancel out)

    Success Criteria:
    - Test both conflict scenarios
    - Whale signal weight (70%) should dominate in strong divergence
    """
    try:
        from scripts.daily_analysis import (
            _calculate_whale_vote,
            _calculate_utxo_vote,
            _fuse_signals,
            _determine_action,
        )
    except ImportError:
        pytest.skip("Signal fusion methods not implemented yet (RED phase)")

    # Conflict 1: Whale bullish, UTXOracle uncertain
    whale_vote_1 = _calculate_whale_vote(net_flow_btc=-150.0, direction="ACCUMULATION")
    utxo_vote_1 = _calculate_utxo_vote(confidence=0.2)
    combined_1 = _fuse_signals(whale_vote_1, utxo_vote_1)
    action_1 = _determine_action(combined_1)

    assert whale_vote_1 == 1.0, f"Expected whale_vote=1.0, got {whale_vote_1}"
    assert utxo_vote_1 == 0.0, f"Expected utxo_vote=0.0, got {utxo_vote_1}"
    assert abs(combined_1 - 0.7) < 0.01, (
        f"Expected combined_signal=0.7, got {combined_1}"
    )
    assert action_1 == "BUY", f"Expected action='BUY', got '{action_1}'"

    # Conflict 2: Whale bearish, UTXOracle confident
    whale_vote_2 = _calculate_whale_vote(net_flow_btc=150.0, direction="DISTRIBUTION")
    utxo_vote_2 = _calculate_utxo_vote(confidence=0.8)
    combined_2 = _fuse_signals(whale_vote_2, utxo_vote_2)
    action_2 = _determine_action(combined_2)

    assert whale_vote_2 == -1.0, f"Expected whale_vote=-1.0, got {whale_vote_2}"
    assert utxo_vote_2 == 1.0, f"Expected utxo_vote=1.0, got {utxo_vote_2}"
    assert abs(combined_2 - (-0.4)) < 0.01, (
        f"Expected combined_signal=-0.4, got {combined_2}"
    )
    assert action_2 == "HOLD", f"Expected action='HOLD', got '{action_2}'"


# =============================================================================
# Phase 5: User Story 3 - Backtest Tests (T063-T064)
# =============================================================================


def test_backtest_correlation_calculation():
    """
    T063: Test correlation calculation between whale net flow and price changes.

    Validates:
    - Pearson correlation coefficient calculation
    - Positive correlation (whale accumulation → price rise)
    - Negative correlation (whale distribution → price drop)
    - Zero correlation (random signals)
    - Edge cases (empty data, single point, identical values)

    Success Criteria:
    - Known positive correlation returns ~0.8 to 1.0
    - Known negative correlation returns ~-0.8 to -1.0
    - Random data returns ~0.0 (±0.3)
    - Edge cases handled gracefully (no crashes)
    """
    try:
        from scripts.whale_flow_backtest import calculate_correlation
    except ImportError:
        pytest.skip("Backtest module not implemented yet (RED phase)")

    # Test Case 1: Perfect positive correlation
    # Whale accumulation (-net_flow) → price rises
    signals_pos = [
        WhaleFlowSignal(
            net_flow_btc=50.0
            - (150.0 * (i + 1)),  # inflow - outflow (correct calculation)
            direction="ACCUMULATION",
            confidence=0.8,
            inflow_btc=50.0,
            outflow_btc=150.0 * (i + 1),
            internal_btc=0.0,
            tx_count_total=100,
            tx_count_relevant=20,
            block_height=920000 + i,
            timestamp=1730000000 + i * 600,
        )
        for i in range(10)
    ]
    price_changes_pos = [1.0 * (i + 1) for i in range(10)]  # Increasing price changes

    corr_pos = calculate_correlation(signals_pos, price_changes_pos)
    assert -1.0 <= corr_pos <= -0.8, (
        f"Expected strong negative correlation (-1.0 to -0.8), got {corr_pos} "
        f"(negative net_flow vs positive price change)"
    )

    # Test Case 2: Perfect negative correlation
    # Whale distribution (+net_flow) → price drops
    signals_neg = [
        WhaleFlowSignal(
            net_flow_btc=(150.0 * (i + 1))
            - 50.0,  # inflow - outflow (correct calculation)
            direction="DISTRIBUTION",
            confidence=0.8,
            inflow_btc=150.0 * (i + 1),
            outflow_btc=50.0,
            internal_btc=0.0,
            tx_count_total=100,
            tx_count_relevant=20,
            block_height=920000 + i,
            timestamp=1730000000 + i * 600,
        )
        for i in range(10)
    ]
    price_changes_neg = [-1.0 * (i + 1) for i in range(10)]  # Decreasing price changes

    corr_neg = calculate_correlation(signals_neg, price_changes_neg)
    assert -1.0 <= corr_neg <= -0.8, (
        f"Expected strong negative correlation (-1.0 to -0.8), got {corr_neg} "
        f"(positive net_flow vs negative price change)"
    )

    # Test Case 3: Zero correlation (uncorrelated data)
    # Using a pattern that doesn't correlate with net_flow
    signals_rand = [
        WhaleFlowSignal(
            net_flow_btc=100.0
            - (
                100.0 + (-1) ** i * 50.0
            ),  # inflow - outflow (alternating: -50, 50, -50, 50, ...)
            direction="NEUTRAL",
            confidence=0.5,
            inflow_btc=100.0,
            outflow_btc=100.0 + (-1) ** i * 50.0,
            internal_btc=0.0,
            tx_count_total=100,
            tx_count_relevant=20,
            block_height=920000 + i,
            timestamp=1730000000 + i * 600,
        )
        for i in range(10)
    ]
    # Pattern that doesn't correlate with net_flow (-50, 50, -50, 50...):
    # Use: 1, -1, -1, 1, 1, -1, -1, 1, 1, -1 (every 2 values same sign)
    price_changes_rand = [1.0 if (i // 2) % 2 == 0 else -1.0 for i in range(10)]

    corr_rand = calculate_correlation(signals_rand, price_changes_rand)
    assert -0.4 <= corr_rand <= 0.4, (
        f"Expected weak/zero correlation (-0.4 to 0.4), got {corr_rand}"
    )

    # Test Case 4: Edge case - insufficient data
    signals_short = [signals_pos[0]]
    price_changes_short = [price_changes_pos[0]]

    corr_short = calculate_correlation(signals_short, price_changes_short)
    assert corr_short == 0.0, f"Expected 0.0 for single data point, got {corr_short}"

    # Test Case 5: Edge case - mismatched lengths
    with pytest.raises(ValueError, match="Signal count .* != price change count"):
        calculate_correlation(signals_pos, price_changes_pos[:5])

    print("✅ T063: Correlation calculation tests passed")


def test_backtest_false_positive_rate():
    """
    T064: Test false positive rate calculation for whale signals.

    Definition:
    - False positive = Signal predicts wrong direction
    - ACCUMULATION but price drops (bearish outcome)
    - DISTRIBUTION but price rises (bullish outcome)
    - NEUTRAL signals are excluded

    Success Criteria:
    - 0% false positive rate when all predictions correct
    - 100% false positive rate when all predictions wrong
    - 50% false positive rate for random predictions
    - NEUTRAL signals excluded from calculation
    - Edge cases handled (no signals, all neutral)
    """
    try:
        from scripts.whale_flow_backtest import calculate_false_positive_rate
    except ImportError:
        pytest.skip("Backtest module not implemented yet (RED phase)")

    # Test Case 1: Perfect predictions (0% false positive)
    signals_perfect = [
        WhaleFlowSignal(
            net_flow_btc=-100.0,  # Outflow (bullish)
            direction="ACCUMULATION",
            confidence=0.8,
            inflow_btc=50.0,
            outflow_btc=150.0,
            internal_btc=0.0,
            tx_count_total=100,
            tx_count_relevant=20,
            block_height=920000,
            timestamp=1730000000,
        ),
        WhaleFlowSignal(
            net_flow_btc=100.0,  # Inflow (bearish)
            direction="DISTRIBUTION",
            confidence=0.8,
            inflow_btc=150.0,
            outflow_btc=50.0,
            internal_btc=0.0,
            tx_count_total=100,
            tx_count_relevant=20,
            block_height=920001,
            timestamp=1730000600,
        ),
    ]
    price_changes_perfect = [2.0, -2.0]  # ACCUMULATION → up, DISTRIBUTION → down

    fpr_perfect = calculate_false_positive_rate(signals_perfect, price_changes_perfect)
    assert fpr_perfect == 0.0, f"Expected 0% false positive, got {fpr_perfect * 100}%"

    # Test Case 2: All wrong predictions (100% false positive)
    signals_wrong = [
        WhaleFlowSignal(
            net_flow_btc=-100.0,
            direction="ACCUMULATION",
            confidence=0.8,
            inflow_btc=50.0,
            outflow_btc=150.0,
            internal_btc=0.0,
            tx_count_total=100,
            tx_count_relevant=20,
            block_height=920000,
            timestamp=1730000000,
        ),
        WhaleFlowSignal(
            net_flow_btc=100.0,
            direction="DISTRIBUTION",
            confidence=0.8,
            inflow_btc=150.0,
            outflow_btc=50.0,
            internal_btc=0.0,
            tx_count_total=100,
            tx_count_relevant=20,
            block_height=920001,
            timestamp=1730000600,
        ),
    ]
    price_changes_wrong = [-2.0, 2.0]  # ACCUMULATION → down, DISTRIBUTION → up (wrong)

    fpr_wrong = calculate_false_positive_rate(signals_wrong, price_changes_wrong)
    assert fpr_wrong == 1.0, f"Expected 100% false positive, got {fpr_wrong * 100}%"

    # Test Case 3: Mixed predictions (50% false positive)
    signals_mixed = [
        WhaleFlowSignal(
            net_flow_btc=-100.0,
            direction="ACCUMULATION",
            confidence=0.8,
            inflow_btc=50.0,
            outflow_btc=150.0,
            internal_btc=0.0,
            tx_count_total=100,
            tx_count_relevant=20,
            block_height=920000 + i,
            timestamp=1730000000 + i * 600,
        )
        for i in range(4)
    ]
    price_changes_mixed = [2.0, -2.0, 2.0, -2.0]  # 50% correct, 50% wrong

    fpr_mixed = calculate_false_positive_rate(signals_mixed, price_changes_mixed)
    assert fpr_mixed == 0.5, f"Expected 50% false positive, got {fpr_mixed * 100}%"

    # Test Case 4: NEUTRAL signals excluded
    signals_with_neutral = [
        WhaleFlowSignal(
            net_flow_btc=-100.0,
            direction="ACCUMULATION",
            confidence=0.8,
            inflow_btc=50.0,
            outflow_btc=150.0,
            internal_btc=0.0,
            tx_count_total=100,
            tx_count_relevant=20,
            block_height=920000,
            timestamp=1730000000,
        ),
        WhaleFlowSignal(
            net_flow_btc=0.0,
            direction="NEUTRAL",
            confidence=0.5,
            inflow_btc=100.0,
            outflow_btc=100.0,
            internal_btc=0.0,
            tx_count_total=100,
            tx_count_relevant=20,
            block_height=920001,
            timestamp=1730000600,
        ),
    ]
    price_changes_with_neutral = [2.0, -2.0]  # NEUTRAL → down (should be ignored)

    fpr_neutral = calculate_false_positive_rate(
        signals_with_neutral, price_changes_with_neutral
    )
    assert fpr_neutral == 0.0, (
        f"Expected 0% (NEUTRAL ignored), got {fpr_neutral * 100}%"
    )

    # Test Case 5: Edge case - all NEUTRAL signals
    signals_all_neutral = [
        WhaleFlowSignal(
            net_flow_btc=0.0,
            direction="NEUTRAL",
            confidence=0.5,
            inflow_btc=100.0,
            outflow_btc=100.0,
            internal_btc=0.0,
            tx_count_total=100,
            tx_count_relevant=20,
            block_height=920000 + i,
            timestamp=1730000000 + i * 600,
        )
        for i in range(3)
    ]
    price_changes_all_neutral = [1.0, -1.0, 2.0]

    fpr_all_neutral = calculate_false_positive_rate(
        signals_all_neutral, price_changes_all_neutral
    )
    assert fpr_all_neutral == 0.0, (
        f"Expected 0.0 (no actionable signals), got {fpr_all_neutral}"
    )

    # Test Case 6: Edge case - mismatched lengths
    with pytest.raises(ValueError, match="Signal count .* != price change count"):
        calculate_false_positive_rate(signals_perfect, price_changes_perfect[:1])

    print("✅ T064: False positive rate tests passed")
