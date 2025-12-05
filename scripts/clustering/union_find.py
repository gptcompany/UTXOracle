"""Union-Find (Disjoint Set) data structure for address clustering.

Implements Union-Find with path compression and union by rank for
O(α(n)) amortized time complexity per operation, where α is the
inverse Ackermann function (effectively constant for practical n).

Reference: Cormen et al., "Introduction to Algorithms" (Chapter 21)
"""

from __future__ import annotations

from collections import defaultdict


class UnionFind:
    """Disjoint set data structure optimized for address clustering.

    Supports string keys (Bitcoin addresses) and provides efficient
    union, find, and cluster enumeration operations.

    Example:
        >>> uf = UnionFind()
        >>> uf.union("addr1", "addr2")
        >>> uf.union("addr2", "addr3")
        >>> uf.connected("addr1", "addr3")
        True
        >>> uf.get_clusters()
        [{'addr1', 'addr2', 'addr3'}]
    """

    def __init__(self) -> None:
        """Initialize empty Union-Find structure."""
        self._parent: dict[str, str] = {}
        self._rank: dict[str, int] = defaultdict(int)

    def find(self, x: str) -> str:
        """Find root of element with path compression.

        Args:
            x: Element to find root for

        Returns:
            Root representative of the set containing x
        """
        if x not in self._parent:
            self._parent[x] = x
            return x

        # Path compression: make every node point directly to root
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, x: str, y: str) -> None:
        """Union sets containing x and y using union by rank.

        Args:
            x: First element
            y: Second element
        """
        root_x = self.find(x)
        root_y = self.find(y)

        if root_x == root_y:
            return  # Already in same set

        # Union by rank: attach smaller tree under larger tree
        if self._rank[root_x] < self._rank[root_y]:
            self._parent[root_x] = root_y
        elif self._rank[root_x] > self._rank[root_y]:
            self._parent[root_y] = root_x
        else:
            self._parent[root_y] = root_x
            self._rank[root_x] += 1

    def connected(self, x: str, y: str) -> bool:
        """Check if two elements are in the same set.

        Args:
            x: First element
            y: Second element

        Returns:
            True if x and y are in the same set, False otherwise
        """
        # Elements not yet added are not connected
        if x not in self._parent or y not in self._parent:
            return False
        return self.find(x) == self.find(y)

    def get_clusters(self) -> list[set[str]]:
        """Get all disjoint sets as list of sets.

        Returns:
            List of sets, each containing elements in the same cluster
        """
        clusters: dict[str, set[str]] = defaultdict(set)

        for element in self._parent:
            root = self.find(element)
            clusters[root].add(element)

        return list(clusters.values())

    def __len__(self) -> int:
        """Return number of elements tracked."""
        return len(self._parent)

    def cluster_count(self) -> int:
        """Return number of distinct clusters."""
        return len(self.get_clusters())
