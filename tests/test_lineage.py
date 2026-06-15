"""Lineage / division-event validation (drop events referencing absent tracks)."""
import numpy as np

from maskviewer.analysis import lineage


def _labels():
    """A 4-frame stack with tracks 1, 2, 3 present (no 88 / 99)."""
    L = np.zeros((4, 20, 20), np.int32)
    L[:, 2:6, 2:6] = 1                     # track 1: all frames
    L[1:, 2:6, 10:14] = 2                  # track 2: appears frame 1
    L[2:, 12:16, 2:6] = 3                  # track 3: appears frame 2
    return L


def _div(parent, daughter, frame):
    return {"parent": parent, "daughter": daughter, "frame": frame,
            "score": 0.5, "parent_centroid": [1, 1], "daughter_centroid": [2, 2]}


def test_present_ids():
    assert lineage.present_ids(_labels()) == {1, 2, 3}


def test_valid_divisions_drops_absent_tracks():
    L = _labels()
    divs = [
        _div(1, 2, 1),       # both present → keep
        _div(1, 99, 3),      # daughter 99 absent (removed in cleaning) → drop
        _div(88, 3, 2),      # parent 88 absent → drop
        _div(77, 66, 2),     # both absent → drop
    ]
    valid = lineage.valid_divisions(divs, L)
    assert len(valid) == 1
    assert valid[0]["parent"] == 1 and valid[0]["daughter"] == 2
    # the cleaned set drives relatives correctly
    assert lineage.relatives(valid, 1) == ([], [2])
    assert lineage.relatives(valid, 2) == ([1], [])
    # the phantom daughter never appears as anyone's relative
    assert lineage.relatives(valid, 99) == ([], [])


def test_valid_divisions_empty():
    assert lineage.valid_divisions([], _labels()) == []
    # all events reference missing tracks → nothing survives (the Pos60 case)
    assert lineage.valid_divisions([_div(11, 16, 63), _div(21, 16, 55)], _labels()) == []
