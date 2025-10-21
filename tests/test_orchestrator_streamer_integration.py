"""
Integration test for orchestrator + DataStreamer client registration bug.

This test reproduces the bug where:
- WebSocket endpoint registers clients to api.streamer
- Orchestrator broadcasts to orchestrator.streamer (different instance)
- Result: broadcasts skip because "no active clients"
"""

import pytest
from live.backend.api import streamer as api_streamer
from live.backend.orchestrator import get_orchestrator


@pytest.mark.asyncio
async def test_orchestrator_uses_same_streamer_as_api():
    """
    Test that orchestrator broadcasts to the SAME DataStreamer instance
    that the WebSocket endpoint uses for client registration.

    Bug reproduction:
    - api.py creates global streamer instance (line 199)
    - orchestrator.py creates its own streamer instance (line 59)
    - WebSocket registers to api.streamer
    - Orchestrator broadcasts to orchestrator.streamer
    - Result: "No active clients" even though clients are connected

    Fix:
    - Orchestrator should import and use api.streamer
    - OR api.py should get streamer from orchestrator
    - They MUST share the same instance
    """
    # Arrange: Clear cached orchestrator to get fresh instance
    import live.backend.orchestrator as orch_module

    orch_module._orchestrator = None

    # Get orchestrator instance
    orchestrator = get_orchestrator()

    # Act: Check if they share the same DataStreamer instance
    same_instance = orchestrator.streamer is api_streamer

    # Assert: MUST be the same object instance
    assert same_instance, (
        "BUG: Orchestrator creates its own DataStreamer instance instead of "
        "using the global api.streamer instance. This causes WebSocket clients "
        "to register to api.streamer while orchestrator broadcasts to "
        "orchestrator.streamer (different instance), resulting in 'No active clients' "
        "even when clients are connected."
    )
