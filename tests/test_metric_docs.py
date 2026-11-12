"""The Help ▸ Metrics reference must describe the perimeter estimator the code uses.

`cell_metrics._perimeter` is scikit-image's `regionprops.perimeter` (Benkrid–Crookes,
neighborhood=4), not the Crofton estimate the docs used to name.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from maskviewer.analysis import cell_metrics, metric_docs  # noqa: E402


def test_perimeter_doc_names_the_estimator_in_use():
    how = metric_docs.METRICS["perimeter"][1]
    assert "Crofton" not in how
    assert "Benkrid" in how


def test_perimeter_estimator_is_benkrid_crookes_nb4():
    # A 10x10 square: the nb=4 Benkrid-Crookes estimate walks the 36 boundary pixel
    # centres (skimage.measure.perimeter(m, 4) == 36.0); Crofton would give ~37.7.
    m = np.zeros((14, 14), bool)
    m[2:12, 2:12] = True
    assert abs(cell_metrics._perimeter(m) - 36.0) < 1e-9
