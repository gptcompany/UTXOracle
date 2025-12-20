"""Wallet-Level Cost Basis Tracking.

Tracks acquisition prices at the wallet (cluster) level to compute accurate
Realized Cap. This fixes the inflation problem where UTXO-level tracking
assigns current prices to internal transfers.

Key insight: When BTC moves between addresses within the same wallet cluster,
the cost basis should NOT be updated to the current price. Only when BTC
enters a new cluster (different entity) should the acquisition price change.

Reference: CheckOnChain/Glassnode methodology for Realized Cap calculation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass
class CostBasisEntry:
    """A single cost basis entry for a wallet cluster.

    Attributes:
        btc_amount: Amount of BTC acquired
        acquisition_price: USD price at time of acquisition
        block_height: Block height when acquired
        timestamp: Timestamp of acquisition
    """

    btc_amount: float
    acquisition_price: float
    block_height: int
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class WalletCostBasis:
    """Container for wallet-level cost basis tracking.

    Stores acquisition history for each cluster, enabling accurate
    Realized Cap calculation that matches industry standards.

    Attributes:
        entries: Mapping of cluster_id to list of acquisition entries
    """

    entries: dict[str, list[CostBasisEntry]] = field(default_factory=dict)

    def get_entries(self, cluster_id: str) -> list[CostBasisEntry]:
        """Get all acquisition entries for a cluster.

        Args:
            cluster_id: Cluster identifier

        Returns:
            List of CostBasisEntry objects for this cluster
        """
        return self.entries.get(cluster_id, [])

    def get_all_clusters(self) -> list[str]:
        """Get all cluster IDs with cost basis data.

        Returns:
            List of cluster IDs
        """
        return list(self.entries.keys())


def track_acquisition_price(
    cost_basis: WalletCostBasis,
    cluster_id: str,
    btc_amount: float,
    acquisition_price: float,
    block_height: int,
    timestamp: datetime | None = None,
) -> None:
    """Record a BTC acquisition for a wallet cluster.

    This should be called when BTC enters a cluster from outside
    (from a different entity). Internal transfers within the same
    cluster should NOT call this function.

    Args:
        cost_basis: WalletCostBasis container to update
        cluster_id: Cluster identifier receiving the BTC
        btc_amount: Amount of BTC acquired (must be > 0)
        acquisition_price: USD price at time of acquisition (must be >= 0)
        block_height: Block height of the acquisition
        timestamp: Optional timestamp (defaults to now)

    Raises:
        ValueError: If btc_amount <= 0 or acquisition_price < 0
    """
    # B1 fix: Validate inputs to match database schema constraints
    if btc_amount <= 0:
        raise ValueError(f"btc_amount must be positive, got {btc_amount}")
    if acquisition_price < 0:
        raise ValueError(
            f"acquisition_price cannot be negative, got {acquisition_price}"
        )

    if cluster_id not in cost_basis.entries:
        cost_basis.entries[cluster_id] = []

    entry = CostBasisEntry(
        btc_amount=btc_amount,
        acquisition_price=acquisition_price,
        block_height=block_height,
        timestamp=timestamp or datetime.now(),
    )
    cost_basis.entries[cluster_id].append(entry)


def get_wallet_realized_value(
    cost_basis: WalletCostBasis,
    cluster_id: str,
) -> float:
    """Calculate the realized value for a wallet cluster.

    The realized value is the sum of (btc_amount * acquisition_price)
    for all acquisitions in this cluster. This uses the ACQUISITION
    price, not the current market price.

    Args:
        cost_basis: WalletCostBasis container
        cluster_id: Cluster identifier

    Returns:
        Total realized value in USD
    """
    entries = cost_basis.get_entries(cluster_id)
    if not entries:
        return 0.0

    return sum(e.btc_amount * e.acquisition_price for e in entries)


def compute_wallet_realized_cap(cost_basis: WalletCostBasis) -> float:
    """Calculate total Realized Cap across all wallet clusters.

    This aggregates the realized value from all tracked clusters
    to produce a network-wide Realized Cap estimate.

    Args:
        cost_basis: WalletCostBasis container

    Returns:
        Total Realized Cap in USD
    """
    total = 0.0
    for cluster_id in cost_basis.get_all_clusters():
        total += get_wallet_realized_value(cost_basis, cluster_id)
    return total


def get_weighted_average_cost_basis(
    cost_basis: WalletCostBasis,
    cluster_id: str,
) -> float:
    """Calculate weighted average cost basis for a cluster.

    The weighted average is: sum(btc * price) / sum(btc)
    This gives the effective per-BTC cost basis for the wallet.

    Args:
        cost_basis: WalletCostBasis container
        cluster_id: Cluster identifier

    Returns:
        Weighted average acquisition price, or 0 if no entries
    """
    entries = cost_basis.get_entries(cluster_id)
    if not entries:
        return 0.0

    total_btc = sum(e.btc_amount for e in entries)
    if total_btc == 0:
        return 0.0

    weighted_sum = sum(e.btc_amount * e.acquisition_price for e in entries)
    return weighted_sum / total_btc


def get_total_btc_in_cluster(
    cost_basis: WalletCostBasis,
    cluster_id: str,
) -> float:
    """Get total BTC amount in a cluster.

    Args:
        cost_basis: WalletCostBasis container
        cluster_id: Cluster identifier

    Returns:
        Total BTC amount
    """
    entries = cost_basis.get_entries(cluster_id)
    return sum(e.btc_amount for e in entries)


def save_cost_basis_to_db(
    cost_basis: WalletCostBasis,
    db_path: str = "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db",
) -> int:
    """Save wallet cost basis entries to database.

    Args:
        cost_basis: WalletCostBasis container
        db_path: Path to DuckDB database

    Returns:
        Number of entries saved
    """
    import duckdb

    count = 0
    conn = duckdb.connect(db_path)

    for cluster_id, entries in cost_basis.entries.items():
        for entry in entries:
            try:
                conn.execute(
                    """
                    INSERT INTO wallet_cost_basis (
                        cluster_id, acquisition_block, btc_amount,
                        acquisition_price, acquisition_timestamp
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (cluster_id, acquisition_block) DO UPDATE SET
                        btc_amount = EXCLUDED.btc_amount,
                        acquisition_price = EXCLUDED.acquisition_price
                    """,
                    [
                        cluster_id,
                        entry.block_height,
                        entry.btc_amount,
                        entry.acquisition_price,
                        entry.timestamp,
                    ],
                )
                count += 1
            except Exception:
                pass

    conn.close()
    return count


def load_cost_basis_from_db(
    db_path: str = "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db",
) -> WalletCostBasis:
    """Load wallet cost basis entries from database.

    Args:
        db_path: Path to DuckDB database

    Returns:
        WalletCostBasis container with loaded entries
    """
    import duckdb

    cost_basis = WalletCostBasis()

    try:
        conn = duckdb.connect(db_path)
        rows = conn.execute(
            """
            SELECT cluster_id, acquisition_block, btc_amount,
                   acquisition_price, acquisition_timestamp
            FROM wallet_cost_basis
            ORDER BY cluster_id, acquisition_block
            """
        ).fetchall()
        conn.close()

        for row in rows:
            cluster_id, block_height, btc_amount, price, timestamp = row
            track_acquisition_price(
                cost_basis,
                cluster_id=cluster_id,
                btc_amount=btc_amount,
                acquisition_price=price,
                block_height=block_height,
                timestamp=timestamp,
            )
    except Exception:
        pass

    return cost_basis
