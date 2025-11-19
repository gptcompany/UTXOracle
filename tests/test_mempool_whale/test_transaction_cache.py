#!/usr/bin/env python3
"""
Tests for TransactionCache Utility (OrderedDict implementation)
Task T009 - Test Coverage for O(1) LRU Cache
"""

from datetime import datetime, timezone
from scripts.utils.transaction_cache import TransactionCache


class TestTransactionCacheBasicOperations:
    """Test basic cache operations"""

    def test_cache_initialization(self):
        """Cache should initialize with correct maxlen"""
        cache = TransactionCache(maxlen=1000)

        assert cache.maxlen == 1000
        assert cache.size == 0
        assert cache.is_full is False

    def test_add_new_transaction(self):
        """Adding new transaction should return True"""
        cache = TransactionCache(maxlen=10)
        txid = "a" * 64
        data = {"value": 100, "fee": 10}

        result = cache.add(txid, data)

        assert result is True  # Newly added
        assert cache.size == 1
        assert cache.contains(txid)

    def test_add_existing_transaction_updates(self):
        """Adding existing transaction should update and return False"""
        cache = TransactionCache(maxlen=10)
        txid = "a" * 64
        data1 = {"value": 100, "fee": 10}
        data2 = {"value": 200, "fee": 20}

        cache.add(txid, data1)
        result = cache.add(txid, data2)

        assert result is False  # Updated existing
        assert cache.size == 1
        retrieved = cache.get(txid)
        assert retrieved["value"] == 200  # Updated value

    def test_get_existing_transaction(self):
        """Getting existing transaction should return data"""
        cache = TransactionCache(maxlen=10)
        txid = "a" * 64
        data = {"value": 100, "fee": 10}

        cache.add(txid, data)
        result = cache.get(txid)

        assert result is not None
        assert result["value"] == 100

    def test_get_nonexistent_transaction(self):
        """Getting nonexistent transaction should return None"""
        cache = TransactionCache(maxlen=10)
        result = cache.get("nonexistent")

        assert result is None

    def test_contains_existing_transaction(self):
        """Contains should return True for existing transaction"""
        cache = TransactionCache(maxlen=10)
        txid = "a" * 64

        cache.add(txid, {"value": 100})
        assert cache.contains(txid) is True
        assert txid in cache  # Test __contains__

    def test_contains_nonexistent_transaction(self):
        """Contains should return False for nonexistent transaction"""
        cache = TransactionCache(maxlen=10)
        assert cache.contains("nonexistent") is False
        assert "nonexistent" not in cache  # Test __contains__


class TestTransactionCacheLRUBehavior:
    """Test LRU (Least Recently Used) eviction"""

    def test_lru_eviction_when_full(self):
        """Oldest item should be evicted when cache is full"""
        cache = TransactionCache(maxlen=3)

        # Add 3 transactions (fill cache)
        cache.add("tx1", {"value": 1})
        cache.add("tx2", {"value": 2})
        cache.add("tx3", {"value": 3})

        assert cache.is_full is True
        assert cache.size == 3

        # Add 4th transaction (should evict tx1)
        cache.add("tx4", {"value": 4})

        assert cache.size == 3  # Still at maxlen
        assert "tx1" not in cache  # Oldest evicted
        assert "tx2" in cache
        assert "tx3" in cache
        assert "tx4" in cache

    def test_lru_access_updates_order(self):
        """Accessing a transaction should move it to end (most recent)"""
        cache = TransactionCache(maxlen=3)

        cache.add("tx1", {"value": 1})
        cache.add("tx2", {"value": 2})
        cache.add("tx3", {"value": 3})

        # Access tx1 (moves to end)
        cache.get("tx1")

        # Add tx4 (should evict tx2, not tx1)
        cache.add("tx4", {"value": 4})

        assert "tx1" in cache  # Accessed, so not evicted
        assert "tx2" not in cache  # Evicted (least recently used)
        assert "tx3" in cache
        assert "tx4" in cache

    def test_lru_update_moves_to_end(self):
        """Updating a transaction should move it to end"""
        cache = TransactionCache(maxlen=3)

        cache.add("tx1", {"value": 1})
        cache.add("tx2", {"value": 2})
        cache.add("tx3", {"value": 3})

        # Update tx1 (moves to end)
        cache.add("tx1", {"value": 100})

        # Add tx4 (should evict tx2, not tx1)
        cache.add("tx4", {"value": 4})

        assert "tx1" in cache  # Updated, so not evicted
        assert "tx2" not in cache  # Evicted
        assert "tx3" in cache
        assert "tx4" in cache


class TestTransactionCacheRemove:
    """Test O(1) remove operation"""

    def test_remove_existing_transaction(self):
        """Removing existing transaction should return True"""
        cache = TransactionCache(maxlen=10)
        txid = "a" * 64

        cache.add(txid, {"value": 100})
        result = cache.remove(txid)

        assert result is True
        assert txid not in cache
        assert cache.size == 0

    def test_remove_nonexistent_transaction(self):
        """Removing nonexistent transaction should return False"""
        cache = TransactionCache(maxlen=10)
        result = cache.remove("nonexistent")

        assert result is False

    def test_remove_multiple_transactions(self):
        """Removing multiple transactions should work correctly"""
        cache = TransactionCache(maxlen=10)

        cache.add("tx1", {"value": 1})
        cache.add("tx2", {"value": 2})
        cache.add("tx3", {"value": 3})

        assert cache.size == 3

        cache.remove("tx2")
        assert cache.size == 2
        assert "tx2" not in cache

        cache.remove("tx1")
        assert cache.size == 1
        assert "tx1" not in cache

        cache.remove("tx3")
        assert cache.size == 0
        assert "tx3" not in cache


class TestTransactionCacheStats:
    """Test cache statistics tracking"""

    def test_stats_total_added(self):
        """Stats should track total additions"""
        cache = TransactionCache(maxlen=10)

        cache.add("tx1", {"value": 1})
        cache.add("tx2", {"value": 2})
        cache.add("tx1", {"value": 100})  # Update, not new add

        stats = cache.get_stats()
        assert stats["total_added"] == 2  # Only new additions count

    def test_stats_total_evicted(self):
        """Stats should track total evictions"""
        cache = TransactionCache(maxlen=2)

        cache.add("tx1", {"value": 1})
        cache.add("tx2", {"value": 2})
        cache.add("tx3", {"value": 3})  # Evicts tx1
        cache.add("tx4", {"value": 4})  # Evicts tx2

        stats = cache.get_stats()
        assert stats["total_evicted"] == 2

    def test_stats_cache_hits_and_misses(self):
        """Stats should track cache hits and misses"""
        cache = TransactionCache(maxlen=10)

        cache.add("tx1", {"value": 1})

        cache.get("tx1")  # Hit
        cache.get("tx2")  # Miss
        cache.get("tx1")  # Hit
        cache.get("tx3")  # Miss

        stats = cache.get_stats()
        assert stats["cache_hits"] == 2
        assert stats["cache_misses"] == 2
        assert stats["total_lookups"] == 4

    def test_stats_hit_rate(self):
        """Stats should calculate hit rate correctly"""
        cache = TransactionCache(maxlen=10)

        cache.add("tx1", {"value": 1})

        cache.get("tx1")  # Hit
        cache.get("tx2")  # Miss
        cache.get("tx1")  # Hit
        cache.get("tx3")  # Miss

        assert cache.hit_rate == 0.5  # 2 hits / 4 lookups

    def test_stats_hit_rate_zero_lookups(self):
        """Hit rate should be 0.0 with no lookups"""
        cache = TransactionCache(maxlen=10)
        assert cache.hit_rate == 0.0

    def test_stats_total_removed(self):
        """Stats should track total removals"""
        cache = TransactionCache(maxlen=10)

        cache.add("tx1", {"value": 1})
        cache.add("tx2", {"value": 2})

        cache.remove("tx1")
        cache.remove("tx2")

        stats = cache.get_stats()
        assert stats["total_removed"] == 2


class TestTransactionCacheGetRecent:
    """Test get_recent functionality"""

    def test_get_recent_returns_most_recent(self):
        """get_recent should return most recently used transactions"""
        cache = TransactionCache(maxlen=10)

        cache.add("tx1", {"value": 1})
        cache.add("tx2", {"value": 2})
        cache.add("tx3", {"value": 3})

        recent = cache.get_recent(n=2)

        assert len(recent) == 2
        assert recent[0]["txid"] == "tx3"  # Most recent first
        assert recent[1]["txid"] == "tx2"

    def test_get_recent_respects_access_order(self):
        """get_recent should respect LRU access order"""
        cache = TransactionCache(maxlen=10)

        cache.add("tx1", {"value": 1})
        cache.add("tx2", {"value": 2})
        cache.add("tx3", {"value": 3})

        # Access tx1 (moves to end)
        cache.get("tx1")

        recent = cache.get_recent(n=3)

        assert recent[0]["txid"] == "tx1"  # Most recent (just accessed)
        assert recent[1]["txid"] == "tx3"
        assert recent[2]["txid"] == "tx2"

    def test_get_recent_with_n_larger_than_cache(self):
        """get_recent should return all items if n > cache size"""
        cache = TransactionCache(maxlen=10)

        cache.add("tx1", {"value": 1})
        cache.add("tx2", {"value": 2})

        recent = cache.get_recent(n=100)

        assert len(recent) == 2  # Only 2 items in cache


class TestTransactionCacheClear:
    """Test clear functionality"""

    def test_clear_removes_all_transactions(self):
        """clear should remove all cached transactions"""
        cache = TransactionCache(maxlen=10)

        cache.add("tx1", {"value": 1})
        cache.add("tx2", {"value": 2})
        cache.add("tx3", {"value": 3})

        assert cache.size == 3

        cache.clear()

        assert cache.size == 0
        assert "tx1" not in cache
        assert "tx2" not in cache
        assert "tx3" not in cache


class TestTransactionCachePerformance:
    """Test performance characteristics"""

    def test_add_is_constant_time(self):
        """add() should be O(1) regardless of cache size"""
        import time

        # Test with small cache
        small_cache = TransactionCache(maxlen=100)
        start = time.perf_counter()
        for i in range(100):
            small_cache.add(f"tx{i:064x}", {"value": i})
        small_time = time.perf_counter() - start

        # Test with large cache
        large_cache = TransactionCache(maxlen=10000)
        start = time.perf_counter()
        for i in range(10000):
            large_cache.add(f"tx{i:064x}", {"value": i})
        large_time = time.perf_counter() - start

        # O(1) means large_time should be ~100x small_time, not >>100x
        # Allow 2x margin for overhead
        assert large_time < small_time * 200

    def test_get_is_constant_time(self):
        """get() should be O(1) regardless of cache size"""
        import time

        # Prepare caches
        small_cache = TransactionCache(maxlen=100)
        for i in range(100):
            small_cache.add(f"tx{i:064x}", {"value": i})

        large_cache = TransactionCache(maxlen=10000)
        for i in range(10000):
            large_cache.add(f"tx{i:064x}", {"value": i})

        # Test get on last item (worst case for O(N) implementations)
        start = time.perf_counter()
        for _ in range(1000):
            small_cache.get(f"tx{99:064x}")
        small_time = time.perf_counter() - start

        start = time.perf_counter()
        for _ in range(1000):
            large_cache.get(f"tx{9999:064x}")
        large_time = time.perf_counter() - start

        # O(1) means times should be similar
        # Allow 5x margin for overhead
        assert large_time < small_time * 5

    def test_remove_is_constant_time(self):
        """remove() should be O(1) with OrderedDict"""
        import time

        # Prepare caches
        small_cache = TransactionCache(maxlen=100)
        for i in range(100):
            small_cache.add(f"tx{i:064x}", {"value": i})

        large_cache = TransactionCache(maxlen=10000)
        for i in range(10000):
            large_cache.add(f"tx{i:064x}", {"value": i})

        # Test remove on middle items
        start = time.perf_counter()
        for i in range(50):
            small_cache.remove(f"tx{i:064x}")
        small_time = time.perf_counter() - start

        start = time.perf_counter()
        for i in range(5000):
            large_cache.remove(f"tx{i:064x}")
        large_time = time.perf_counter() - start

        # O(1) means large_time should be ~100x small_time, not >>100x
        # Allow 2x margin for overhead
        assert large_time < small_time * 200


class TestTransactionCacheEdgeCases:
    """Test edge cases"""

    def test_maxlen_one(self):
        """Cache with maxlen=1 should work correctly"""
        cache = TransactionCache(maxlen=1)

        cache.add("tx1", {"value": 1})
        assert cache.size == 1

        cache.add("tx2", {"value": 2})
        assert cache.size == 1
        assert "tx1" not in cache
        assert "tx2" in cache

    def test_add_with_timestamps(self):
        """Cache should store timestamps correctly"""
        cache = TransactionCache(maxlen=10)

        before = datetime.now(timezone.utc)
        cache.add("tx1", {"value": 1})
        after = datetime.now(timezone.utc)

        recent = cache.get_recent(n=1)
        added_at = recent[0]["added_at"]

        assert before <= added_at <= after

    def test_update_changes_updated_at(self):
        """Updating a transaction should change updated_at timestamp"""
        cache = TransactionCache(maxlen=10)

        cache.add("tx1", {"value": 1})
        first_recent = cache.get_recent(n=1)
        first_updated_at = first_recent[0]["updated_at"]

        import time

        time.sleep(0.01)  # Small delay

        cache.add("tx1", {"value": 2})
        second_recent = cache.get_recent(n=1)
        second_updated_at = second_recent[0]["updated_at"]

        assert second_updated_at > first_updated_at


class TestTransactionCacheRepr:
    """Test string representation"""

    def test_repr_includes_key_info(self):
        """__repr__ should include size, maxlen, hit_rate, impl"""
        cache = TransactionCache(maxlen=100)
        cache.add("tx1", {"value": 1})

        repr_str = repr(cache)

        assert "1/100" in repr_str  # size/maxlen
        assert "OrderedDict" in repr_str  # implementation
        assert "hit_rate" in repr_str

    def test_len_returns_size(self):
        """__len__ should return cache size"""
        cache = TransactionCache(maxlen=10)

        cache.add("tx1", {"value": 1})
        cache.add("tx2", {"value": 2})

        assert len(cache) == 2
