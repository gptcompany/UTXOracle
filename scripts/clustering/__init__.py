"""Address Clustering and CoinJoin Detection Module.

Provides heuristics for clustering Bitcoin addresses by entity and detecting
privacy-enhancing transactions (CoinJoins).

Public API:
- UnionFind: Disjoint set data structure for clustering
- cluster_addresses: Multi-input heuristic clustering
- get_cluster_stats: Get clustering statistics
- detect_coinjoin: CoinJoin pattern detection
- filter_coinjoins: Filter CoinJoin transactions from list
- detect_change_outputs: Identify likely change outputs
"""

from scripts.clustering.union_find import UnionFind
from scripts.clustering.address_clustering import (
    AddressCluster,
    cluster_addresses,
    get_cluster_stats,
    get_cluster_for_address,
    save_cluster,
)
from scripts.clustering.coinjoin_detector import (
    CoinJoinResult,
    detect_coinjoin,
    is_coinjoin,
    save_coinjoin_result,
)
from scripts.clustering.change_detector import (
    ChangeDetectionResult,
    detect_change_outputs,
    get_likely_change_address,
)
from scripts.clustering.cost_basis import (
    CostBasisEntry,
    WalletCostBasis,
    track_acquisition_price,
    get_wallet_realized_value,
    compute_wallet_realized_cap,
    get_weighted_average_cost_basis,
    get_total_btc_in_cluster,
    save_cost_basis_to_db,
    load_cost_basis_from_db,
)
from scripts.clustering.migrate_cost_basis import (
    compute_wallet_realized_cap_from_db,
    get_cluster_realized_value_from_db,
)


def filter_coinjoins(
    transactions: list[dict],
    threshold: float = 0.7,
) -> list[dict]:
    """Filter CoinJoin transactions from a list.

    Removes transactions identified as CoinJoins with confidence above threshold.
    Use this before whale detection to improve signal accuracy.

    Args:
        transactions: List of transaction dictionaries
        threshold: Minimum confidence to filter (default: 0.7)

    Returns:
        List of transactions with CoinJoins removed

    Example:
        >>> clean_txs = filter_coinjoins(transactions)
        >>> print(f"Filtered {len(transactions) - len(clean_txs)} CoinJoins")
    """
    filtered = []

    for tx in transactions:
        result = detect_coinjoin(tx)
        if not (result.is_coinjoin and result.confidence >= threshold):
            filtered.append(tx)

    return filtered


# Public API exports
__all__ = [
    # Union-Find
    "UnionFind",
    # Address Clustering
    "AddressCluster",
    "cluster_addresses",
    "get_cluster_stats",
    "get_cluster_for_address",
    "save_cluster",
    # CoinJoin Detection
    "CoinJoinResult",
    "detect_coinjoin",
    "is_coinjoin",
    "filter_coinjoins",
    "save_coinjoin_result",
    # Change Detection
    "ChangeDetectionResult",
    "detect_change_outputs",
    "get_likely_change_address",
    # Cost Basis (Wallet-Level)
    "CostBasisEntry",
    "WalletCostBasis",
    "track_acquisition_price",
    "get_wallet_realized_value",
    "compute_wallet_realized_cap",
    "get_weighted_average_cost_basis",
    "get_total_btc_in_cluster",
    "save_cost_basis_to_db",
    "load_cost_basis_from_db",
    # Database-backed Cost Basis
    "compute_wallet_realized_cap_from_db",
    "get_cluster_realized_value_from_db",
]
