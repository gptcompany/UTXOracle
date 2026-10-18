"""The frontend must not call HTTP/WebSocket routes that no mounted FastAPI app serves (F-236).

URL literals are read from the JavaScript AST (tree-sitter), in every ``frontend/**/*.js`` and in the inline
``<script>`` blocks of ``frontend/**/*.html``; no line regex on source text. They are matched against the routes of
both mounted apps (``api.apps.live.create_app`` and ``api.main.app``). The dead whale JWT/WebSocket surface
(``/ws/whale-alerts``, ``/api/auth/*``) was removed from the backend; a frontend call to it would be reported here.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
import tree_sitter_javascript
from tree_sitter import Language, Node, Parser

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

# Same-origin paths only: string literals starting with one of these are treated as API/WebSocket URLs.
URL_PREFIXES = ("/api/", "/ws/", "/v1/", "/health", "/metrics", "/auth", "/token")

# Calls to routes no mounted app serves, present before F-236 and unrelated to auth. Each entry must still be
# missing (see test_known_missing_routes_are_still_missing): fix the route or the page, then delete the entry.
KNOWN_MISSING: dict[str, str] = {
    "/api/health": "frontend/metrics/index.html polls /api/health; only /health exists",
    "/api/metrics/pro-risk": "frontend/metrics/pro_risk.html: no /api/metrics/pro-risk route in either app",
    "/api/metrics/pro-risk/history": "frontend/metrics/pro_risk.html: no history route",
    "/api/metrics/puell-multiple/history": "frontend/metrics/puell_multiple.html: no history route",
    "/api/metrics/reserve-risk/history": "frontend/metrics/reserve_risk.html: no history route",
}

_PARSER = Parser(Language(tree_sitter_javascript.language()))


class _InlineScripts(HTMLParser):
    """Collect the text of ``<script>`` elements without a ``src``."""

    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[str] = []
        self._current: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and not dict(attrs).get("src"):
            self._current = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._current is not None:
            self.scripts.append("".join(self._current))
            self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current.append(data)


def _sources() -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []
    for path in sorted(FRONTEND.rglob("*")):
        rel = path.relative_to(ROOT).as_posix()
        if path.suffix == ".js":
            sources.append((rel, path.read_text(encoding="utf-8")))
        elif path.suffix == ".html":
            parser = _InlineScripts()
            parser.feed(path.read_text(encoding="utf-8"))
            sources.extend(
                (f"{rel}#script{i}", text) for i, text in enumerate(parser.scripts)
            )
    return sources


def _literal_value(node: Node, source: bytes) -> str | None:
    """Text of a string literal; ``${...}`` substitutions of a template literal become ``{*}``."""
    if node.type == "string":
        return source[node.start_byte + 1 : node.end_byte - 1].decode()
    if node.type == "template_string":
        parts: list[str] = []
        for child in node.children:
            if child.type == "template_substitution":
                parts.append("{*}")
            elif child.type == "string_fragment":
                parts.append(source[child.start_byte : child.end_byte].decode())
        return "".join(parts)
    return None


def _walk(node: Node):
    yield node
    for child in node.children:
        yield from _walk(child)


def frontend_urls() -> dict[str, set[str]]:
    """Map each same-origin URL path literal found in the frontend to the places it appears."""
    found: dict[str, set[str]] = {}
    for where, text in _sources():
        source = text.encode()
        for node in _walk(_PARSER.parse(source).root_node):
            value = _literal_value(node, source)
            if value is None:
                continue
            value = re.sub(
                r"^\{\*\}(?=/)", "", value
            )  # `${API_BASE}/api/...`: the base is not part of the path
            if value.startswith(URL_PREFIXES):
                path = re.split(r"[?#]", value, maxsplit=1)[0]
                found.setdefault(path, set()).add(f"{where}:{node.start_point[0] + 1}")
    return found


@pytest.fixture(scope="module")
def routes():
    from api.apps.live import create_app
    from api.main import app as legacy_app

    return [route for app in (create_app(), legacy_app) for route in app.routes]


def _served(path: str, routes) -> bool:
    probe = path.replace("{*}", "x")
    for route in routes:
        regex = getattr(route, "path_regex", None)
        if regex is not None and regex.match(probe):
            return True
        if route.__class__.__name__ == "Mount" and probe.startswith(route.path):
            return True
    # A base such as "/api/metrics", used as `${BASE}/name`, is served when routes exist below it.
    return any(
        getattr(route, "path", "").startswith(probe.rstrip("/") + "/")
        for route in routes
    )


def test_url_extraction_reads_the_ast_not_text() -> None:
    source = (
        b"// fetch('/api/in/comment')\n"
        b"const a = fetch('/api/real');\n"
        b"const b = new WebSocket(`${base}/ws/live?x=${t}`);\n"
        b"const c = '/static/not-an-api';\n"
    )
    seen = set()
    for node in _walk(_PARSER.parse(source).root_node):
        value = _literal_value(node, source)
        if value is not None and value.startswith(("/api/", "{*}/ws/", "/static")):
            seen.add(value)
    assert seen == {"/api/real", "{*}/ws/live?x={*}", "/static/not-an-api"}


def test_frontend_calls_only_served_routes(routes) -> None:
    missing = {
        path: sorted(where)
        for path, where in frontend_urls().items()
        if path not in KNOWN_MISSING and not _served(path, routes)
    }
    assert not missing, f"frontend calls routes no mounted app serves: {missing}"


def test_removed_whale_auth_surface_is_not_referenced() -> None:
    urls = frontend_urls()
    assert "/ws/whale-alerts" not in urls
    assert not [
        path for path in urls if path.startswith(("/api/auth", "/auth", "/token"))
    ]


@pytest.mark.parametrize("path", sorted(KNOWN_MISSING))
def test_known_missing_routes_are_still_missing(path: str, routes) -> None:
    urls = frontend_urls()
    assert path in urls, (
        f"{path} is no longer used by the frontend: remove it from KNOWN_MISSING"
    )
    assert not _served(path, routes), (
        f"{path} is now served: remove it from KNOWN_MISSING"
    )
