"""The Recalibrate button sends the login token to the write-protected route (F-266).

The page runs in a real browser; every request is answered locally by page.route, so the test
needs no server and no network. Skipped only when neither Playwright nor a Chrome is available.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
ORIGIN = "http://utxoracle.test"
RECALIBRATE = "/api/v1/models/power-law/recalibrate"
TOKEN_KEY = "utxoracle_jwt_token"
# Synthetic unsigned token with a far expiry: the page only reads its exp, the server verifies it.
FAKE_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJleHAiOjQxMDI0NDQ4MDB9.c2ln"
CHART_STUB = """
const PowerLawChart = {
  async init() {}, async update() {}, getModelInfo() { return null; }
};
"""


@pytest.fixture
def page():
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome")
        except sync_api.Error as exc:
            pytest.skip(f"no Chrome for Playwright: {exc.message.splitlines()[0]}")
        yield browser.new_page()
        browser.close()


def _serve(page, recalibrate_status: int) -> list[dict]:
    """Answer every request locally; return the recorded recalibrate requests."""
    calls = []

    def handle(route):
        request = route.request
        path = request.url.removeprefix(ORIGIN).split("?")[0]
        if path == "/power_law":
            return route.fulfill(
                body=(FRONTEND / "power_law.html").read_text(), content_type="text/html"
            )
        if path == "/static/js/auth.js":
            return route.fulfill(
                body=(FRONTEND / "js/auth.js").read_text(),
                content_type="text/javascript",
            )
        if path.endswith("power_law_chart.js"):
            return route.fulfill(body=CHART_STUB, content_type="text/javascript")
        if path == RECALIBRATE:
            calls.append({"method": request.method, "headers": request.headers})
            return route.fulfill(
                status=recalibrate_status,
                body=json.dumps({}),
                content_type="application/json",
            )
        return route.fulfill(body="", content_type="text/javascript")

    page.route("**/*", handle)
    return calls


def _open(page, token: str | None):
    if token:
        page.add_init_script(f"localStorage.setItem({TOKEN_KEY!r}, {token!r})")
    page.goto(f"{ORIGIN}/power_law")
    page.wait_for_load_state("load")


def _click_recalibrate(page):
    page.click("#recalibrate-btn")
    page.wait_for_function(
        "document.getElementById('recalibrate-btn').disabled === false"
    )


def test_recalibrate_sends_the_login_token(page):
    calls = _serve(page, 200)
    _open(page, FAKE_TOKEN)
    _click_recalibrate(page)
    assert [c["method"] for c in calls] == ["POST"]
    assert calls[0]["headers"].get("authorization") == f"Bearer {FAKE_TOKEN}"
    assert page.inner_text("#error-container") == ""


def test_recalibrate_without_token_still_asks_the_server(page):
    # AUTH_ENABLED=false: the server needs no token, so the page must not block the request.
    calls = _serve(page, 200)
    _open(page, None)
    _click_recalibrate(page)
    assert [c["method"] for c in calls] == ["POST"]
    assert "authorization" not in calls[0]["headers"]
    assert page.inner_text("#error-container") == ""


def test_recalibrate_without_token_refused_points_to_login(page):
    calls = _serve(page, 401)
    _open(page, None)
    _click_recalibrate(page)
    assert len(calls) == 1
    assert (
        page.get_attribute("#error-container a", "href")
        == "/static/login.html?return=/power_law"
    )


@pytest.mark.parametrize("status", [401, 403])
def test_recalibrate_rejected_token_is_cleared_and_reports_write_permission(
    page, status
):
    calls = _serve(page, status)
    _open(page, FAKE_TOKEN)
    _click_recalibrate(page)
    assert len(calls) == 1
    assert "write permission" in page.inner_text("#error-container")
    # login.html redirects back when it finds an unexpired token: the rejected one must be gone.
    assert page.evaluate(f"localStorage.getItem({TOKEN_KEY!r})") is None
