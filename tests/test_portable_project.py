"""Portable project files — `data_roots` saved relative to the project file.

A project saved alongside its data must keep working when the whole folder is moved
(another path / another machine / a share mounted elsewhere). We build a tiny real
recording tree, save a project into it, then *move the entire tree* and confirm the
recording is still discovered. Legacy absolute roots must still load.
"""
import json
import os
import shutil

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from maskviewer import project as projmod  # noqa: E402


def _recording_tree(root):
    """A minimal discoverable recording: <root>/WT/Pos0/Pos0.ome.tif + masks."""
    import tifffile
    rec = os.path.join(root, "WT", "Pos0")
    os.makedirs(os.path.join(rec, "pipeline_results"), exist_ok=True)
    tifffile.imwrite(os.path.join(rec, "Pos0.ome.tif"),
                     np.zeros((2, 4, 4), np.uint16))
    np.savez(os.path.join(rec, "pipeline_results", "masks.npz"),
             labels=np.zeros((2, 4, 4), np.int32))
    return root


def test_data_roots_saved_relative_to_project_file(tmp_path):
    data = _recording_tree(str(tmp_path / "ic_analysis"))
    proj = projmod.from_data_roots(data, name="IC")
    proj.excluded.add("Pos0")
    fn = os.path.join(data, "proj.json")          # project saved *inside* the data dir
    projmod.save_project(proj, fn)
    blob = json.load(open(fn))
    assert blob["data_roots"] == ["."]            # portable: relative to the file
    assert blob["excluded"] == ["Pos0"]


def test_project_moves_with_data(tmp_path):
    data = _recording_tree(str(tmp_path / "orig"))
    proj = projmod.from_data_roots(data, name="IC")
    projmod.save_project(proj, os.path.join(data, "proj.json"))

    moved = str(tmp_path / "relocated")           # simulate copy to a new location
    shutil.copytree(data, moved)
    reloaded = projmod.load_project(os.path.join(moved, "proj.json"))

    assert reloaded.data_roots == [moved]         # resolved to the NEW absolute path
    assert [e.label for e in reloaded.entries] == ["Pos0"]   # data still discovered


def test_absolute_data_roots_backward_compatible(tmp_path):
    data = _recording_tree(str(tmp_path / "abs"))
    fn = str(tmp_path / "legacy.json")
    json.dump({"name": "L", "data_roots": [data]}, open(fn, "w"))   # legacy absolute
    reloaded = projmod.load_project(fn)
    assert reloaded.data_roots == [data]
    assert [e.label for e in reloaded.entries] == ["Pos0"]


def test_resave_relativises_legacy_absolute(tmp_path):
    """Loading a legacy absolute project then saving it (in the data dir) makes it
    portable — exactly what re-saving ic293.json does."""
    data = _recording_tree(str(tmp_path / "d"))
    fn = os.path.join(data, "p.json")
    json.dump({"name": "L", "data_roots": [data], "excluded": ["Pos0"]},
              open(fn, "w"))
    proj = projmod.load_project(fn)
    projmod.save_project(proj, fn)                # re-save in place
    blob = json.load(open(fn))
    assert blob["data_roots"] == ["."]           # now relative/portable
    assert blob["excluded"] == ["Pos0"]          # content preserved
