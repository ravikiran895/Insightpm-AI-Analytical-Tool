"""Tests for the in-memory TTL cache."""
import time

from app.cache import TTLCache, cached_query


class TestTTLCache:
    def test_set_and_get(self):
        c = TTLCache(default_ttl_seconds=60)
        c.set("k1", ["row1"])
        assert c.get("k1") == ["row1"]

    def test_miss_returns_none(self):
        c = TTLCache()
        assert c.get("nonexistent") is None

    def test_expiry(self):
        c = TTLCache(default_ttl_seconds=1)
        c.set("k1", "value")
        assert c.get("k1") == "value"
        time.sleep(1.1)
        assert c.get("k1") is None  # expired

    def test_make_key_deterministic(self):
        k1 = TTLCache.make_key("SELECT 1", {"a": 1})
        k2 = TTLCache.make_key("SELECT 1", {"a": 1})
        assert k1 == k2

    def test_make_key_param_order_invariant(self):
        # Same params in different dict order should produce same key
        k1 = TTLCache.make_key("SELECT", {"a": 1, "b": 2})
        k2 = TTLCache.make_key("SELECT", {"b": 2, "a": 1})
        assert k1 == k2

    def test_make_key_different_params(self):
        k1 = TTLCache.make_key("SELECT", {"a": 1})
        k2 = TTLCache.make_key("SELECT", {"a": 2})
        assert k1 != k2

    def test_make_key_handles_lists_in_params(self):
        # A common shape: array params for IN UNNEST
        k1 = TTLCache.make_key("SELECT", {"events": ["a", "b", "c"]})
        k2 = TTLCache.make_key("SELECT", {"events": ["a", "b", "c"]})
        assert k1 == k2

    def test_stats_tracking(self):
        c = TTLCache()
        c.set("k", "v")
        c.get("k")  # hit
        c.get("k")  # hit
        c.get("missing")  # miss
        stats = c.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == round(2 / 3, 3)

    def test_eviction_at_size_limit(self):
        c = TTLCache(default_ttl_seconds=60, max_size=10)
        for i in range(20):
            c.set(f"k{i}", f"v{i}")
        # Internal store should be capped
        assert len(c._store) <= 10

    def test_invalidate_all(self):
        c = TTLCache()
        c.set("k1", "v1")
        c.set("k2", "v2")
        c.invalidate_all()
        assert c.get("k1") is None
        assert c.get("k2") is None


class TestCachedQuery:
    def test_runner_called_once_for_same_query(self):
        call_count = [0]

        def runner(sql, params):
            call_count[0] += 1
            return [{"r": call_count[0]}]

        # Use unique SQL so we don't collide with other tests' module-level cache
        sql = "SELECT unique_for_test_runner_called_once"
        r1 = cached_query(sql, {"a": 1}, runner)
        r2 = cached_query(sql, {"a": 1}, runner)
        assert call_count[0] == 1, "runner should be called once, second was a hit"
        assert r1 == r2

    def test_different_params_call_runner_again(self):
        call_count = [0]

        def runner(sql, params):
            call_count[0] += 1
            return [{"call": call_count[0]}]

        sql = "SELECT different_params_test"
        cached_query(sql, {"x": 1}, runner)
        cached_query(sql, {"x": 2}, runner)
        assert call_count[0] == 2
