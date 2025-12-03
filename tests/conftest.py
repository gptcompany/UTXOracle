"""
Pytest configuration and shared fixtures

Add global fixtures here that are used across multiple test modules.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """
    FastAPI test client fixture.

    Imports the app and creates a TestClient for making HTTP requests.
    This fixture is used across all API tests.

    Yields:
        TestClient: Configured FastAPI test client
    """
    from api.main import app

    with TestClient(app) as test_client:
        yield test_client
