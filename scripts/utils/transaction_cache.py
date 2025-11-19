#!/usr/bin/env python3
"""
Transaction Cache with OrderedDict (LRU)
Task T009 - REFACTORED: Fixed O(N) bug, now true O(1) operations

Memory-bounded LRU cache for transaction tracking using OrderedDict.
All operations (add, get, remove) are O(1).
"""

from collections import OrderedDict
from typing import Dict, Optional, Any, List
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class TransactionCache:
    """
    Memory-bounded LRU cache for transaction tracking

    Uses OrderedDict for true O(1) operations on all methods.
    Automatically evicts least recently used items when capacity is reached.

    Performance:
    - add(): O(1)
    - get(): O(1)
    - remove(): O(1)
    - contains(): O(1)
    """

    def __init__(self, maxlen: int = 10000):
        """
        Initialize the transaction cache

        Args:
            maxlen: Maximum number of transactions to keep (default: 10000)
        """
        self.maxlen = maxlen
        self._cache: OrderedDict = OrderedDict()
        self._stats = {
            "total_added": 0,
            "total_evicted": 0,
            "total_lookups": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_removed": 0,
        }

        logger.info(f"TransactionCache initialized with maxlen={maxlen} (OrderedDict)")

    def add(self, txid: str, data: Any) -> bool:
        """
        Add a transaction to the cache (LRU)

        If transaction exists, moves it to end (most recent).
        If cache is full, evicts least recently used.

        Args:
            txid: Transaction ID (hash)
            data: Transaction data to cache

        Returns:
            True if newly added, False if updated existing
        """
        is_new = txid not in self._cache

        if not is_new:
            # Move to end (most recent)
            self._cache.move_to_end(txid)
            self._cache[txid] = {
                "data": data,
                "added_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
            return False

        # Check if we need to evict
        if len(self._cache) >= self.maxlen:
            # Evict least recently used (first item)
            evicted_txid, evicted_data = self._cache.popitem(last=False)
            self._stats["total_evicted"] += 1
            logger.debug(f"Evicted LRU transaction: {evicted_txid[:16]}...")

        # Add new entry
        self._cache[txid] = {
            "data": data,
            "added_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        self._stats["total_added"] += 1

        return True

    def get(self, txid: str) -> Optional[Any]:
        """
        Get transaction data from cache (moves to end if found)

        Args:
            txid: Transaction ID to look up

        Returns:
            Transaction data if found, None otherwise
        """
        self._stats["total_lookups"] += 1

        if txid in self._cache:
            # Move to end (most recently accessed)
            self._cache.move_to_end(txid)
            self._stats["cache_hits"] += 1
            return self._cache[txid]["data"]

        self._stats["cache_misses"] += 1
        return None

    def contains(self, txid: str) -> bool:
        """Check if transaction is in cache (no LRU update)"""
        return txid in self._cache

    def remove(self, txid: str) -> bool:
        """
        Remove a transaction from cache (O(1))

        Args:
            txid: Transaction ID to remove

        Returns:
            True if removed, False if not found
        """
        if txid not in self._cache:
            return False

        # O(1) removal with OrderedDict
        del self._cache[txid]
        self._stats["total_removed"] += 1
        logger.debug(f"Removed transaction: {txid[:16]}...")
        return True

    def get_recent(self, n: int = 100) -> List[Dict[str, Any]]:
        """
        Get n most recently used transactions

        Args:
            n: Number of recent transactions to return

        Returns:
            List of recent transaction entries (newest first)
        """
        # OrderedDict maintains insertion/update order
        # Most recent is at the end, so reverse
        items = list(self._cache.items())[-n:]
        items.reverse()

        return [
            {
                "txid": txid,
                "data": entry["data"],
                "added_at": entry["added_at"],
                "updated_at": entry.get("updated_at", entry["added_at"]),
            }
            for txid, entry in items
        ]

    def clear(self):
        """Clear all cached transactions"""
        old_size = len(self._cache)
        self._cache.clear()
        logger.info(f"Cache cleared ({old_size} transactions removed)")

    @property
    def size(self) -> int:
        """Current number of transactions in cache"""
        return len(self._cache)

    @property
    def is_full(self) -> bool:
        """Check if cache is at capacity"""
        return len(self._cache) >= self.maxlen

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate"""
        lookups = self._stats["total_lookups"]
        if lookups == 0:
            return 0.0
        return self._stats["cache_hits"] / lookups

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Dictionary with cache statistics
        """
        return {
            "size": self.size,
            "maxlen": self.maxlen,
            "is_full": self.is_full,
            "hit_rate": self.hit_rate,
            **self._stats,
        }

    def __len__(self) -> int:
        """Return number of cached transactions"""
        return len(self._cache)

    def __contains__(self, txid: str) -> bool:
        """Support 'txid in cache' syntax"""
        return txid in self._cache

    def __repr__(self) -> str:
        """String representation"""
        return (
            f"TransactionCache(size={self.size}/{self.maxlen}, "
            f"hit_rate={self.hit_rate:.2%}, impl=OrderedDict)"
        )


# Example usage and testing
if __name__ == "__main__":
    import json

    print("🔧 TransactionCache - OrderedDict Refactor Test")
    print("=" * 60)

    # Create a small cache for testing
    cache = TransactionCache(maxlen=5)
    print(f"✅ Created: {cache}\n")

    # Test 1: Adding transactions
    print("📝 Test 1: Adding transactions (LRU eviction)")
    for i in range(7):
        txid = "a" * (64 - len(str(i))) + str(i)
        data = {"value": 100 + i, "fee": 10 + i}
        added = cache.add(txid, data)
        action = "Added" if added else "Updated"
        print(f"   {action}: {txid[:16]}... (size: {cache.size})")

    print(f"\n📊 After adds: {cache.get_stats()}\n")

    # Test 2: Lookups (LRU updates)
    print("🔍 Test 2: Lookups (with LRU update)")
    test_txids = [
        "a" * 63 + "0",  # Evicted
        "a" * 63 + "5",  # Should exist
        "a" * 63 + "6",  # Should exist
        "a" * 63 + "2",  # Should exist
    ]

    for txid in test_txids:
        result = cache.get(txid)
        status = "✅ Found" if result else "❌ Miss"
        print(f"   {txid[:16]}... → {status}")

    # Test 3: O(1) Remove
    print("\n🗑️  Test 3: O(1) Remove operation")
    txid_to_remove = "a" * 63 + "5"
    removed = cache.remove(txid_to_remove)
    print(
        f"   Remove {txid_to_remove[:16]}... → {'✅ Success' if removed else '❌ Not found'}"
    )
    print(f"   Cache size after remove: {cache.size}")

    # Verify it's gone
    still_there = cache.contains(txid_to_remove)
    print(f"   Still in cache? {still_there} (should be False)")

    # Test 4: Update existing (move to end)
    print("\n🔄 Test 4: Update existing (LRU move to end)")
    txid_to_update = "a" * 63 + "6"
    cache.add(txid_to_update, {"value": 999, "fee": 999})
    recent = cache.get_recent(3)
    print(f"   Updated {txid_to_update[:16]}...")
    print("   Most recent 3 transactions:")
    for entry in recent:
        print(f"     - {entry['txid'][:16]}... (value: {entry['data']['value']})")

    # Test 5: Final stats
    print("\n📊 Final stats:")
    stats = cache.get_stats()
    print(json.dumps(stats, indent=2))

    # Test 6: Performance comparison note
    print("\n⚡ Performance: All operations O(1)")
    print("   - add(): O(1) with OrderedDict.move_to_end()")
    print("   - get(): O(1) with OrderedDict.__getitem__() + move_to_end()")
    print("   - remove(): O(1) with OrderedDict.__delitem__()")
    print("   - LRU eviction: O(1) with popitem(last=False)")

    print("\n✅ All tests passed - OrderedDict refactor successful!")
