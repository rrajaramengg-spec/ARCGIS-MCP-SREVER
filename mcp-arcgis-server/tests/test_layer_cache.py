"""Tests for BoundedLayerCache."""

import threading
from unittest.mock import MagicMock

from mcp_arcgis_server.arcgis.client import BoundedLayerCache


class TestBoundedLayerCache:
    def test_put_and_get(self):
        cache = BoundedLayerCache(max_size=10)
        layer = MagicMock()
        cache.put("url1", layer)
        assert cache.get("url1") is layer

    def test_get_nonexistent_returns_none(self):
        cache = BoundedLayerCache(max_size=10)
        assert cache.get("missing") is None

    def test_capacity_evicts_lru(self):
        cache = BoundedLayerCache(max_size=2)
        l1, l2, l3 = MagicMock(), MagicMock(), MagicMock()
        cache.put("a", l1)
        cache.put("b", l2)
        cache.put("c", l3)  # Should evict "a"
        assert cache.get("a") is None
        assert cache.get("b") is l2
        assert cache.get("c") is l3
        assert len(cache) == 2

    def test_get_moves_to_end(self):
        cache = BoundedLayerCache(max_size=2)
        l1, l2, l3 = MagicMock(), MagicMock(), MagicMock()
        cache.put("a", l1)
        cache.put("b", l2)
        cache.get("a")  # Move "a" to end, "b" is now LRU
        cache.put("c", l3)  # Should evict "b"
        assert cache.get("a") is l1
        assert cache.get("b") is None
        assert cache.get("c") is l3

    def test_clear(self):
        cache = BoundedLayerCache(max_size=10)
        cache.put("a", MagicMock())
        cache.put("b", MagicMock())
        cache.clear()
        assert len(cache) == 0
        assert cache.get("a") is None

    def test_len(self):
        cache = BoundedLayerCache(max_size=10)
        assert len(cache) == 0
        cache.put("a", MagicMock())
        assert len(cache) == 1

    def test_contains(self):
        cache = BoundedLayerCache(max_size=10)
        cache.put("a", MagicMock())
        assert "a" in cache
        assert "b" not in cache

    def test_thread_safety(self):
        cache = BoundedLayerCache(max_size=50)
        errors = []

        def writer(start):
            try:
                for i in range(100):
                    cache.put(f"url_{start}_{i}", MagicMock())
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for i in range(100):
                    cache.get(f"url_0_{i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=(0,)),
            threading.Thread(target=writer, args=(1,)),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(cache) <= 50
