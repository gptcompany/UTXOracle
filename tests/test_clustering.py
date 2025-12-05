"""Tests for Address Clustering and CoinJoin Detection Module.

Test coverage for:
- Union-Find data structure
- Multi-input clustering heuristic
- CoinJoin detection patterns
- Change output detection
- Integration with whale tracking
"""


# =============================================================================
# Phase 2: Union-Find Tests
# =============================================================================


class TestUnionFindBasic:
    """T004: Basic Union-Find operations."""

    def test_find_returns_same_root_after_union(self):
        """Elements in same set should have same root."""
        from scripts.clustering.union_find import UnionFind

        uf = UnionFind()
        uf.union("a", "b")

        assert uf.find("a") == uf.find("b")

    def test_find_returns_different_roots_without_union(self):
        """Elements not unioned should have different roots."""
        from scripts.clustering.union_find import UnionFind

        uf = UnionFind()
        uf.find("a")  # Initialize
        uf.find("b")  # Initialize

        assert uf.find("a") != uf.find("b")

    def test_connected_returns_true_after_union(self):
        """connected() should return True for unioned elements."""
        from scripts.clustering.union_find import UnionFind

        uf = UnionFind()
        uf.union("addr1", "addr2")

        assert uf.connected("addr1", "addr2") is True

    def test_connected_returns_false_without_union(self):
        """connected() should return False for non-unioned elements."""
        from scripts.clustering.union_find import UnionFind

        uf = UnionFind()

        assert uf.connected("addr1", "addr2") is False

    def test_get_clusters_returns_correct_groups(self):
        """get_clusters() should return all disjoint sets."""
        from scripts.clustering.union_find import UnionFind

        uf = UnionFind()
        uf.union("a", "b")
        uf.union("c", "d")

        clusters = uf.get_clusters()

        assert len(clusters) == 2
        assert {"a", "b"} in clusters
        assert {"c", "d"} in clusters


class TestUnionFindTransitivity:
    """T005: Union-Find transitivity property."""

    def test_transitivity_through_chain(self):
        """a-b, b-c implies a connected to c."""
        from scripts.clustering.union_find import UnionFind

        uf = UnionFind()
        uf.union("a", "b")
        uf.union("b", "c")

        assert uf.connected("a", "c") is True

    def test_transitivity_through_long_chain(self):
        """a-b, b-c, c-d, d-e implies a connected to e."""
        from scripts.clustering.union_find import UnionFind

        uf = UnionFind()
        uf.union("a", "b")
        uf.union("b", "c")
        uf.union("c", "d")
        uf.union("d", "e")

        assert uf.connected("a", "e") is True
        assert uf.find("a") == uf.find("e")

    def test_merging_two_clusters(self):
        """Merging two existing clusters should connect all elements."""
        from scripts.clustering.union_find import UnionFind

        uf = UnionFind()
        # Create cluster 1: a-b-c
        uf.union("a", "b")
        uf.union("b", "c")
        # Create cluster 2: x-y-z
        uf.union("x", "y")
        uf.union("y", "z")

        # Verify separate
        assert uf.connected("a", "x") is False

        # Merge clusters
        uf.union("c", "x")

        # All should be connected
        assert uf.connected("a", "z") is True
        assert len(uf.get_clusters()) == 1


# =============================================================================
# Phase 3: Address Clustering Tests (US1)
# =============================================================================


class TestClusterSingleTx:
    """T008: Cluster addresses from single transaction."""

    def test_cluster_addresses_from_single_tx(self):
        """All input addresses in same tx should be clustered."""
        from scripts.clustering.address_clustering import cluster_addresses
        from scripts.clustering.union_find import UnionFind

        uf = UnionFind()
        tx_inputs = ["addr1", "addr2", "addr3"]

        cluster_addresses(uf, tx_inputs)

        assert uf.connected("addr1", "addr2")
        assert uf.connected("addr2", "addr3")
        assert uf.connected("addr1", "addr3")

    def test_cluster_single_address_tx(self):
        """Single-input tx should create singleton cluster."""
        from scripts.clustering.address_clustering import cluster_addresses
        from scripts.clustering.union_find import UnionFind

        uf = UnionFind()
        tx_inputs = ["single_addr"]

        cluster_addresses(uf, tx_inputs)

        clusters = uf.get_clusters()
        assert len(clusters) == 1
        assert "single_addr" in clusters[0]


class TestClusterMultipleTx:
    """T009: Cluster addresses from multiple transactions."""

    def test_cluster_addresses_from_multiple_txs(self):
        """Multiple txs with overlapping addresses should merge clusters."""
        from scripts.clustering.address_clustering import cluster_addresses
        from scripts.clustering.union_find import UnionFind

        uf = UnionFind()

        # TX1: addr1, addr2
        cluster_addresses(uf, ["addr1", "addr2"])
        # TX2: addr3, addr4
        cluster_addresses(uf, ["addr3", "addr4"])
        # TX3: addr2, addr3 (bridges the two clusters)
        cluster_addresses(uf, ["addr2", "addr3"])

        # All should be connected
        assert uf.connected("addr1", "addr4")
        assert len(uf.get_clusters()) == 1

    def test_independent_clusters_stay_separate(self):
        """Txs with no overlap should create separate clusters."""
        from scripts.clustering.address_clustering import cluster_addresses
        from scripts.clustering.union_find import UnionFind

        uf = UnionFind()

        cluster_addresses(uf, ["a1", "a2"])
        cluster_addresses(uf, ["b1", "b2"])

        assert not uf.connected("a1", "b1")
        assert len(uf.get_clusters()) == 2


class TestClusterTransitivity:
    """T010: Verify transitivity in clustering."""

    def test_transitivity_through_shared_addresses(self):
        """Clustering should be transitive through shared addresses."""
        from scripts.clustering.address_clustering import cluster_addresses
        from scripts.clustering.union_find import UnionFind

        uf = UnionFind()

        # Chain: A shares with B, B shares with C, C shares with D
        cluster_addresses(uf, ["a1", "shared_ab"])
        cluster_addresses(uf, ["shared_ab", "b1", "shared_bc"])
        cluster_addresses(uf, ["shared_bc", "c1", "shared_cd"])
        cluster_addresses(uf, ["shared_cd", "d1"])

        # a1 should be connected to d1 through chain
        assert uf.connected("a1", "d1")

    def test_get_cluster_stats(self):
        """get_cluster_stats should return correct statistics."""
        from scripts.clustering.address_clustering import (
            cluster_addresses,
            get_cluster_stats,
        )
        from scripts.clustering.union_find import UnionFind

        uf = UnionFind()

        # Create varying cluster sizes
        cluster_addresses(uf, ["a1", "a2", "a3"])  # 3 addresses
        cluster_addresses(uf, ["b1", "b2"])  # 2 addresses
        cluster_addresses(uf, ["c1"])  # 1 address

        stats = get_cluster_stats(uf)

        assert stats["cluster_count"] == 3
        assert stats["total_addresses"] == 6
        assert stats["max_cluster_size"] == 3
        assert stats["avg_cluster_size"] == 2.0


# =============================================================================
# Phase 4: CoinJoin Detection Tests (US2)
# =============================================================================


class TestDetectGenericCoinJoin:
    """T015: Detect generic CoinJoin patterns."""

    def test_detect_generic_coinjoin_equal_outputs(self):
        """Transaction with many equal outputs should be flagged as CoinJoin."""
        from scripts.clustering.coinjoin_detector import detect_coinjoin

        # 8 inputs, 8 equal outputs of 0.1 BTC
        tx = {
            "txid": "abc123",
            "vin": [{"txid": f"in{i}", "vout": 0} for i in range(8)],
            "vout": [
                {"value": 0.1, "scriptPubKey": {"address": f"out{i}"}} for i in range(8)
            ],
        }

        result = detect_coinjoin(tx)

        assert result.is_coinjoin is True
        assert result.confidence >= 0.7
        assert result.equal_output_count >= 8

    def test_detect_coinjoin_minimum_threshold(self):
        """Need at least 5 equal outputs for generic CoinJoin."""
        from scripts.clustering.coinjoin_detector import detect_coinjoin

        # Only 3 equal outputs - should NOT be CoinJoin
        tx = {
            "txid": "abc123",
            "vin": [{"txid": f"in{i}", "vout": 0} for i in range(3)],
            "vout": [
                {"value": 0.1, "scriptPubKey": {"address": f"out{i}"}} for i in range(3)
            ],
        }

        result = detect_coinjoin(tx)

        assert result.is_coinjoin is False


class TestDetectWasabi:
    """T016: Detect Wasabi CoinJoin patterns."""

    def test_detect_wasabi_coinjoin(self):
        """Wasabi CoinJoin with 100+ outputs should be detected."""
        from scripts.clustering.coinjoin_detector import detect_coinjoin

        # Wasabi typically has 100+ equal outputs
        tx = {
            "txid": "wasabi123",
            "vin": [{"txid": f"in{i}", "vout": 0} for i in range(100)],
            "vout": [
                {"value": 0.1, "scriptPubKey": {"address": f"out{i}"}}
                for i in range(100)
            ],
        }

        result = detect_coinjoin(tx)

        assert result.is_coinjoin is True
        assert result.confidence >= 0.9
        assert result.coinjoin_type == "wasabi"


class TestDetectWhirlpool:
    """T017: Detect Whirlpool CoinJoin patterns."""

    def test_detect_whirlpool_fixed_denomination(self):
        """Whirlpool uses fixed denominations (0.001, 0.01, 0.05, 0.5 BTC)."""
        from scripts.clustering.coinjoin_detector import detect_coinjoin

        # Whirlpool 0.01 BTC pool with 5 participants
        tx = {
            "txid": "whirlpool123",
            "vin": [{"txid": f"in{i}", "vout": 0} for i in range(5)],
            "vout": [
                {"value": 0.01, "scriptPubKey": {"address": f"out{i}"}}
                for i in range(5)
            ],
        }

        result = detect_coinjoin(tx)

        assert result.is_coinjoin is True
        assert result.coinjoin_type == "whirlpool"
        assert 0.01 in [0.001, 0.01, 0.05, 0.5]  # Fixed denomination

    def test_detect_whirlpool_satoshi_values(self):
        """Whirlpool detection with satoshi values (electrs API format)."""
        from scripts.clustering.coinjoin_detector import detect_coinjoin

        # Whirlpool 0.01 BTC = 1,000,000 satoshis
        tx = {
            "txid": "whirlpool_sats",
            "vin": [{"txid": f"in{i}", "vout": 0} for i in range(5)],
            "vout": [
                {"value": 1000000, "scriptPubKey": {"address": f"out{i}"}}
                for i in range(5)
            ],
        }

        result = detect_coinjoin(tx)

        assert result.is_coinjoin is True
        assert result.coinjoin_type == "whirlpool"

    def test_detect_whirlpool_all_denominations_satoshis(self):
        """All Whirlpool denominations work in satoshis."""
        from scripts.clustering.coinjoin_detector import detect_coinjoin

        # 0.001, 0.01, 0.05, 0.5 BTC in satoshis
        for sats in [100_000, 1_000_000, 5_000_000, 50_000_000]:
            tx = {
                "txid": f"whirlpool_{sats}",
                "vin": [{"txid": f"in{i}", "vout": 0} for i in range(5)],
                "vout": [
                    {"value": sats, "scriptPubKey": {"address": f"out{i}"}}
                    for i in range(5)
                ],
            }
            result = detect_coinjoin(tx)
            assert result.coinjoin_type == "whirlpool", f"Failed for {sats} sats"


class TestNormalTxNotCoinJoin:
    """T018: Normal transactions should NOT be flagged as CoinJoin."""

    def test_normal_payment_not_coinjoin(self):
        """Standard payment transaction with different outputs."""
        from scripts.clustering.coinjoin_detector import detect_coinjoin

        # Normal payment: 2 inputs, 2 outputs (payment + change)
        tx = {
            "txid": "normal123",
            "vin": [{"txid": "in1", "vout": 0}, {"txid": "in2", "vout": 1}],
            "vout": [
                {"value": 1.5, "scriptPubKey": {"address": "payment_addr"}},
                {"value": 0.4999, "scriptPubKey": {"address": "change_addr"}},
            ],
        }

        result = detect_coinjoin(tx)

        assert result.is_coinjoin is False
        assert result.confidence < 0.5

    def test_consolidation_tx_not_coinjoin(self):
        """Consolidation transaction (many inputs, one output)."""
        from scripts.clustering.coinjoin_detector import detect_coinjoin

        # Consolidation: 10 inputs, 1 output
        tx = {
            "txid": "consolidate123",
            "vin": [{"txid": f"in{i}", "vout": 0} for i in range(10)],
            "vout": [{"value": 5.0, "scriptPubKey": {"address": "consolidate_addr"}}],
        }

        result = detect_coinjoin(tx)

        assert result.is_coinjoin is False

    def test_batch_payment_not_coinjoin(self):
        """Batch payment with different amounts is not CoinJoin."""
        from scripts.clustering.coinjoin_detector import detect_coinjoin

        # Batch payment: 1 input, multiple different outputs
        tx = {
            "txid": "batch123",
            "vin": [{"txid": "in1", "vout": 0}],
            "vout": [
                {"value": 0.5, "scriptPubKey": {"address": "pay1"}},
                {"value": 0.3, "scriptPubKey": {"address": "pay2"}},
                {"value": 0.2, "scriptPubKey": {"address": "pay3"}},
                {"value": 0.1, "scriptPubKey": {"address": "pay4"}},
            ],
        }

        result = detect_coinjoin(tx)

        assert result.is_coinjoin is False


# =============================================================================
# Phase 5: Change Detection Tests (US3)
# =============================================================================


class TestDetectOddAmountChange:
    """T024: Detect change outputs by odd amounts."""

    def test_detect_odd_amount_as_change(self):
        """Output with many decimals is likely change."""
        from scripts.clustering.change_detector import detect_change_outputs

        tx = {
            "txid": "change123",
            "vout": [
                {
                    "value": 1.0,
                    "scriptPubKey": {"address": "payment"},
                },  # Round = payment
                {
                    "value": 0.12345678,
                    "scriptPubKey": {"address": "change"},
                },  # Odd = change
            ],
        }

        result = detect_change_outputs(tx)

        assert 1 in result.likely_change_outputs  # Index of change output
        assert 0 in result.likely_payment_outputs  # Index of payment output

    def test_both_round_amounts_no_change_detected(self):
        """Two round amounts - can't determine change confidently."""
        from scripts.clustering.change_detector import detect_change_outputs

        tx = {
            "txid": "round123",
            "vout": [
                {"value": 1.0, "scriptPubKey": {"address": "out1"}},
                {"value": 2.0, "scriptPubKey": {"address": "out2"}},
            ],
        }

        result = detect_change_outputs(tx)

        # Both could be payments, no clear change
        assert len(result.likely_change_outputs) == 0


class TestDetectSmallOutputChange:
    """T025: Detect change outputs by relative size."""

    def test_small_output_as_change(self):
        """Output < 10% of largest is likely change."""
        from scripts.clustering.change_detector import detect_change_outputs

        tx = {
            "txid": "small123",
            "vout": [
                {"value": 10.0, "scriptPubKey": {"address": "large_payment"}},
                {
                    "value": 0.5,
                    "scriptPubKey": {"address": "small_change"},
                },  # 5% of max
            ],
        }

        result = detect_change_outputs(tx)

        assert 1 in result.likely_change_outputs

    def test_similar_amounts_no_size_change(self):
        """Similar sized outputs - can't determine by size."""
        from scripts.clustering.change_detector import detect_change_outputs

        tx = {
            "txid": "similar123",
            "vout": [
                {"value": 1.0, "scriptPubKey": {"address": "out1"}},
                {"value": 0.9, "scriptPubKey": {"address": "out2"}},  # 90% of max
            ],
        }

        result = detect_change_outputs(tx)

        # Neither is clearly change by size alone
        # (may still be detected by other heuristics)
        assert len([i for i in result.likely_change_outputs if i in [0, 1]]) <= 1


# =============================================================================
# Phase 6: Whale Integration Tests (US4)
# =============================================================================


class TestWhaleDetectionWithClustering:
    """T029: Whale detection with address clustering."""

    def test_filter_coinjoins_removes_coinjoin_txs(self):
        """filter_coinjoins should remove CoinJoin transactions."""
        from scripts.clustering import filter_coinjoins

        transactions = [
            # Normal transaction
            {
                "txid": "normal1",
                "vin": [{"txid": "in1", "vout": 0}],
                "vout": [
                    {"value": 1.0, "scriptPubKey": {"address": "out1"}},
                    {"value": 0.5, "scriptPubKey": {"address": "out2"}},
                ],
            },
            # CoinJoin transaction (8 equal outputs)
            {
                "txid": "coinjoin1",
                "vin": [{"txid": f"in{i}", "vout": 0} for i in range(8)],
                "vout": [
                    {"value": 0.1, "scriptPubKey": {"address": f"out{i}"}}
                    for i in range(8)
                ],
            },
        ]

        filtered = filter_coinjoins(transactions)

        assert len(filtered) == 1
        assert filtered[0]["txid"] == "normal1"

    def test_filter_coinjoins_with_threshold(self):
        """filter_coinjoins should respect confidence threshold."""
        from scripts.clustering import filter_coinjoins

        transactions = [
            # Borderline CoinJoin (lower confidence)
            {
                "txid": "borderline1",
                "vin": [{"txid": f"in{i}", "vout": 0} for i in range(5)],
                "vout": [
                    {"value": 0.1, "scriptPubKey": {"address": f"out{i}"}}
                    for i in range(5)
                ],
            },
        ]

        # High threshold - should keep borderline
        filtered_high = filter_coinjoins(transactions, threshold=0.95)
        assert len(filtered_high) == 1

        # Low threshold - should remove
        filtered_low = filter_coinjoins(transactions, threshold=0.5)
        assert len(filtered_low) == 0


class TestWhaleDetectionFiltersCoinJoin:
    """T030: Whale detection filters CoinJoin transactions."""

    def test_cluster_addresses_from_whale_txs(self):
        """Clustering should work with whale-style transactions."""
        from scripts.clustering import filter_coinjoins
        from scripts.clustering.address_clustering import cluster_addresses
        from scripts.clustering.union_find import UnionFind

        # Simulate whale transactions
        transactions = [
            {
                "txid": "whale1",
                "vin": [
                    {
                        "txid": "in1",
                        "vout": 0,
                        "prevout": {"scriptpubkey_address": "whale_addr1"},
                    },
                    {
                        "txid": "in2",
                        "vout": 0,
                        "prevout": {"scriptpubkey_address": "whale_addr2"},
                    },
                ],
                "vout": [{"value": 100.0, "scriptPubKey": {"address": "exchange"}}],
            },
        ]

        # Filter CoinJoins first
        clean_txs = filter_coinjoins(transactions)
        assert len(clean_txs) == 1

        # Cluster input addresses
        uf = UnionFind()
        for tx in clean_txs:
            input_addrs = [
                vin.get("prevout", {}).get("scriptpubkey_address")
                for vin in tx.get("vin", [])
                if vin.get("prevout", {}).get("scriptpubkey_address")
            ]
            cluster_addresses(uf, input_addrs)

        # Whale addresses should be clustered
        assert uf.connected("whale_addr1", "whale_addr2")

    def test_coinjoin_not_clustered_after_filter(self):
        """CoinJoin inputs should not affect clustering after filtering."""
        from scripts.clustering import filter_coinjoins
        from scripts.clustering.address_clustering import cluster_addresses
        from scripts.clustering.union_find import UnionFind

        transactions = [
            # Normal whale tx
            {
                "txid": "whale1",
                "vin": [
                    {"prevout": {"scriptpubkey_address": "whale1"}},
                    {"prevout": {"scriptpubkey_address": "whale2"}},
                ],
                "vout": [{"value": 50.0, "scriptPubKey": {"address": "dest"}}],
            },
            # CoinJoin (should be filtered out)
            {
                "txid": "coinjoin1",
                "vin": [{"txid": f"in{i}", "vout": 0} for i in range(8)],
                "vout": [
                    {"value": 0.1, "scriptPubKey": {"address": f"out{i}"}}
                    for i in range(8)
                ],
            },
        ]

        clean_txs = filter_coinjoins(transactions)

        # Build clusters only from clean txs
        uf = UnionFind()
        for tx in clean_txs:
            input_addrs = [
                vin.get("prevout", {}).get("scriptpubkey_address")
                for vin in tx.get("vin", [])
                if vin.get("prevout", {}).get("scriptpubkey_address")
            ]
            if input_addrs:
                cluster_addresses(uf, input_addrs)

        # Only whale addresses should be clustered
        clusters = uf.get_clusters()
        assert len(clusters) == 1
        assert "whale1" in clusters[0]
        assert "whale2" in clusters[0]


# =============================================================================
# Edge Case Tests (Regression Prevention)
# =============================================================================


class TestEdgeCasesRegression:
    """Tests for edge cases that previously caused crashes."""

    def test_is_round_amount_handles_infinity(self):
        """_is_round_amount should not crash on infinity."""
        from scripts.clustering.change_detector import _is_round_amount

        # Should not raise exception
        result = _is_round_amount(float("inf"))
        assert result is True  # Infinity treated as "round" (safe default)

    def test_is_round_amount_handles_nan(self):
        """_is_round_amount should not crash on NaN."""
        from scripts.clustering.change_detector import _is_round_amount

        result = _is_round_amount(float("nan"))
        assert result is True  # NaN treated as "round" (safe default)

    def test_is_round_amount_handles_negative(self):
        """_is_round_amount should handle negative values."""
        from scripts.clustering.change_detector import _is_round_amount

        result = _is_round_amount(-100)
        assert result is True  # Negative treated as "round" (safe default)

    def test_normalize_to_satoshis_handles_infinity(self):
        """_normalize_to_satoshis should not crash on infinity."""
        from scripts.clustering.coinjoin_detector import _normalize_to_satoshis

        result = _normalize_to_satoshis(float("inf"))
        assert result == 0  # Invalid values return 0

    def test_normalize_to_satoshis_handles_nan(self):
        """_normalize_to_satoshis should not crash on NaN."""
        from scripts.clustering.coinjoin_detector import _normalize_to_satoshis

        result = _normalize_to_satoshis(float("nan"))
        assert result == 0  # Invalid values return 0

    def test_normalize_to_satoshis_handles_negative(self):
        """_normalize_to_satoshis should handle negative values."""
        from scripts.clustering.coinjoin_detector import _normalize_to_satoshis

        result = _normalize_to_satoshis(-100)
        assert result == 0  # Invalid values return 0

    def test_detect_coinjoin_empty_tx(self):
        """detect_coinjoin should handle empty transactions gracefully."""
        from scripts.clustering import detect_coinjoin

        result = detect_coinjoin({})
        assert result.is_coinjoin is False
        assert result.txid == "unknown"

    def test_detect_change_outputs_empty_tx(self):
        """detect_change_outputs should handle empty transactions gracefully."""
        from scripts.clustering import detect_change_outputs

        result = detect_change_outputs({})
        assert result.likely_change_outputs == []
        assert result.likely_payment_outputs == []

    def test_filter_coinjoins_empty_list(self):
        """filter_coinjoins should handle empty list gracefully."""
        from scripts.clustering import filter_coinjoins

        result = filter_coinjoins([])
        assert result == []
