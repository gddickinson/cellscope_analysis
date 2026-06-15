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


def _division_stack():
    """A realistic division: a parent that swells + stays round, then a persistent
    daughter appears beside it; plus a border-entry and a distant new cell."""
    L = np.zeros((10, 80, 80), np.int32)
    for t, r in enumerate((6, 7, 8, 10)):        # parent swells (rounds up) frames 0-3
        _disc(L, t, 1, 40, 30, r)
    for t in range(4, 10):                       # parent continues (shrunk) after split
        _disc(L, t, 1, 40, 28, 7)
        _disc(L, t, 2, 40, 42, 7)                # daughter: appears frame 4, persists
    for t in range(2, 10):
        _disc(L, t, 3, 4, 4, 6)                  # enters at the border → not a division
    for t in range(5, 10):
        _disc(L, t, 4, 70, 70, 6)                # distant new cell → not a division
    return L


def test_infer_divisions_scored_split():
    """A swelling, balled parent with a persistent adjacent daughter scores high
    and is detected; the border-entry and distant cell are not."""
    ev = lineage.infer_divisions(_division_stack())
    assert len(ev) == 1, [(e["parent"], e["daughter"], e["frame"]) for e in ev]
    e = ev[0]
    assert e["parent"] == 1 and e["daughter"] == 2 and e["frame"] == 4
    assert 0.0 <= e["score"] <= 1.0 and e["score"] > 0.7, e["score"]
    assert all(k in e for k in ("prox", "swell", "balled", "persist", "mass"))
    assert e["swell"] > 0.5 and e["balled"] > 0.5 and e["persist"] > 0.9
    assert lineage.relatives(ev, 1) == ([], [2])
    ids = lineage.present_ids(_division_stack())
    assert all(x["parent"] in ids and x["daughter"] in ids for x in ev)


def test_infer_divisions_score_threshold():
    """The score threshold gates candidates; return_all exposes their scores."""
    L = _division_stack()
    assert lineage.infer_divisions(L, score_threshold=0.99) == []   # nothing passes
    allc = lineage.infer_divisions(L, score_threshold=0.99, return_all=True)
    assert len(allc) == 1 and "score" in allc[0]                    # candidate kept for inspection


def test_infer_divisions_none_for_simple_motion():
    """A single cell translating across frames → no spurious divisions."""
    L = np.zeros((6, 60, 60), np.int32)
    for t in range(6):
        _disc(L, t, 1, 30, 10 + 4 * t, 7)
    assert lineage.infer_divisions(L) == []


def test_infer_divisions_degenerate():
    assert lineage.infer_divisions(np.zeros((1, 10, 10), np.int32)) == []
    assert lineage.infer_divisions(np.zeros((4, 10, 10), np.int32)) == []   # empty
