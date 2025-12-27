"""Address Clustering using Multi-Input Heuristic.

Implements the Multi-Input Heuristic (MIH): addresses that appear together
as inputs in the same transaction are controlled by the same entity.

This is one of the most reliable clustering heuristics, based on the fact
that only the owner of all inputs can sign a transaction.

Reference: Meiklejohn et al. (2013) "A Fistful of Bitcoins"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.clustering.union_find import UnionFind


@dataclass
class AddressCluster:
    """Represents a cluster of addresses belonging to the same entity.

    Attributes:
        cluster_id: Unique identifier (typically root address)
        addresses: Set of addresses in this cluster
        total_balance: Combined balance (requires UTXO lookup)
        tx_count: Number of transactions involving cluster addresses
        first_seen: Timestamp of first observed transaction
        last_seen: Timestamp of most recent transaction
        is_exchange_likely: Heuristic flag for exchange-like behavior
        label: Optional user-assigned or inferred label
    """

    cluster_id: str
    addresses: set[str] = field(default_factory=set)
    total_balance: float = 0.0
    tx_count: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    is_exchange_likely: bool = False
    label: str | None = None


def cluster_addresses(uf: UnionFind, input_addresses: list[str]) -> None:
    """Cluster addresses that appear together in a transaction's inputs.

    Implements the Multi-Input Heuristic: all input addresses in the same
    transaction are assumed to be controlled by the same entity.

    Args:
        uf: UnionFind data structure to update
        input_addresses: List of addresses from transaction inputs

    Example:
        >>> uf = UnionFind()
        >>> cluster_addresses(uf, ["addr1", "addr2", "addr3"])
        >>> uf.connected("addr1", "addr3")
        True
    """
    if len(input_addresses) < 1:
        return

    if len(input_addresses) == 1:
        # Single-input tx: just add to UnionFind (creates singleton)
        uf.find(input_addresses[0])
        return

    # Union all input addresses together
    first_addr = input_addresses[0]
    for addr in input_addresses[1:]:
        uf.union(first_addr, addr)


def get_cluster_stats(uf: UnionFind) -> dict:
    """Get statistics about current clustering state.

    Args:
        uf: UnionFind data structure

    Returns:
        Dictionary with clustering statistics:
        - cluster_count: Number of distinct clusters
        - total_addresses: Total addresses tracked
        - max_cluster_size: Size of largest cluster
        - min_cluster_size: Size of smallest cluster
        - avg_cluster_size: Average cluster size
    """
    clusters = uf.get_clusters()

    if not clusters:
        return {
            "cluster_count": 0,
            "total_addresses": 0,
            "max_cluster_size": 0,
            "min_cluster_size": 0,
            "avg_cluster_size": 0.0,
        }

    sizes = [len(c) for c in clusters]

    return {
        "cluster_count": len(clusters),
        "total_addresses": sum(sizes),
        "max_cluster_size": max(sizes),
        "min_cluster_size": min(sizes),
        "avg_cluster_size": sum(sizes) / len(clusters),
    }


def save_cluster(
    uf: UnionFind,
    db_path: str = str(UTXORACLE_DB_PATH),
) -> int:
    """Save all clusters to database.

    Args:
        uf: UnionFind data structure with clusters
        db_path: Path to DuckDB database

    Returns:
        Number of addresses saved
    """
    import duckdb

from scripts.config import UTXORACLE_DB_PATH
    from datetime import datetime

    clusters = uf.get_clusters()
    if not clusters:
        return 0

    conn = duckdb.connect(db_path)
    now = datetime.now()
    count = 0

    for cluster_set in clusters:
        cluster_id = uf.find(next(iter(cluster_set)))

        for address in cluster_set:
            try:
                conn.execute(
                    """
                    INSERT INTO address_clusters (address, cluster_id, first_seen, last_seen)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (address) DO UPDATE SET
                        cluster_id = EXCLUDED.cluster_id,
                        last_seen = EXCLUDED.last_seen
                    """,
                    [address, cluster_id, now, now],
                )
                count += 1
            except Exception:
                # Skip duplicates or errors
                pass

    conn.close()
    return count


def get_cluster_for_address(uf: UnionFind, address: str) -> AddressCluster | None:
    """Get the cluster containing a specific address.

    Args:
        uf: UnionFind data structure
        address: Address to look up

    Returns:
        AddressCluster if address is tracked, None otherwise
    """
    if address not in uf._parent:
        return None

    cluster_id = uf.find(address)
    clusters = uf.get_clusters()

    for cluster_set in clusters:
        if address in cluster_set:
            return AddressCluster(
                cluster_id=cluster_id,
                addresses=cluster_set,
            )

    return None
