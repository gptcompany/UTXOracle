"""Regressione F-415: /api/research/tier-stats usava repo.fetchall, che non esiste.

Il repo e' un mock con autospec: un metodo inesistente solleva AttributeError
(come in produzione) invece di essere accettato in silenzio. Nessun servizio reale.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, create_autospec

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.questdb_repository import QuestDBRepository
from api.routes.questdb import get_questdb_repo, router


def _client(repo) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_questdb_repo] = lambda: repo
    return TestClient(app, raise_server_exceptions=False)


def test_tier_stats_uses_existing_repo_methods():
    repo = create_autospec(QuestDBRepository, instance=True)
    repo.fetch = AsyncMock(
        return_value=[
            {"fetch_tier": 1, "cnt": 3},
            {"fetch_tier": 2, "cnt": 1},
        ]
    )
    repo.fetchrow = AsyncMock(return_value={"fetch_tier": 1})

    resp = _client(repo).get("/api/research/tier-stats?days=7")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_samples"] == 4
    assert body["last_tier_used"] == 1
    assert {s["tier"]: s["percentage"] for s in body["stats"]} == {
        1: 75.0,
        2: 25.0,
    }
