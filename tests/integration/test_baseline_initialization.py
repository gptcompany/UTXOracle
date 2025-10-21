"""
Integration test for baseline initialization in orchestrator.

Tests that baseline calculator's initial calculation is passed to mempool analyzer.
"""

import pytest
from live.backend.orchestrator import PipelineOrchestrator
from unittest.mock import Mock, patch


def test_orchestrator_passes_initial_baseline_to_analyzer():
    """
    Test that when orchestrator starts, the baseline calculated during
    BaselineCalculator initialization is passed to the mempool analyzer.

    This test should FAIL currently because orchestrator doesn't retrieve
    and pass the initial baseline.
    """
    # Mock Bitcoin RPC to prevent actual blockchain access
    with patch("live.backend.baseline_calculator.BitcoinRPC") as mock_rpc_class:
        mock_rpc = Mock()

        # Mock ask_node to handle RPC calls
        def mock_ask_node(method, *args):
            if method == "getblockcount":
                return 1000
            elif method == "getblockhash":
                height = args[0][0] if args and len(args[0]) > 0 else 0
                return "0" * 64  # Simple 64-char hex string
            elif method == "getblock":
                blockhash = args[0][0] if args and len(args[0]) > 0 else ""
                return {
                    "time": 1000000,  # Block-level timestamp
                    "height": 900,  # Block height
                    "tx": [
                        {
                            "vout": [
                                {
                                    "value": 0.001,
                                    "scriptPubKey": {"type": "pubkeyhash"},
                                },
                                {
                                    "value": 0.002,
                                    "scriptPubKey": {"type": "pubkeyhash"},
                                },
                            ],
                            "vin": [{"txid": "a" * 64}],
                        }
                    ]
                    * 20,  # 20 transactions per block
                }
            return None

        mock_rpc.ask_node = mock_ask_node
        mock_rpc_class.return_value = mock_rpc

        # Create orchestrator (which creates BaselineCalculator and MempoolAnalyzer)
        orchestrator = PipelineOrchestrator()

        # Check that analyzer has baseline set
        assert hasattr(orchestrator.analyzer, "baseline"), (
            "Analyzer should have 'baseline' attribute"
        )

        assert orchestrator.analyzer.baseline is not None, (
            "Analyzer baseline should not be None after orchestrator init"
        )

        assert orchestrator.analyzer.baseline.price > 0, (
            f"Baseline price should be positive, got {orchestrator.analyzer.baseline.price}"
        )

        print(
            f"✓ Analyzer initialized with baseline: ${orchestrator.analyzer.baseline.price:,.0f}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
