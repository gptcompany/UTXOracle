"""examples/n8n/utxoracle-alerts.json: the ntfy dati node fails closed (#709).

Without NTFY_BASE_URL and a plain NTFY_TOPIC_DATI the workflow must not publish: no public
default in the URL, and the only way into the ntfy node is the true branch of a guard node.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "examples/n8n/utxoracle-alerts.json"


def _workflow() -> dict:
    return json.loads(WORKFLOW.read_text(encoding="utf-8"))


def _ntfy_nodes(workflow: dict) -> list[dict]:
    return [
        n
        for n in workflow["nodes"]
        if "NTFY_TOPIC_DATI" in str(n.get("parameters", {}).get("url", ""))
    ]


def _incoming(workflow: dict, target: str) -> list[tuple[str, int]]:
    """(source node, output index) of every connection into target."""
    edges = []
    for source, outputs in workflow["connections"].items():
        for index, branch in enumerate(outputs.get("main", [])):
            edges += [(source, index) for c in branch if c["node"] == target]
    return edges


def _guard(workflow: dict, name: str) -> dict:
    node = next(n for n in workflow["nodes"] if n["name"] == name)
    assert node["type"] == "n8n-nodes-base.if", (
        f"{name} feeds ntfy but is not an If node"
    )
    return node


def test_ntfy_url_has_no_default_destination():
    nodes = _ntfy_nodes(_workflow())
    assert nodes, "no ntfy dati node found"
    for node in nodes:
        url = node["parameters"]["url"]
        assert "||" not in url and "??" not in url, url
        assert "ntfy.sh" not in url, url


def test_ntfy_node_is_reached_only_through_the_guard_true_branch():
    workflow = _workflow()
    for node in _ntfy_nodes(workflow):
        edges = _incoming(workflow, node["name"])
        assert edges, f"{node['name']} is unreachable"
        for source, index in edges:
            _guard(workflow, source)
            assert index == 0, (
                f"{node['name']} reached from the false branch of {source}"
            )


def _guard_expressions() -> list[str]:
    workflow = _workflow()
    expressions = []
    for node in _ntfy_nodes(workflow):
        for source, _ in _incoming(workflow, node["name"]):
            conditions = _guard(workflow, source)["parameters"]["conditions"]
            assert conditions["combinator"] == "and"
            for cond in conditions["conditions"]:
                assert cond["operator"] == {
                    "type": "boolean",
                    "operation": "true",
                    "singleValue": True,
                }
                expressions.append(cond["leftValue"])
    return expressions


CASES = [
    ({"NTFY_BASE_URL": "https://ntfy.example", "NTFY_TOPIC_DATI": "dati_1"}, True),
    ({"NTFY_BASE_URL": "https://ntfy.example"}, False),
    ({"NTFY_TOPIC_DATI": "dati_1"}, False),
    ({"NTFY_BASE_URL": "https://ntfy.example", "NTFY_TOPIC_DATI": ""}, False),
    ({"NTFY_BASE_URL": "https://ntfy.example", "NTFY_TOPIC_DATI": "ENC[abc]"}, False),
    (
        {"NTFY_BASE_URL": "https://ntfy.example", "NTFY_TOPIC_DATI": "encrypted:abc"},
        False,
    ),
    ({"NTFY_BASE_URL": "", "NTFY_TOPIC_DATI": "dati_1"}, False),
]


@pytest.mark.skipif(
    shutil.which("node") is None, reason="evaluating the n8n expression needs node"
)
@pytest.mark.parametrize(("env", "expected"), CASES)
def test_guard_sends_only_with_base_url_and_plain_topic(env, expected):
    expressions = _guard_expressions()
    assert expressions, "no guard condition found"
    for expression in expressions:
        assert expression.startswith("={{") and expression.endswith("}}"), expression
        body = expression[3:-2]
        script = f"const $env = {json.dumps(env)}; process.stdout.write(String(Boolean({body})));"
        out = subprocess.run(
            ["node", "-e", script],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout
        assert out == str(expected).lower(), (env, expression)
