"""Edge-dynamics panel: lazy (visibility-gated) compute + render integrity.

The right-hand docks are tabbed, so clicking cells while another tab is in
front must NOT pay for the multi-second edge-dynamics compute. `EdgePanel`
tracks its visibility via show/hide events (which fire on tab switches) and
defers the heavy kymograph/fluorescence compute until it is the front tab.
Also smoke-tests every draw mode after the render layer was split into
`edge_render.EdgeRenderMixin`.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

pytest.importorskip("PyQt5")
from PyQt5 import QtWidgets, QtGui  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _labels():
    """2 cells over 8 frames (drifting discs) — enough for kymographs."""
    T, H, W = 8, 64, 64
    lab = np.zeros((T, H, W), np.int32)
    yy, xx = np.ogrid[:H, :W]
    for t in range(T):
        lab[t][(yy - (16 + t))**2 + (xx - 16)**2 <= 8**2] = 1
        lab[t][(yy - 40)**2 + (xx - (40 - t))**2 <= 7**2] = 2
    return lab


class _Rec:
    channel_names = ["DIC", "Cy5"]
    n_channels = 2

    def __init__(self, lab):
        self._img = np.stack([(lab > 0) * 100, (lab > 0) * 500], 1).astype(np.uint16)

    def aligned_channel(self, c):
        return self._img[:, c]


def _show(p):
    p.showEvent(QtGui.QShowEvent())


def _hide(p):
    p.hideEvent(QtGui.QHideEvent())


def test_defers_compute_while_hidden(app):
    from maskviewer.gui.panels.edge_panel import EdgePanel
    p, lab = EdgePanel(), _labels()
    assert p._visible is False                      # not the front tab yet
    p.set_cell(1, lab, 0.5, 10.0, recording=_Rec(lab))
    assert p._pending == 1 and p._vel is None       # deferred — nothing computed
    _show(p)                                        # user switches to the Edge tab
    assert p._visible and p._pending is None
    assert p._vel is not None and p._vel.size > 0   # computed on show


def test_computes_immediately_when_visible(app):
    from maskviewer.gui.panels.edge_panel import EdgePanel
    p, lab = EdgePanel(), _labels()
    _show(p)                                        # Edge tab is in front
    p.set_cell(1, lab, 0.5, 10.0, recording=_Rec(lab))
    assert p._pending is None and p._vel is not None


def test_hidden_again_defers_next_cell(app):
    from maskviewer.gui.panels.edge_panel import EdgePanel
    p, lab = EdgePanel(), _labels()
    _show(p)
    p.set_cell(1, lab, 0.5, 10.0, recording=_Rec(lab))
    _hide(p)                                        # user switches away
    assert p._visible is False
    p.set_cell(2, lab, 0.5, 10.0, recording=_Rec(lab))
    assert p._pending == 2                          # deferred again


def test_clear_cell_resets_pending(app):
    from maskviewer.gui.panels.edge_panel import EdgePanel
    p, lab = EdgePanel(), _labels()
    p.set_cell(2, lab, 0.5, 10.0, recording=_Rec(lab))
    p.clear_cell()
    assert p._pending is None and p.cell_id == 0


def test_revisit_is_cache_hit(app):
    from maskviewer.gui.panels.edge_panel import EdgePanel
    p, lab = EdgePanel(), _labels()
    _show(p)
    p.set_cell(1, lab, 0.5, 10.0, recording=_Rec(lab))
    key = (1, p.fluor.currentText())
    cached_vel = p._cache[key]["_vel"]              # computed + cached
    p.set_cell(2, lab, 0.5, 10.0, recording=_Rec(lab))
    p.set_cell(1, lab, 0.5, 10.0, recording=_Rec(lab))   # revisit same recording
    assert p._vel is cached_vel                     # restored from cache, not recomputed


def test_precompute_all_caches_every_cell(app):
    from maskviewer.gui.panels.edge_panel import EdgePanel
    p, lab = EdgePanel(), _labels()
    p.set_context(lab, 0.5, 10.0, recording=_Rec(lab))
    p.precompute_all()                              # run_async None -> synchronous
    fluor = p.fluor.currentText()
    assert (1, fluor) in p._cache and (2, fluor) in p._cache


def test_new_recording_clears_cache(app):
    from maskviewer.gui.panels.edge_panel import EdgePanel
    p, lab = EdgePanel(), _labels()
    _show(p)
    p.set_cell(1, lab, 0.5, 10.0, recording=_Rec(lab))
    assert p._cache
    p.set_context(_labels(), 0.5, 10.0, recording=_Rec(lab))   # different labels object
    assert p._cache == {}


def test_all_render_modes_after_split(app):
    """Every view mode draws without error (validates the edge_render split)."""
    from maskviewer.gui.panels.edge_panel import EdgePanel
    from maskviewer.gui.panels.edge_render import _MODES
    p, lab = EdgePanel(), _labels()
    _show(p)
    p.set_cell(1, lab, 0.5, 10.0, recording=_Rec(lab))
    p.set_frame(3)
    for i in range(len(_MODES)):
        p.mode.setCurrentIndex(i)
        p._replot()                                 # must not raise
