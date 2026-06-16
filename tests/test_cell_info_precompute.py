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
from PyQt5 import QtCore, QtWidgets  # noqa: E402
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


def _panel(tmp_path):
    from maskviewer.gui.panels.cell_info import CellInfoPanel
    p = CellInfoPanel()
    # Isolate persisted settings to a temp ini so the test never writes the real
    # QSettings (set_metric_enabled / set_auto_precompute would otherwise pollute it).
    p._settings = QtCore.QSettings(str(tmp_path / "viewer.ini"), QtCore.QSettings.IniFormat)
    p.set_available(["DIC"], 0.5)
    p._enabled = set(cell_metrics.DEFAULT_PLOT_METRICS)   # deterministic (ignore QSettings)
    p._auto_precompute = False                            # ditto — don't depend on stored prefs
    return p


def test_precompute_caches_all_cells(app, tmp_path):
    p, lab = _panel(tmp_path), _labels()
    p.set_context(lab, 0.5, 10.0)
    assert p._cache == {}
    p.precompute_all()                          # run_async is None -> runs synchronously
    assert set(p._cache) == {1, 2, 3}
    assert p._precomputed
    before = p._cache[2]
    p.set_cell(2, lab, 0.5, 10.0, recording=None)
    assert p._cft is before                     # served from cache, not recomputed
    assert p.cell_id == 2


def test_metric_change_invalidates_cache(app, tmp_path):
    p, lab = _panel(tmp_path), _labels()
    p.set_context(lab, 0.5, 10.0)
    p.precompute_all()
    assert p._precomputed and p._cache
    p.set_metric_enabled("solidity", True)      # enabling a metric makes cached cfts stale
    assert not p._precomputed
    assert p._cache == {}


def test_new_recording_invalidates_cache(app, tmp_path):
    p, lab = _panel(tmp_path), _labels()
    p.set_context(lab, 0.5, 10.0)
    p.precompute_all()
    assert p._cache
    p.set_context(_labels(), 0.5, 10.0)         # different labels object -> drop cache
    assert p._cache == {}
    assert not p._precomputed


def test_set_cell_memoises_without_precompute(app, tmp_path):
    p, lab = _panel(tmp_path), _labels()
    p.set_cell(1, lab, 0.5, 10.0, recording=None)
    first = p._cft
    assert 1 in p._cache
    p.set_cell(2, lab, 0.5, 10.0, recording=None)
    p.set_cell(1, lab, 0.5, 10.0, recording=None)   # revisit -> cache hit
    assert p._cft is first


def test_auto_precompute_on_context_when_enabled(app, tmp_path):
    p, lab = _panel(tmp_path), _labels()
    p._auto_precompute = True                       # as if the Config toggle is on
    p.set_context(lab, 0.5, 10.0)                   # load -> auto precompute (sync here)
    assert p._precomputed
    assert set(p._cache) == {1, 2, 3}


def test_no_auto_precompute_when_disabled(app, tmp_path):
    p, lab = _panel(tmp_path), _labels()
    assert p._auto_precompute is False              # default off
    p.set_context(lab, 0.5, 10.0)
    assert not p._precomputed
    assert p._cache == {}


def test_set_auto_precompute_precomputes_current_recording(app, tmp_path):
    p, lab = _panel(tmp_path), _labels()
    p.set_context(lab, 0.5, 10.0)                   # loaded, not precomputed
    assert not p._precomputed
    p.set_auto_precompute(True)                     # enabling it precomputes now
    assert p._precomputed and set(p._cache) == {1, 2, 3}


def test_button_precompute_chains_edge(app, tmp_path):
    """The explicit button (chain=True) folds in edge precompute via after_precompute."""
    p, lab = _panel(tmp_path), _labels()
    p.set_context(lab, 0.5, 10.0)
    called = []
    p.after_precompute = lambda: called.append(True)
    p.precompute_all(chain=True)                    # synchronous (run_async None)
    assert called == [True]


def test_auto_precompute_does_not_chain_edge(app, tmp_path):
    """Auto-precompute (chain=False, default) stays cell-info-only — no heavy edge pass."""
    p, lab = _panel(tmp_path), _labels()
    p._auto_precompute = True
    called = []
    p.after_precompute = lambda: called.append(True)
    p.set_context(lab, 0.5, 10.0)                   # load → auto precompute (no chain)
    assert p._precomputed and called == []          # cell-info done, edge NOT chained
