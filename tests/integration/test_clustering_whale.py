"""Integration tests for Address Clustering with Whale Detection.

Tests the complete flow of:
1. Filtering CoinJoins from transactions
2. Clustering addresses from clean transactions
3. Using clustering data with whale flow analysis

These tests validate the integration between modules,
not individual component behavior (covered in unit tests).
"""


class TestClusteringWhaleIntegration:
    """Integration tests for clustering + whale detection workflow."""

    def test_full_clustering_workflow(self):
        """Test complete clustering workflow: filter → cluster → analyze."""
        from scripts.clustering import (
            UnionFind,
            cluster_addresses,
            filter_coinjoins,
            get_cluster_stats,
        )

        # Sample transactions from a block
        transactions = [
            # Normal whale transaction
            {
                "txid": "whale_tx_1",
                "vin": [
                    {"prevout": {"scriptpubkey_address": "whale_hot_1"}},
                    {"prevout": {"scriptpubkey_address": "whale_hot_2"}},
                    {"prevout": {"scriptpubkey_address": "whale_hot_3"}},
                ],
                "vout": [
                    {"value": 500.0, "scriptPubKey": {"address": "exchange_deposit"}},
                ],
            },
            # Another whale consolidation
            {
                "txid": "whale_tx_2",
                "vin": [
                    {"prevout": {"scriptpubkey_address": "whale_cold_1"}},
                    {"prevout": {"scriptpubkey_address": "whale_cold_2"}},
                ],
                "vout": [
                    {"value": 300.0, "scriptPubKey": {"address": "whale_hot_1"}},
                ],
            },
            # CoinJoin (should be filtered)
            {
                "txid": "coinjoin_tx",
                "vin": [{"txid": f"in{i}", "vout": 0} for i in range(8)],
                "vout": [
                    {"value": 0.1, "scriptPubKey": {"address": f"mixer{i}"}}
                    for i in range(8)
                ],
            },
            # Normal user payment
            {
                "txid": "user_payment",
                "vin": [{"prevout": {"scriptpubkey_address": "user_1"}}],
                "vout": [
                    {"value": 0.5, "scriptPubKey": {"address": "merchant"}},
                    {"value": 0.1, "scriptPubKey": {"address": "user_change"}},
                ],
            },
        ]

        # Step 1: Filter CoinJoins
        clean_txs = filter_coinjoins(transactions)
        assert len(clean_txs) == 3  # CoinJoin removed

        # Step 2: Build address clusters
        uf = UnionFind()
        for tx in clean_txs:
            input_addrs = [
                vin.get("prevout", {}).get("scriptpubkey_address")
                for vin in tx.get("vin", [])
                if vin.get("prevout", {}).get("scriptpubkey_address")
            ]
            if input_addrs:
                cluster_addresses(uf, input_addrs)

        # Step 3: Analyze clusters
        stats = get_cluster_stats(uf)

        # Verify clustering
        # whale_tx_1: whale_hot_1, whale_hot_2, whale_hot_3 (cluster A)
        # whale_tx_2: whale_cold_1, whale_cold_2 -> whale_hot_1 (connects to cluster A)
        # user_payment: user_1 only (singleton, not clustered with multiple inputs)
        # So we have: 1 whale cluster + 1 user singleton = potentially 2 clusters
        # But user_1 only has 1 input, so it's just added to UnionFind as singleton
        assert stats["cluster_count"] >= 1  # At least the whale cluster

        # Whale addresses should be clustered together via whale_hot_1
        # whale_tx_2 outputs to whale_hot_1, connecting cold wallets to hot
        assert uf.connected("whale_hot_1", "whale_hot_2")
        assert uf.connected("whale_hot_1", "whale_hot_3")
        assert uf.connected("whale_cold_1", "whale_cold_2")  # Same tx inputs

        # User is separate (only 1 input, doesn't create multi-input cluster)
        assert not uf.connected("whale_hot_1", "user_1")

    def test_coinjoin_filtering_preserves_whale_signals(self):
        """Verify CoinJoin filtering doesn't remove whale transactions."""
        from scripts.clustering import filter_coinjoins

        transactions = [
            # Large whale transaction (not CoinJoin - different output values)
            {
                "txid": "big_whale",
                "vin": [{"txid": f"in{i}", "vout": 0} for i in range(10)],
                "vout": [
                    {"value": 1000.0, "scriptPubKey": {"address": "dest1"}},
                    {"value": 500.0, "scriptPubKey": {"address": "dest2"}},
                    {"value": 250.0, "scriptPubKey": {"address": "change"}},
                ],
            },
            # CoinJoin (equal outputs)
            {
                "txid": "coinjoin",
                "vin": [{"txid": f"in{i}", "vout": 0} for i in range(10)],
                "vout": [
                    {"value": 0.1, "scriptPubKey": {"address": f"out{i}"}}
                    for i in range(10)
                ],
            },
        ]

        filtered = filter_coinjoins(transactions)

        # Whale transaction preserved
        assert len(filtered) == 1
        assert filtered[0]["txid"] == "big_whale"

    def test_cluster_size_for_entity_identification(self):
        """Large clusters suggest exchanges or services."""
        from scripts.clustering import UnionFind, cluster_addresses, get_cluster_stats

        uf = UnionFind()

        # Simulate many transactions from one entity
        for i in range(20):
            # Each tx has 2-3 addresses from same entity
            addrs = [f"entity_addr_{i * 3 + j}" for j in range(3)]
            if i > 0:
                # Connect to previous transaction
                addrs.append(f"entity_addr_{(i - 1) * 3}")
            cluster_addresses(uf, addrs)

        stats = get_cluster_stats(uf)

        # Single large cluster
        assert stats["cluster_count"] == 1
        assert stats["max_cluster_size"] >= 50  # Many connected addresses

    def test_detection_accuracy_with_real_patterns(self):
        """Test against realistic CoinJoin vs normal transaction patterns."""
        from scripts.clustering import detect_coinjoin

        # Wasabi-style (many equal outputs)
        wasabi_tx = {
            "txid": "wasabi",
            "vin": [{"txid": f"in{i}", "vout": 0} for i in range(50)],
            "vout": [
                {"value": 0.01, "scriptPubKey": {"address": f"out{i}"}}
                for i in range(100)
            ],
        }
        assert detect_coinjoin(wasabi_tx).coinjoin_type == "wasabi"

        # Whirlpool-style (fixed denomination)
        whirlpool_tx = {
            "txid": "whirlpool",
            "vin": [{"txid": f"in{i}", "vout": 0} for i in range(5)],
            "vout": [
                {"value": 0.05, "scriptPubKey": {"address": f"out{i}"}}
                for i in range(5)
            ],
        }
        assert detect_coinjoin(whirlpool_tx).coinjoin_type == "whirlpool"

        # Exchange withdrawal (many outputs, different amounts)
        exchange_tx = {
            "txid": "exchange_batch",
            "vin": [{"txid": "hot_wallet", "vout": 0}],
            "vout": [
                {"value": 0.5 + i * 0.1, "scriptPubKey": {"address": f"user{i}"}}
                for i in range(20)
            ],
        }
        assert not detect_coinjoin(exchange_tx).is_coinjoin


class TestChangeDetectionIntegration:
    """Integration tests for change detection with clustering."""

    def test_change_output_not_clustered(self):
        """Change outputs should be identified but not affect clustering."""
        from scripts.clustering import (
            UnionFind,
            cluster_addresses,
            detect_change_outputs,
        )

        tx = {
            "txid": "payment",
            "vin": [
                {"prevout": {"scriptpubkey_address": "sender_1"}},
                {"prevout": {"scriptpubkey_address": "sender_2"}},
            ],
            "vout": [
                {"value": 1.0, "scriptPubKey": {"address": "merchant"}},  # Payment
                {"value": 0.05, "scriptPubKey": {"address": "change"}},  # Change
            ],
        }

        # Detect change
        change_result = detect_change_outputs(tx)
        assert 1 in change_result.likely_change_outputs

        # Cluster inputs
        uf = UnionFind()
        cluster_addresses(uf, ["sender_1", "sender_2"])

        # Sender addresses clustered
        assert uf.connected("sender_1", "sender_2")
