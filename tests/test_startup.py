"""Startup data-root resolution (Config ▸ Startup toggles → what loads on launch).

`startup_roots` is pure (no Qt), so we test the four toggle combinations and the
`include_sample` flag on `load_config` directly — the GUI just persists the two
booleans and main_viewer feeds them in.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from maskviewer.config import SAMPLE_DIR, load_config, startup_roots  # noqa: E402


def _write_cfg(tmp_path, roots):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"data_roots": roots}))
    return str(p)


def test_blank_slate_when_both_off(tmp_path):
    cfg = _write_cfg(tmp_path, ["/some/data"])
    assert startup_roots(False, False, config_path=cfg) == []


def test_demo_only(tmp_path):
    cfg = _write_cfg(tmp_path, ["/some/data"])
    assert startup_roots(False, True, config_path=cfg) == [SAMPLE_DIR]


def test_config_only_excludes_demo(tmp_path):
    cfg = _write_cfg(tmp_path, ["/some/data"])
    assert startup_roots(True, False, config_path=cfg) == ["/some/data"]


def test_both_on_appends_demo(tmp_path):
    cfg = _write_cfg(tmp_path, ["/some/data"])
    assert startup_roots(True, True, config_path=cfg) == ["/some/data", SAMPLE_DIR]


def test_load_config_include_sample_flag(tmp_path):
    cfg = _write_cfg(tmp_path, ["/some/data"])
    assert load_config(cfg, include_sample=False)["data_roots"] == ["/some/data"]
    assert SAMPLE_DIR in load_config(cfg, include_sample=True)["data_roots"]
