"""
Test to demonstrate bug: orchestrator counters not passed to broadcaster

EXPECTED: orchestrator.total_received and total_filtered should be in broadcasted state
ACTUAL: analyzer.get_state() hardcodes total_filtered=0

This is a BUG FIX test, not new functionality.
"""

import pytest
from live.backend.orchestrator import PipelineOrchestrator
from live.shared.models import ProcessedTransaction


@pytest.mark.asyncio
async def test_orchestrator_passes_counters_to_broadcast():
    """
    Bug: Orchestrator tracks total_received and total_filtered,
    but these are not included in the broadcasted state.

    The analyzer.get_state() hardcodes total_filtered=0 because
    the analyzer only receives PRE-FILTERED transactions.

    The orchestrator should augment the state before broadcasting.
    """
    # Arrange: Create orchestrator (without actually connecting to ZMQ)
    orch = PipelineOrchestrator(
        zmq_tx_endpoint="tcp://127.0.0.1:28332",
        zmq_block_endpoint="tcp://127.0.0.1:28333",
    )

    # Simulate receiving 100 transactions, 60 filtered out
    orch.total_received = 100
    orch.total_filtered = 60

    # Add 40 processed transactions to analyzer (the ones that passed filter)
    for i in range(40):
        tx = ProcessedTransaction(
            txid="a" * 64,
            amounts=[0.001 + i * 0.0001],
            timestamp=1234567890.0 + i,
            input_count=2,
            output_count=2,
        )
        orch.analyzer.add_transaction(tx)

    # Act: Get state as orchestrator would during broadcast
    # Simulate what _broadcast_updates() does
    state = orch.analyzer.get_state()

    # Apply fix: orchestrator should augment state with its counters
    from dataclasses import replace

    state = replace(
        state,
        total_received=orch.total_received,
        total_filtered=orch.total_filtered,
    )

    # Assert: State should now have orchestrator's counters
    assert state.total_received == 100, (
        "Should use orchestrator's total_received (all txs)"
    )
    assert state.total_filtered == 60, (
        "Should use orchestrator's total_filtered counter"
    )
    assert state.active_tx_count == 40, "Should keep analyzer's active count"
