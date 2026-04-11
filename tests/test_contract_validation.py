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
        "allowed_consumers", "current_label", "admission_tier", "source_of_truth",
        "backend_class", "freshness_target", "empty_state_policy",
        "stale_state_policy", "known_caveats", "owner", "version",
        "deprecation_status"
    }
    
    for entry in registry["entries"]:
        missing = required_fields - set(entry.keys())
        assert not missing, f"Registry entry {entry.get('surface_id', 'UNKNOWN')} is missing fields: {missing}"
        assert isinstance(entry["allowed_consumers"], list), f"Registry entry {entry['surface_id']} allowed_consumers must be a list"
        assert entry["allowed_consumers"], f"Registry entry {entry['surface_id']} allowed_consumers must not be empty"

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
        md_lines = f.readlines()
        
    # Extract surface IDs from the markdown table
    md_surfaces = set()
    in_table = False
    for line in md_lines:
        if line.startswith("| Surface ID |"):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            cols = [col.strip() for col in line.split("|")]
            if len(cols) > 2:
                # First col is empty string due to leading |, second col is Surface ID
                surface_id = cols[1].strip("`")
                if surface_id:
                    md_surfaces.add(surface_id)
        elif in_table and not line.strip():
            in_table = False
            
    reg_surfaces = {e["surface_id"] for e in registry["entries"]}
    for surface_id in reg_surfaces:
        assert surface_id in md_surfaces, f"Surface {surface_id} from YAML not found in the markdown table of {CONTRACT_MD_PATH.name}"

def test_drift_detection_roadmap_vs_manifest(provenance):
    """T018: Detect route-family drift between roadmap docs and manifest."""
    with open(ROADMAP_PATH, 'r') as f:
        md_lines = f.readlines()
    
    roadmap_surfaces = []
    in_table = False
    for line in md_lines:
        if line.startswith("| Surface |"):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            cols = [col.strip() for col in line.split("|")]
            if len(cols) > 2:
                surface = cols[1].strip("`")
                if surface:
                    roadmap_surfaces.append(surface)
        elif in_table and not line.strip():
            in_table = False
            
    prov_routes = {e["route_family"] for e in provenance["entries"]}
    prov_ids = {e["surface_id"] for e in provenance["entries"]}
    
    # We want to make sure roadmap entries map to something in the provenance manifest.
    for rm_surface in roadmap_surfaces:
        # Check if it's a route family prefix or a human-readable name like 'address-cohorts'
        # Roadmap has things like '/api/prices/*' or 'address-cohorts'
        if rm_surface.startswith("/api/"):
            first_part = rm_surface.split(",")[0].strip().strip("`").replace("/*", "").replace("*", "")
            prefix = "/".join(first_part.split("/")[:-1])
            found = any(prefix in pr for pr in prov_routes)
            assert found, f"Roadmap route {rm_surface} not found in provenance manifest route families: {prov_routes}"
        elif "post-`M6`" in rm_surface or "manifest" in rm_surface or "registry" in rm_surface:
            # Skip operational/governance rows that aren't API surfaces
            continue
        else:
            # It's a named surface like 'address-cohorts' or 'PRO Risk'
            # Just ensure it maps to some route or surface ID broadly
            # PRO Risk -> pro_risk_surface
            # Puell Multiple -> puell_multiple_surface
            normalized_name = rm_surface.lower().replace(" ", "_").replace("-", "_")
            found = any(normalized_name in pid for pid in prov_ids) or any(normalized_name in pr.lower().replace("-", "_") for pr in prov_routes)
            assert found, f"Roadmap named surface '{rm_surface}' not found in provenance manifest IDs or routes."
