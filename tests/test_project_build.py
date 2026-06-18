"""Manually-assembled projects: add recordings / folders from different trees and
have them persist across save → reload (portable). Pure model tests (no Qt).
"""
import os
import shutil

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from maskviewer import project as projmod  # noqa: E402
from maskviewer.io.dataset import Entry  # noqa: E402


def _rec(root, label, cond):
    """A discoverable recording <root>/<cond>/<label>/<label>.ome.tif + masks."""
    import tifffile
    d = os.path.join(root, cond, label)
    os.makedirs(os.path.join(d, "pipeline_results"), exist_ok=True)
    tifffile.imwrite(os.path.join(d, f"{label}.ome.tif"), np.zeros((2, 4, 4), np.uint16))
    np.savez(os.path.join(d, "pipeline_results", "masks.npz"),
             labels=np.zeros((2, 4, 4), np.int32))
    return os.path.join(d, f"{label}.ome.tif"), os.path.join(d, "pipeline_results", "masks.npz")


def test_add_recording_persists_across_save(tmp_path):
    A = str(tmp_path / "projA")
    _rec(A, "PosA", "WT")
    tifB, npzB = _rec(str(tmp_path / "projB"), "PosB", "KO")
    proj = projmod.from_data_roots(A, name="hand")
    assert proj.add_recording(Entry("PosB", "KO", tifB, npzB)) is True
    fn = os.path.join(A, "p.json")
    projmod.save_project(proj, fn)
    r = projmod.load_project(fn)
    assert sorted(e.label for e in r.entries) == ["PosA", "PosB"]   # added survives
    assert [e.label for e in r.extra] == ["PosB"]


def test_add_recording_dedup(tmp_path):
    A = str(tmp_path / "a")
    tif, npz = _rec(A, "PosA", "WT")
    proj = projmod.from_data_roots(A)
    assert proj.add_recording(Entry("PosA", "WT", tif, npz)) is False   # already discovered
    assert len(proj.entries) == 1 and proj.extra == []


def test_add_folder_merges_and_persists(tmp_path):
    A = str(tmp_path / "a"); B = str(tmp_path / "b")
    _rec(A, "PosA", "WT")
    _rec(B, "PosB", "KO")
    proj = projmod.from_data_roots(A, name="multi")
    assert proj.add_folder(B) == 1
    assert os.path.abspath(B) in proj.data_roots
    fn = os.path.join(str(tmp_path), "p.json")
    projmod.save_project(proj, fn)
    r = projmod.load_project(fn)
    assert sorted(e.label for e in r.entries) == ["PosA", "PosB"]
    assert r.extra == []                                # B persists via data_roots, not extra


def test_add_folder_no_duplicate_with_extra(tmp_path):
    A = str(tmp_path / "a"); B = str(tmp_path / "b")
    _rec(A, "PosA", "WT")
    tifB, npzB = _rec(B, "PosB", "KO")
    proj = projmod.from_data_roots(A)
    proj.add_recording(Entry("PosB", "KO", tifB, npzB))   # added individually first
    assert proj.add_folder(B) == 0                        # already present → no dup
    fn = os.path.join(str(tmp_path), "p.json")
    projmod.save_project(proj, fn)
    r = projmod.load_project(fn)
    assert sorted(e.label for e in r.entries) == ["PosA", "PosB"]   # exactly one each


def test_added_recording_path_is_portable(tmp_path):
    base = tmp_path / "base"
    A = str(base / "projA")
    _rec(A, "PosA", "WT")
    tifB, npzB = _rec(str(base / "projB"), "PosB", "KO")
    proj = projmod.from_data_roots(A, name="hand")
    proj.add_recording(Entry("PosB", "KO", tifB, npzB))
    projmod.save_project(proj, os.path.join(A, "p.json"))

    moved = str(tmp_path / "moved")                       # relocate the whole tree
    shutil.copytree(str(base), moved)
    r = projmod.load_project(os.path.join(moved, "projA", "p.json"))
    labels = sorted(e.label for e in r.entries)
    assert labels == ["PosA", "PosB"]                     # both resolve at the new location
    added = next(e for e in r.entries if e.label == "PosB")
    assert added.recording_path.startswith(moved) and os.path.isfile(added.recording_path)
