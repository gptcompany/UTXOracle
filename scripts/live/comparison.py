from __future__ import annotations

from scripts.live.models import LiveComparison


def compute_basis_points(value: float | None, reference: float | None) -> float | None:
    if value is None or reference is None or reference == 0:
        return None
    return ((value - reference) / reference) * 10_000


def build_live_comparison(
    utxoracle_price: float | None,
    mempool_exchange_price: float | None,
    hyperliquid_oracle_price: float | None,
    hyperliquid_mark_price: float | None,
) -> LiveComparison:
    return LiveComparison(
        utxo_vs_mempool_bps=compute_basis_points(
            utxoracle_price, mempool_exchange_price
        ),
        utxo_vs_hl_oracle_bps=compute_basis_points(
            utxoracle_price, hyperliquid_oracle_price
        ),
        utxo_vs_hl_mark_bps=compute_basis_points(
            utxoracle_price, hyperliquid_mark_price
        ),
    )
