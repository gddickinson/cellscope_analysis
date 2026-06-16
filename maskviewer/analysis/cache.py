"""Per-recording disk cache for expensive analysis passes (e.g. VAMPIRE shape modes).

Keyed by a fast **content fingerprint** of the label stack (shape, dtype, nonzero
count + a strided byte sample) plus the computation parameters, so it auto-invalidates
when the masks or params change. Stored under ``analysis_out/cache/`` (gitignored).
Failures (unreadable/unwritable cache) degrade gracefully to a recompute.
"""
from __future__ import annotations

import hashlib
import os
import pickle

import numpy as np


def content_key(name: str, labels, **params) -> str:
    """Stable cache key for ``(name, label-stack content, params)``.

    Hashes a strided sample (≈250k elements) + the nonzero count rather than the full
    array, so keying a 2048²×T stack is sub-second yet collision-safe in practice."""
    a = np.ascontiguousarray(labels)
    h = hashlib.blake2b(digest_size=16)
    h.update(f"{name}|{a.shape}|{a.dtype}|{int((a > 0).sum())}".encode())
    flat = a.reshape(-1)
    stride = max(1, flat.size // 250_000)
    h.update(np.ascontiguousarray(flat[::stride]).tobytes())
    h.update(repr(sorted(params.items())).encode())
    return f"{name}_{h.hexdigest()}"


def cache_dir() -> str:
    from ..config import PROJECT_ROOT
    d = os.path.join(PROJECT_ROOT, "analysis_out", "cache")
    os.makedirs(d, exist_ok=True)
    return d


def load_or_compute(key: str, compute):
    """Return the cached result for ``key``; else call ``compute()``, store + return it.

    A corrupt/absent cache file just triggers a recompute; an unwritable cache dir is
    ignored (the result is still returned)."""
    try:
        path = os.path.join(cache_dir(), key + ".pkl")
    except Exception:
        return compute()
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
    result = compute()
    try:
        with open(path, "wb") as f:
            pickle.dump(result, f)
    except Exception:
        pass
    return result
