"""Per-recording analysis disk cache (cache.content_key + load_or_compute)."""
import numpy as np

from maskviewer.analysis import cache


def _stack():
    L = np.zeros((3, 20, 20), np.int32)
    L[:, 2:8, 2:8] = 1
    return L


def test_content_key_stable_and_sensitive():
    L = _stack()
    k = cache.content_key("t", L, n=3)
    assert k == cache.content_key("t", L, n=3)           # deterministic
    L2 = L.copy(); L2[0, 15, 15] = 2
    assert k != cache.content_key("t", L2, n=3)          # mask content changes the key
    assert k != cache.content_key("t", L, n=4)           # params change the key
    assert k != cache.content_key("u", L, n=3)           # name change


def test_load_or_compute_runs_once(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "cache_dir", lambda: str(tmp_path))
    calls = []

    def compute():
        calls.append(1)
        return {"v": 42, "arr": np.arange(5)}

    r1 = cache.load_or_compute("k1", compute)
    r2 = cache.load_or_compute("k1", compute)            # served from the cache file
    assert len(calls) == 1                               # computed exactly once
    assert r1["v"] == r2["v"] == 42
    assert np.array_equal(r1["arr"], r2["arr"])
    # a different key recomputes
    cache.load_or_compute("k2", compute)
    assert len(calls) == 2
