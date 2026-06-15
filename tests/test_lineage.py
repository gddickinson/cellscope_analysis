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


def _disc(L, t, cid, cy, cx, r):
    yy, xx = np.ogrid[:L.shape[1], :L.shape[2]]
    L[t][(yy - cy) ** 2 + (xx - cx) ** 2 <= r * r] = cid


def test_infer_divisions_detects_a_split():
    """A new daughter appearing adjacent to a parent present the previous frame
    is a division; a cell entering at the border, and a distant new cell, are not."""
    L = np.zeros((5, 60, 60), np.int32)
    for t in range(5):
        _disc(L, t, 1, 30, 20, 8)            # parent: present all frames
    for t in range(2, 5):
        _disc(L, t, 2, 30, 34, 7)            # daughter: appears frame 2, beside parent 1
    for t in range(2, 5):
        _disc(L, t, 3, 4, 4, 6)              # enters at the border frame 2 → not a division
    for t in range(3, 5):
        _disc(L, t, 4, 50, 50, 6)            # distant new cell → not a division
    ev = lineage.infer_divisions(L)
    assert len(ev) == 1, ev
    e = ev[0]
    assert e["parent"] == 1 and e["daughter"] == 2 and e["frame"] == 2
    assert lineage.relatives(ev, 1) == ([], [2])
    assert lineage.relatives(ev, 2) == ([1], [])
    # every inferred event references real tracks present in the stack
    ids = lineage.present_ids(L)
    assert all(e["parent"] in ids and e["daughter"] in ids for e in ev)


def test_infer_divisions_none_for_simple_motion():
    """A single cell translating across frames → no spurious divisions."""
    L = np.zeros((6, 60, 60), np.int32)
    for t in range(6):
        _disc(L, t, 1, 30, 10 + 4 * t, 7)
    assert lineage.infer_divisions(L) == []


def test_infer_divisions_degenerate():
    assert lineage.infer_divisions(np.zeros((1, 10, 10), np.int32)) == []
    assert lineage.infer_divisions(np.zeros((4, 10, 10), np.int32)) == []   # empty
