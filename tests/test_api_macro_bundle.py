import pytest
from pydantic import ValidationError
from api.models.bundles import BTCMacroBundleV1, BTCMacroMetricsV1, BundleMetadata, BundleStatus
from datetime import datetime, timezone

def test_btc_macro_metrics_forbids_unadmitted_fields():
    """
    T029: Prove the bundle does not proxy the full BRK universe.
    Only realized_price_usd, liveliness, reserve_risk, nupl, and sopr are allowed.
    """
    with pytest.raises(ValidationError) as exc:
        BTCMacroMetricsV1(
            realized_price_usd=60000.0,
            unadmitted_brk_field=42.0
        )
    
    assert "Extra inputs are not permitted" in str(exc.value)
    assert "unadmitted_brk_field" in str(exc.value)

def test_btc_macro_bundle_v1_validation():
    """
    T028: Add missing-value and partial-degradation semantics for btc_macro.v1.
    All metric fields are strictly Optional.
    """
    metadata = BundleMetadata(
        schema_version="v1",
        bundle_id="btc_macro.v1",
        sequence_id=1,
        produced_at=datetime.now(timezone.utc),
        bundle_status=BundleStatus.DEGRADED,
        degraded_reasons=["BRK upstream missing nupl"]
    )
    
    metrics = BTCMacroMetricsV1(
        realized_price_usd=50000.0,
        liveliness=None, # Degraded semantic
        reserve_risk=None,
        nupl=None,
        sopr=None
    )
    
    bundle = BTCMacroBundleV1(
        metadata=metadata,
        metrics=metrics,
        source_health={"brk": "degraded"}
    )
    
    assert bundle.metrics.liveliness is None
    assert bundle.metadata.bundle_status == "degraded"
    assert "BRK upstream missing nupl" in bundle.metadata.degraded_reasons
