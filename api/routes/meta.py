import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["meta"])

MANIFEST_PATH = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "feature_provenance_manifest.yaml"


class FeatureFailureMode(BaseModel):
    empty: str
    stale: str
    degraded: str
    misconfigured: str
    placeholder: str


class FeatureEntry(BaseModel):
    surface_id: str
    route_family: str
    backend_class: str
    primary_tables: List[str]
    upstreams: List[str]
    required_env: List[str]
    writer_owner: str
    read_path_owner: str
    freshness_source: str
    failure_mode: FeatureFailureMode
    provenance_notes: List[str]


class FeatureProvenanceManifest(BaseModel):
    schema_version: str
    published_at: str
    source_documents: List[str]
    backend_classes: Dict[str, str]
    failure_mode_vocabulary: Dict[str, str]
    entries: List[FeatureEntry]


@router.get("/api/meta/features", response_model=FeatureProvenanceManifest)
async def get_feature_provenance():
    """
    Returns the canonical feature dependency and provenance manifest.
    This describes the backend class, data sources, failure semantics,
    and ownership for every production route family exposed by this service.
    """
    if not MANIFEST_PATH.exists():
        logging.error(f"Feature provenance manifest not found at {MANIFEST_PATH}")
        raise HTTPException(
            status_code=503,
            detail="Feature provenance manifest is currently unavailable."
        )

    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest_data = yaml.safe_load(f)
            
        return FeatureProvenanceManifest(**manifest_data)
    except yaml.YAMLError as e:
        logging.error(f"Failed to parse feature provenance manifest: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to parse feature provenance manifest."
        )
    except Exception as e:
        logging.exception(f"Unexpected error reading feature provenance manifest: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error reading feature provenance manifest."
        )
