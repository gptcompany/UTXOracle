"""Tests for URPD (UTXO Realized Price Distribution) module.

spec-021: Advanced On-Chain Metrics
TDD: Tests written BEFORE implementation.
"""

import duckdb
import pytest

from scripts.models.metrics_models import URPDBucket, URPDResult


@pytest.fixture
def test_db():
    """Create an in-memory DuckDB with test UTXO data."""
    conn = duckdb.connect(":memory:")

    # Create the utxo_lifecycle table schema
    conn.execute(
        """
        CREATE TABLE utxo_lifecycle (
            outpoint VARCHAR PRIMARY KEY,
            txid VARCHAR NOT NULL,
            vout_index INTEGER NOT NULL,
            creation_block INTEGER NOT NULL,
            creation_timestamp TIMESTAMP NOT NULL,
            creation_price_usd DOUBLE NOT NULL,
            btc_value DOUBLE NOT NULL,
            realized_value_usd DOUBLE NOT NULL,
            spent_block INTEGER,
            spent_timestamp TIMESTAMP,
            spent_price_usd DOUBLE,
            spending_txid VARCHAR,
            age_blocks INTEGER,
            age_days INTEGER,
            cohort VARCHAR,
            sub_cohort VARCHAR,
            sopr DOUBLE,
            is_coinbase BOOLEAN DEFAULT FALSE,
            is_spent BOOLEAN DEFAULT FALSE,
            price_source VARCHAR DEFAULT 'utxoracle'
        )
        """
    )

    # Create VIEW alias for production code compatibility
    conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")

    # Insert test data spanning multiple price buckets
    # 5 UTXOs at different acquisition prices
    test_utxos = [
        # Low price bucket ($10,000-$15,000) - 3 BTC total
        ("tx1:0", "tx1", 0, 700000, "2024-01-01", 12000.0, 1.5, 18000.0, False),
        ("tx2:0", "tx2", 0, 700100, "2024-01-02", 14000.0, 1.5, 21000.0, False),
        # Mid price bucket ($50,000-$55,000) - 2 BTC total
        ("tx3:0", "tx3", 0, 800000, "2024-06-01", 52000.0, 1.0, 52000.0, False),
        ("tx4:0", "tx4", 0, 800100, "2024-06-02", 53000.0, 1.0, 53000.0, False),
        # High price bucket ($95,000-$100,000) - 1.5 BTC total
        ("tx5:0", "tx5", 0, 870000, "2024-12-01", 97000.0, 0.75, 72750.0, False),
        ("tx6:0", "tx6", 0, 870100, "2024-12-02", 99000.0, 0.75, 74250.0, False),
        # Spent UTXO (should be excluded)
        ("tx7:0", "tx7", 0, 750000, "2024-04-01", 65000.0, 0.5, 32500.0, True),
    ]

    for row in test_utxos:
        conn.execute(
            """
            INSERT INTO utxo_lifecycle (
                outpoint, txid, vout_index, creation_block,
                creation_timestamp, creation_price_usd, btc_value,
                realized_value_usd, is_spent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )

    yield conn
    conn.close()


class TestURPDCalculation:
    """Tests for calculate_urpd() function."""

    def test_calculate_urpd_basic(self, test_db):
        """T011: Basic URPD calculation returns valid result."""
        from scripts.metrics.urpd import calculate_urpd

        result = calculate_urpd(
            conn=test_db,
            current_price_usd=100000.0,
            bucket_size_usd=5000.0,
            block_height=875000,
        )

        # Verify result type
        assert isinstance(result, URPDResult)

        # Verify total supply (excludes spent UTXO: 1.5+1.5+1.0+1.0+0.75+0.75 = 6.5 BTC)
        assert result.total_supply_btc == pytest.approx(6.5, rel=0.01)

        # Verify bucket size preserved
        assert result.bucket_size_usd == 5000.0

        # Verify current price preserved
        assert result.current_price_usd == 100000.0

        # Verify block height
        assert result.block_height == 875000

        # Verify we have some buckets
        assert len(result.buckets) > 0

    def test_urpd_bucket_aggregation(self, test_db):
        """T012: GROUP BY aggregates BTC correctly per bucket."""
        from scripts.metrics.urpd import calculate_urpd

        result = calculate_urpd(
            conn=test_db,
            current_price_usd=100000.0,
            bucket_size_usd=5000.0,
            block_height=875000,
        )

        # Find the $10,000-$15,000 bucket (price_low=10000)
        low_bucket = next(
            (b for b in result.buckets if b.price_low == 10000.0),
            None,
        )
        assert low_bucket is not None
        # Should have 3 BTC (1.5 + 1.5 from two UTXOs at $12k and $14k)
        assert low_bucket.btc_amount == pytest.approx(3.0, rel=0.01)
        assert low_bucket.utxo_count == 2

        # Find the $50,000-$55,000 bucket (price_low=50000)
        mid_bucket = next(
            (b for b in result.buckets if b.price_low == 50000.0),
            None,
        )
        assert mid_bucket is not None
        # Should have 2 BTC (1.0 + 1.0)
        assert mid_bucket.btc_amount == pytest.approx(2.0, rel=0.01)
        assert mid_bucket.utxo_count == 2

        # Find the $95,000-$100,000 bucket (price_low=95000)
        high_bucket = next(
            (b for b in result.buckets if b.price_low == 95000.0),
            None,
        )
        assert high_bucket is not None
        # Should have 1.5 BTC (0.75 + 0.75)
        assert high_bucket.btc_amount == pytest.approx(1.5, rel=0.01)
        assert high_bucket.utxo_count == 2

    def test_urpd_profit_loss_split(self, test_db):
        """T013: Correctly calculates supply above/below current price."""
        from scripts.metrics.urpd import calculate_urpd

        # Test with current price = $60,000
        # Supply in profit (cost basis < $60k): 3 BTC (low bucket) + 2 BTC (mid bucket) = 5 BTC
        # Supply in loss (cost basis > $60k): 1.5 BTC (high bucket at $95k-$100k)
        result = calculate_urpd(
            conn=test_db,
            current_price_usd=60000.0,
            bucket_size_usd=5000.0,
            block_height=875000,
        )

        # Supply below price = in profit
        assert result.supply_below_price_btc == pytest.approx(5.0, rel=0.01)
        # Supply above price = in loss
        assert result.supply_above_price_btc == pytest.approx(1.5, rel=0.01)

        # Percentages should match
        total = result.total_supply_btc
        expected_below_pct = (5.0 / total) * 100
        expected_above_pct = (1.5 / total) * 100

        assert result.supply_below_price_pct == pytest.approx(
            expected_below_pct, rel=0.1
        )
        assert result.supply_above_price_pct == pytest.approx(
            expected_above_pct, rel=0.1
        )

    def test_urpd_dominant_bucket(self, test_db):
        """T014: Correctly identifies bucket with highest BTC amount."""
        from scripts.metrics.urpd import calculate_urpd

        result = calculate_urpd(
            conn=test_db,
            current_price_usd=100000.0,
            bucket_size_usd=5000.0,
            block_height=875000,
        )

        # Dominant bucket should be the low price bucket (3 BTC)
        assert result.dominant_bucket is not None
        assert result.dominant_bucket.btc_amount == pytest.approx(3.0, rel=0.01)
        assert result.dominant_bucket.price_low == 10000.0

    def test_urpd_empty_result(self):
        """T015: Handles empty UTXO set gracefully."""
        from scripts.metrics.urpd import calculate_urpd

        # Create empty database
        conn = duckdb.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE utxo_lifecycle (
                outpoint VARCHAR PRIMARY KEY,
                txid VARCHAR NOT NULL,
                vout_index INTEGER NOT NULL,
                creation_block INTEGER NOT NULL,
                creation_timestamp TIMESTAMP NOT NULL,
                creation_price_usd DOUBLE NOT NULL,
                btc_value DOUBLE NOT NULL,
                realized_value_usd DOUBLE NOT NULL,
                is_spent BOOLEAN DEFAULT FALSE
            )
            """
        )
        conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")

        result = calculate_urpd(
            conn=conn,
            current_price_usd=100000.0,
            bucket_size_usd=5000.0,
            block_height=875000,
        )

        conn.close()

        # Should return valid result with empty buckets
        assert isinstance(result, URPDResult)
        assert result.total_supply_btc == 0.0
        assert len(result.buckets) == 0
        assert result.dominant_bucket is None
        assert result.supply_above_price_btc == 0.0
        assert result.supply_below_price_btc == 0.0


class TestURPDBucket:
    """Tests for URPDBucket dataclass validation."""

    def test_valid_bucket(self):
        """Valid bucket creation succeeds."""
        bucket = URPDBucket(
            price_low=10000.0,
            price_high=15000.0,
            btc_amount=1.5,
            utxo_count=3,
            percentage=15.0,
        )
        assert bucket.price_low == 10000.0
        assert bucket.price_high == 15000.0
        assert bucket.btc_amount == 1.5

    def test_negative_price_low_fails(self):
        """Negative price_low raises ValueError."""
        with pytest.raises(ValueError, match="price_low must be >= 0"):
            URPDBucket(
                price_low=-100.0,
                price_high=15000.0,
                btc_amount=1.5,
                utxo_count=3,
                percentage=15.0,
            )

    def test_price_high_less_than_low_fails(self):
        """price_high < price_low raises ValueError."""
        with pytest.raises(ValueError, match="price_high must be >= price_low"):
            URPDBucket(
                price_low=20000.0,
                price_high=15000.0,
                btc_amount=1.5,
                utxo_count=3,
                percentage=15.0,
            )

    def test_negative_btc_amount_fails(self):
        """Negative btc_amount raises ValueError."""
        with pytest.raises(ValueError, match="btc_amount must be >= 0"):
            URPDBucket(
                price_low=10000.0,
                price_high=15000.0,
                btc_amount=-1.0,
                utxo_count=3,
                percentage=15.0,
            )

    def test_percentage_out_of_range_fails(self):
        """percentage > 100 raises ValueError."""
        with pytest.raises(ValueError, match="percentage must be in"):
            URPDBucket(
                price_low=10000.0,
                price_high=15000.0,
                btc_amount=1.5,
                utxo_count=3,
                percentage=150.0,
            )


class TestURPDResult:
    """Tests for URPDResult dataclass validation."""

    def test_valid_result(self):
        """Valid result creation succeeds."""
        result = URPDResult(
            buckets=[],
            bucket_size_usd=5000.0,
            total_supply_btc=100.0,
            current_price_usd=100000.0,
            supply_above_price_btc=20.0,
            supply_below_price_btc=80.0,
            supply_above_price_pct=20.0,
            supply_below_price_pct=80.0,
            dominant_bucket=None,
            block_height=875000,
        )
        assert result.total_supply_btc == 100.0

    def test_invalid_bucket_size_fails(self):
        """bucket_size_usd <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="bucket_size_usd must be > 0"):
            URPDResult(
                buckets=[],
                bucket_size_usd=0.0,
                total_supply_btc=100.0,
                current_price_usd=100000.0,
                supply_above_price_btc=20.0,
                supply_below_price_btc=80.0,
                supply_above_price_pct=20.0,
                supply_below_price_pct=80.0,
                dominant_bucket=None,
                block_height=875000,
            )

    def test_invalid_current_price_fails(self):
        """current_price_usd <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="current_price_usd must be > 0"):
            URPDResult(
                buckets=[],
                bucket_size_usd=5000.0,
                total_supply_btc=100.0,
                current_price_usd=0.0,
                supply_above_price_btc=20.0,
                supply_below_price_btc=80.0,
                supply_above_price_pct=20.0,
                supply_below_price_pct=80.0,
                dominant_bucket=None,
                block_height=875000,
            )

    def test_to_dict(self):
        """to_dict() returns correct structure."""
        bucket = URPDBucket(
            price_low=10000.0,
            price_high=15000.0,
            btc_amount=3.0,
            utxo_count=5,
            percentage=30.0,
        )
        result = URPDResult(
            buckets=[bucket],
            bucket_size_usd=5000.0,
            total_supply_btc=10.0,
            current_price_usd=100000.0,
            supply_above_price_btc=0.0,
            supply_below_price_btc=10.0,
            supply_above_price_pct=0.0,
            supply_below_price_pct=100.0,
            dominant_bucket=bucket,
            block_height=875000,
        )

        d = result.to_dict()
        assert d["bucket_size_usd"] == 5000.0
        assert d["total_supply_btc"] == 10.0
        assert d["block_height"] == 875000
        assert len(d["buckets"]) == 1
        assert d["dominant_bucket"]["btc_amount"] == 3.0
