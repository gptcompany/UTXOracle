import pytest

from scripts.live.comparison import build_live_comparison, compute_basis_points


def test_compute_basis_points_uses_reference_denominator():
    result = compute_basis_points(84_211.52, 84_302.11)

    assert result == pytest.approx(-10.745875755659792, rel=1e-6)


def test_build_live_comparison_handles_missing_sources():
    comparison = build_live_comparison(84_211.52, None, 84_295.40, 84_310.80)

    assert comparison.utxo_vs_mempool_bps is None
    assert comparison.utxo_vs_hl_oracle_bps == pytest.approx(-9.950720917154447, rel=1e-6)
    assert comparison.utxo_vs_hl_mark_bps == pytest.approx(-11.775478349155604, rel=1e-6)
