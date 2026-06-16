"""Cell-Info precompute + per-cell caching (so switching cells is instant).

Headless (QT offscreen): build the panel, give it a recording context, and
check that `precompute_all` caches every cell, that switching to a cell is then
a cache *hit* (same object, no recompute), and that the cache invalidates when
the recording or the enabled-metric set changes.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

pytest.importorskip("PyQt5")
from PyQt5 import QtWidgets  # noqa: E402
from maskviewer.analysis import cell_metrics  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _labels():
    """3 cells over 6 frames (two drift, one is static)."""
    T, H, W = 6, 40, 40
    lab = np.zeros((T, H, W), np.int32)
    for t in range(T):
        lab[t, 5:12, 5 + t:12 + t] = 1
        lab[t, 20:27, 20:27] = 2
        lab[t, 30:36, 2 + t:8 + t] = 3
    return lab


def _panel():
    from maskviewer.gui.panels.cell_info import CellInfoPanel
    p = CellInfoPanel()
    p.set_available(["DIC"], 0.5)
    p._enabled = set(cell_metrics.DEFAULT_PLOT_METRICS)   # deterministic (ignore QSettings)
    return p


def test_precompute_caches_all_cells(app):
    p, lab = _panel(), _labels()
    p.set_context(lab, 0.5, 10.0)
    assert p._cache == {}
    p.precompute_all()                          # run_async is None -> runs synchronously
    assert set(p._cache) == {1, 2, 3}
    assert p._precomputed
    before = p._cache[2]
    p.set_cell(2, lab, 0.5, 10.0, recording=None)
    assert p._cft is before                     # served from cache, not recomputed
    assert p.cell_id == 2


def test_metric_change_invalidates_cache(app):
    p, lab = _panel(), _labels()
    p.set_context(lab, 0.5, 10.0)
    p.precompute_all()
    assert p._precomputed and p._cache
    p.set_metric_enabled("solidity", True)      # enabling a metric makes cached cfts stale
    assert not p._precomputed
    assert p._cache == {}


def test_new_recording_invalidates_cache(app):
    p, lab = _panel(), _labels()
    p.set_context(lab, 0.5, 10.0)
    p.precompute_all()
    assert p._cache
    p.set_context(_labels(), 0.5, 10.0)         # different labels object -> drop cache
    assert p._cache == {}
    assert not p._precomputed


def test_set_cell_memoises_without_precompute(app):
    p, lab = _panel(), _labels()
    p.set_cell(1, lab, 0.5, 10.0, recording=None)
    first = p._cft
    assert 1 in p._cache
    p.set_cell(2, lab, 0.5, 10.0, recording=None)
    p.set_cell(1, lab, 0.5, 10.0, recording=None)   # revisit -> cache hit
    assert p._cft is first
