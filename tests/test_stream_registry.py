"""Tests for the consumer-facing stream registry (spec-061).

T004 (schema validation), T004b (name immutability), T027 (schema_version
presence). RED first, then GREEN by aligning the registry YAML.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft7Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "docs" / "contracts" / "stream_registry.yaml"
SCHEMA = (
    REPO_ROOT
    / "specs"
    / "061-stream-consumption-contract"
    / "contracts"
    / "stream_registry.schema.yaml"
)

EXPECTED_NAMES = (
    "live_snapshots",
    "entity_flows_daily",
    "whale_transactions",
    "mempool_predictions",
    "net_flow_metrics",
    "backtest_whale_signals",
    "price_analysis",
    "urpd_features_daily",
    "utxo_lifecycle_full",
    "utxo_snapshots",
    "mvrv_daily",
    "nupl_daily",
    "realized_cap_daily",
)


@pytest.fixture(scope="module")
def registry() -> dict:
    return yaml.safe_load(REGISTRY.read_text())


@pytest.fixture(scope="module")
def schema() -> dict:
    return yaml.safe_load(SCHEMA.read_text())


def test_registry_validates_against_schema(registry, schema):
    """T004: registry MUST conform to its JSON Schema."""
    errors = sorted(
        Draft7Validator(schema).iter_errors(registry),
        key=lambda e: list(e.absolute_path),
    )
    assert not errors, "\n".join(
        f"{list(e.absolute_path)}: {e.message}" for e in errors
    )


def test_registry_has_exactly_13_streams(registry):
    """T004: registry MUST have exactly 13 entries per spec-061 FR-001."""
    assert len(registry["streams"]) == 13


def test_stream_names_are_unique(registry):
    """T004: stream names MUST be unique."""
    names = [s["name"] for s in registry["streams"]]
    assert len(set(names)) == len(names)


def test_stream_names_frozen(registry):
    """T004b: the 13 contractual names MUST match EXPECTED_NAMES exactly.

    Renaming any stream is a breaking change under FR-005 and requires the
    30-day overlap window from FR-009. This test fails loudly if a future
    PR drifts from the contract.
    """
    actual = set(s["name"] for s in registry["streams"])
    expected = set(EXPECTED_NAMES)
    missing = expected - actual
    extra = actual - expected
    assert not missing and not extra, (
        f"Stream name contract violated.\n"
        f"  missing (renamed or removed?): {sorted(missing)}\n"
        f"  extra   (new without deprecation?): {sorted(extra)}\n"
        f"If this is an intentional contract change, update EXPECTED_NAMES "
        f"AND publish a deprecation entry per FR-009 (30-day overlap)."
    )


def test_schema_version_present_and_semver(registry):
    """T027: every stream MUST declare a SemVer schema_version."""
    pattern = re.compile(r"^\d+\.\d+\.\d+$")
    for s in registry["streams"]:
        v = s.get("schema_version")
        assert v is not None, f"{s['name']}: missing schema_version"
        assert pattern.match(v), f"{s['name']}: schema_version {v!r} is not SemVer"


def test_freshness_strategy_required_fields(registry):
    """T011a precondition: tip_lag_blocks entries declare block_column;
    max_ts entries declare timestamp_column."""
    for s in registry["streams"]:
        strategy = s["freshness_strategy"]
        if strategy == "max_ts":
            assert "timestamp_column" in s, (
                f"{s['name']}: max_ts strategy requires timestamp_column"
            )
        elif strategy == "tip_lag_blocks":
            # F5 (review 2026-06-02): block_column and block_columns are
            # mutually exclusive — the schema enforces it; we assert XOR here
            # to keep the operational contract visible at the test layer.
            has_single = "block_column" in s
            has_multi = "block_columns" in s
            assert has_single ^ has_multi, (
                f"{s['name']}: tip_lag_blocks entry must declare exactly one of "
                f"block_column / block_columns (got both={has_single and has_multi}, "
                f"neither={not (has_single or has_multi)})"
            )
            if has_multi:
                assert all(isinstance(c, str) for c in s["block_columns"])
        else:
            raise AssertionError(
                f"{s['name']}: unknown freshness_strategy {strategy!r}"
            )


def test_block_column_and_block_columns_are_mutually_exclusive(schema):
    """F5 (review 2026-06-02): schema MUST reject entries declaring BOTH columns.

    A misconfigured entry where both forms are set would silently lose either
    block_column (because route prefers block_columns) or surface a confusing
    inconsistency; mutual exclusion at the schema layer fails fast at startup.
    """
    bad_entry = {
        "name": "fake_stream",
        "table": "fake_table",
        "freshness_strategy": "tip_lag_blocks",
        "block_column": "spent_block",
        "block_columns": ["creation_block", "spent_block"],
        "schema_version": "1.0.0",
        "sla_seconds": 259200,
        "source_spec": "specs/017",
        "pinned_columns": ["spent_block"],
    }
    errors = list(
        Draft7Validator(schema).iter_errors(
            {"version": "1.0.0", "streams": [bad_entry] * 13}
        )
    )
    assert errors, (
        "schema must reject entries with BOTH block_column and block_columns"
    )


def test_utxo_lifecycle_freshness_checks_creations_and_spends(registry):
    """Operational guard: spent freshness alone can produce a false OK."""
    entry = next(s for s in registry["streams"] if s["name"] == "utxo_lifecycle_full")
    assert entry["freshness_strategy"] == "tip_lag_blocks"
    assert set(entry["block_columns"]) == {"creation_block", "spent_block"}


def test_sla_seconds_positive(registry):
    """Every stream MUST declare sla_seconds > 0."""
    for s in registry["streams"]:
        assert s["sla_seconds"] > 0, f"{s['name']}: sla_seconds must be > 0"


def test_deprecated_at_field_optional(registry, schema):
    """T029: deprecated_at MUST be optional; registry MUST validate with or without it.

    Constructs a synthetic registry copy where one entry carries
    `deprecated_at: 2026-05-31`. The schema MUST accept it without
    error, and a registry without any `deprecated_at` field (the
    current state) MUST also validate.
    """
    # Current registry has zero deprecated_at fields; it must still validate.
    errors = list(Draft7Validator(schema).iter_errors(registry))
    assert not errors, "Registry without any deprecated_at must validate"

    # Add deprecated_at to one entry; it must still validate.
    augmented = copy.deepcopy(registry)
    augmented["streams"][0]["deprecated_at"] = "2026-05-31"
    errors = list(Draft7Validator(schema).iter_errors(augmented))
    assert not errors, (
        "Registry with deprecated_at on one entry must validate; "
        f"errors: {[e.message for e in errors]}"
    )
