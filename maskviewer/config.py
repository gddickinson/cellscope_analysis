"""Project configuration — where to find recordings + masks.

Real data lives OUTSIDE this (public) repo, so paths are machine-specific
and kept in a gitignored `config.json` at the project root:

    {"data_roots": ["/path/to/cellscope/ic295_analysis/by_condition"]}

`config.example.json` (committed) documents the format. With no config the
viewer falls back to the bundled synthetic `sample_data/` so it runs out of
the box. CLI flags (`--data-root`, `--config`) override the file.
"""
from __future__ import annotations

import os
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_DIR = os.path.join(PROJECT_ROOT, "sample_data")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")


def load_config(path: str | None = None, include_sample: bool = True) -> dict:
    """Return the config dict with a `data_roots` list. When `include_sample`
    (the default, for analysis scripts), the bundled synthetic sample dir is
    appended as a fallback; the GUI startup path passes False and adds the demo
    only when the user opts in (see `startup_roots`)."""
    path = path or CONFIG_PATH
    cfg: dict = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            cfg = {}
    roots = list(cfg.get("data_roots") or [])
    if include_sample and os.path.isdir(SAMPLE_DIR) and SAMPLE_DIR not in roots:
        roots.append(SAMPLE_DIR)
    cfg["data_roots"] = roots
    return cfg


def startup_roots(load_config_roots: bool, load_demo: bool,
                  config_path: str | None = None) -> list:
    """Data roots to scan when the GUI launches, per the persisted startup
    toggles (Config ▸ Settings ▸ Startup). Both off → an empty list, i.e. the
    viewer opens on a blank slate (no recordings) and the user loads data via
    File ▸ Open Project Folder / Recent Projects. Pure (no Qt) so it's testable."""
    roots: list = []
    if load_config_roots:
        roots += list(load_config(config_path, include_sample=False)["data_roots"])
    if load_demo and os.path.isdir(SAMPLE_DIR) and SAMPLE_DIR not in roots:
        roots.append(SAMPLE_DIR)
    return roots
