"""
TTL cache for BigQuery query results.

Why this exists:
- Every dashboard render fires 4+ queries. Without caching, refreshing the page
  re-bills BigQuery each time. For a 30-day window on a busy dataset, one full
  dashboard render can scan 10-50 GB. At ~$5/TB this adds up fast.
- A 5-minute TTL is the right default for PM workflows. PMs explore for a few
  minutes per session; data freshness in 5-minute increments is fine for
  decision-making.
- In-memory (not Redis) because this is a single-process internal tool. Keep
  ops simple. If we ever go multi-process, swap the dict for Redis -- the
  interface is identical.

Cache stats are exposed via /api/cache/stats so we can see hit rate during
development. If hit rate stays below 30%, the TTL is wrong (or the cache is
useless and we should remove it).
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class _Entry:
    value: Any
    expires_at: float


@dataclass
class _Stats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    entries: int = 0


class TTLCache:
    """Thread-safe TTL cache with size cap and LRU-ish eviction.

    We do simple oldest-first eviction when over max_size, not true LRU --
    but for a few hundred entries the difference is invisible.
    """

    def __init__(self, default_ttl_seconds: int = 300, max_size: int = 500):
        self._store: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl_seconds
        self._max_size = max_size
        self._stats = _Stats()

    @staticmethod
    def make_key(sql: str, params: Optional[dict] = None) -> str:
        """Deterministic key for a (sql, params) pair.

        We hash because params can include long IN-lists. Storing the raw
        SQL+params as the key would bloat memory.
        """
        # Sort keys so {"a":1, "b":2} and {"b":2, "a":1} hash the same.
        # default=str handles dates/Decimals from BQ -- they don't appear in
        # cache keys today but cheap insurance.
        params_str = json.dumps(params or {}, sort_keys=True, default=str)
        blob = (sql + "||" + params_str).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._stats.misses += 1
                return None
            if time.time() >= entry.expires_at:
                # Expired -- delete and treat as miss
                del self._store[key]
                self._stats.evictions += 1
                self._stats.misses += 1
                return None
            self._stats.hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        with self._lock:
            self._store[key] = _Entry(value=value, expires_at=time.time() + ttl)
            self._evict_if_needed()
            self._stats.entries = len(self._store)

    def _evict_if_needed(self) -> None:
        # Holds _lock from caller.
        if len(self._store) <= self._max_size:
            return
        # Evict oldest 10% so we don't thrash on every set.
        to_evict = max(1, len(self._store) // 10)
        # Sort by expires_at ascending; the most-expired (soonest) go first.
        oldest = sorted(self._store.items(), key=lambda kv: kv[1].expires_at)[:to_evict]
        for k, _ in oldest:
            del self._store[k]
        self._stats.evictions += to_evict

    def invalidate_all(self) -> None:
        """Used when /api/connect changes the active dataset."""
        with self._lock:
            self._store.clear()
            self._stats.entries = 0

    def stats(self) -> dict:
        with self._lock:
            total = self._stats.hits + self._stats.misses
            hit_rate = (self._stats.hits / total) if total > 0 else 0.0
            return {
                "hits": self._stats.hits,
                "misses": self._stats.misses,
                "evictions": self._stats.evictions,
                "entries": self._stats.entries,
                "hit_rate": round(hit_rate, 3),
            }


# Module-level singleton. Single process = single cache.
_cache = TTLCache(default_ttl_seconds=300, max_size=500)


def cached_query(
    sql: str,
    params: Optional[dict],
    runner: Callable[[str, Optional[dict]], list[dict]],
    ttl_seconds: Optional[int] = None,
) -> list[dict]:
    """Wrap a query runner with caching. Returns cached value if fresh, else
    runs the query and stores the result."""
    key = TTLCache.make_key(sql, params)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    result = runner(sql, params)
    _cache.set(key, result, ttl_seconds=ttl_seconds)
    return result


def invalidate_cache() -> None:
    _cache.invalidate_all()


def cache_stats() -> dict:
    return _cache.stats()
