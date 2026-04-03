import pytest
import yaml
import os
from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DOCS_DIR = PROJECT_ROOT / "docs"
CONTRACTS_DIR = DOCS_DIR / "contracts"

REGISTRY_PATH = CONTRACTS_DIR / "feature_contract_registry.yaml"
PROVENANCE_PATH = CONTRACTS_DIR / "feature_provenance_manifest.yaml"
ROADMAP_PATH = DOCS_DIR / "FEATURE_SERVICE_ROADMAP_2026-04-01.md"
CONTRACT_MD_PATH = DOCS_DIR / "FEATURE_CONTRACT_REGISTRY.md"

def load_yaml(path: Path) -> dict:
    with open(path, 'r') as f:
        return yaml.safe_load(f)

@pytest.fixture(scope="module")
def registry():
    return load_yaml(REGISTRY_PATH)

@pytest.fixture(scope="module")
def provenance():
    return load_yaml(PROVENANCE_PATH)

def test_registry_mandatory_fields(registry):
    """T014: Validator that fails on missing required fields in the YAML registry."""
    assert "entries" in registry
    required_fields = {
        "surface_id", "route_family", "routes", "canonical_host",
        "consumer", "current_label", "admission_tier", "source_of_truth",
        "backend_class", "freshness_target", "empty_state_policy",
        "stale_state_policy", "known_caveats", "owner", "version",
        "deprecation_status"
    }
    
    for entry in registry["entries"]:
        missing = required_fields - set(entry.keys())
        assert not missing, f"Registry entry {entry.get('surface_id', 'UNKNOWN')} is missing fields: {missing}"

def test_provenance_mandatory_fields(provenance):
    """T017: Add validation checks for missing backend class, owner, or failure mode."""
    assert "entries" in provenance
    required_fields = {
        "surface_id", "route_family", "backend_class", "primary_tables",
        "upstreams", "required_env", "writer_owner", "read_path_owner",
        "freshness_source", "failure_mode", "provenance_notes"
    }
    
    required_failure_modes = {"empty", "stale", "degraded", "misconfigured", "placeholder"}

    for entry in provenance["entries"]:
        surface_id = entry.get('surface_id', 'UNKNOWN')
        missing = required_fields - set(entry.keys())
        assert not missing, f"Provenance entry {surface_id} is missing fields: {missing}"
        
        failure_mode = entry["failure_mode"]
        missing_modes = required_failure_modes - set(failure_mode.keys())
        assert not missing_modes, f"Provenance entry {surface_id} failure_mode is missing: {missing_modes}"

def test_cross_yaml_consistency(registry, provenance):
    """Ensure both YAMLs cover the exact same surfaces."""
    reg_surfaces = {e["surface_id"] for e in registry["entries"]}
    prov_surfaces = {e["surface_id"] for e in provenance["entries"]}
    
    assert reg_surfaces == prov_surfaces, f"Mismatch in surface_ids between registry and provenance. Only in registry: {reg_surfaces - prov_surfaces}. Only in provenance: {prov_surfaces - reg_surfaces}"

def test_consistency_yaml_vs_markdown(registry):
    """T015: Consistency checks between YAML registry and contract markdown."""
    with open(CONTRACT_MD_PATH, 'r') as f:
        md_content = f.read()
        
    reg_surfaces = {e["surface_id"] for e in registry["entries"]}
    for surface_id in reg_surfaces:
        # Check if the surface_id is mentioned in the Markdown document
        # Usually it's in a table or header. We'll do a simple existence check for now.
        assert surface_id in md_content, f"Surface {surface_id} from YAML not found in {CONTRACT_MD_PATH.name}"

def test_drift_detection_roadmap_vs_manifest(provenance):
    """T018: Detect route-family drift between roadmap docs and manifest."""
    with open(ROADMAP_PATH, 'r') as f:
        roadmap_content = f.read()
    
    # Extract route families from the roadmap table (usually backticked in the first column)
    # E.g. | `/api/prices/*` |
    # This regex looks for Markdown table rows starting with a backticked route.
    route_matches = re.findall(r'\|\s*`(/api/[^`]+)`\s*\|', roadmap_content)
    
    prov_routes = {e["route_family"] for e in provenance["entries"]}
    
    # Some routes in roadmap might be listed slightly differently (e.g. `/api/whale/transactions`, `/summary`...)
    # We will just verify that the base prefix from the roadmap exists in *some* provenance route family.
    # We can also check reverse: does every provenance route have some mention in the roadmap?
    
    for rm_route in route_matches:
        # Clean up commas and multiple routes in a single backtick if any
        base_route = rm_route.split(",")[0].strip().replace("/*", "").replace("*", "")
        # Just ensure the base route string is found somewhere in the provenance routes
        found = any(base_route in pr for pr in prov_routes)
        assert found, f"Roadmap route {rm_route} not found in provenance manifest route families: {prov_routes}"
