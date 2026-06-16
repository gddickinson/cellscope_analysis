"""Tests for the mask detection-source feature (colour-by "Mask source").

The pipeline's ``fusion_source_stack`` (DIC↔Cy5 detection fusion) records per-pixel
which channel detected each region (1=DIC, 2=Cy5, 3=both). The final ``masks.npz``
drops it, so it is read from a sibling pre-cleaning artifact and reduced to a per-cell
majority for display-only colouring.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maskviewer.io import load_masks  # noqa: E402


def test_cell_sources_majority_vote(tmp_path):
    T = 2
    lab = np.zeros((T, 30, 30), np.int32)
    src = np.zeros((T, 30, 30), np.uint8)
    lab[:, 2:8, 2:8] = 1
    src[:, 2:8, 2:8] = 3                       # cell 1 → both
    lab[:, 12:18, 12:18] = 2
    src[:, 12:18, 12:18] = 2                   # cell 2 → Cy5
    lab[:, 22:28, 22:28] = 3
    src[:, 22:28, 22:28] = 1                   # cell 3 → mostly DIC
    src[0, 22:24, 22:24] = 2                   # …with a Cy5 minority
    p = str(tmp_path / "masks.npz")
    np.savez_compressed(p, labels=lab, fusion_source_stack=src)
    m = load_masks(p)
    assert m.source_path == p
    assert m.source_stack().shape == (T, 30, 30)
    assert m.cell_sources() == {1: 3, 2: 2, 3: 1}


def test_source_read_from_sibling_when_final_lacks_it(tmp_path):
    lab = np.zeros((1, 20, 20), np.int32)
    lab[0, 2:8, 2:8] = 1
    src = np.zeros((1, 20, 20), np.uint8)
    src[0, 2:8, 2:8] = 2
    np.savez_compressed(str(tmp_path / "masks.npz"), labels=lab)            # no source
    np.savez_compressed(str(tmp_path / "masks_precleanup.npz"),
                        labels=lab, fusion_source_stack=src)                # has source
    m = load_masks(str(tmp_path / "masks.npz"))
    assert m.source_path.endswith("masks_precleanup.npz")
    assert m.cell_sources() == {1: 2}


def test_no_source_data_is_graceful(tmp_path):
    lab = np.zeros((1, 10, 10), np.int32)
    lab[0, 2:5, 2:5] = 1
    np.savez_compressed(str(tmp_path / "masks.npz"), labels=lab)
    m = load_masks(str(tmp_path / "masks.npz"))
    assert m.source_path is None
    assert m.source_stack() is None
    assert m.cell_sources() == {}


def test_color_by_offers_source():
    from maskviewer.gui.panels.display_panel import COLOR_BY
    assert any(key == "source" for _label, key in COLOR_BY)
