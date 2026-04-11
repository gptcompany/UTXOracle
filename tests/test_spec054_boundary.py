"""Verify spec-054 boundary invariants."""
import yaml

def test_boundary_artifact_exists():
    with open("docs/contracts/surface_boundary.yaml") as f:
        data = yaml.safe_load(f)
    assert data["schema_version"] == "1"
    assert len(data["families"]) > 0

def test_every_family_has_required_fields():
    with open("docs/contracts/surface_boundary.yaml") as f:
        data = yaml.safe_load(f)
    required = {"route_family", "host", "tier", "allowed_consumers", "source_of_truth", "fail_mode", "execution_eligible"}
    for family in data["families"]:
        missing = required - set(family.keys())
        assert not missing, f"{family['route_family']} missing: {missing}"

def test_tier1_execution_is_minimal():
    with open("docs/contracts/surface_boundary.yaml") as f:
        data = yaml.safe_load(f)
    tier1 = [f for f in data["families"] if f["tier"] == "tier_1_execution"]
    # Only live, features, signals, and health
    tier1_prefixes = {f["route_family"] for f in tier1}
    assert tier1_prefixes == {"/health", "/api/v1/live/*", "/api/features/btc/*", "/api/signals/btc/*"}

def test_no_tier2_is_execution_eligible():
    with open("docs/contracts/surface_boundary.yaml") as f:
        data = yaml.safe_load(f)
    for family in data["families"]:
        if family["tier"] != "tier_1_execution":
            assert not family["execution_eligible"], f"{family['route_family']} is non-tier1 but execution_eligible"

def test_registry_tiers_match_boundary():
    """Cross-check registry YAML tiers against boundary artifact."""
    with open("docs/contracts/feature_contract_registry.yaml") as f:
        registry = yaml.safe_load(f)
    with open("docs/contracts/surface_boundary.yaml") as f:
        boundary = yaml.safe_load(f)
    boundary_map = {f["route_family"]: f["tier"] for f in boundary["families"]}
    for entry in registry["entries"]:
        rf = entry["route_family"]
        if rf in boundary_map:
            assert entry["admission_tier"] == boundary_map[rf], f"Mismatch for {rf}: registry={entry['admission_tier']} boundary={boundary_map[rf]}"
