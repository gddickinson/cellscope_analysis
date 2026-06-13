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


def load_config(path: str | None = None) -> dict:
    """Return the config dict, always with a non-empty `data_roots` list
    (the bundled sample dir is appended as a fallback)."""
    path = path or CONFIG_PATH
    cfg: dict = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            cfg = {}
    roots = list(cfg.get("data_roots") or [])
    if os.path.isdir(SAMPLE_DIR) and SAMPLE_DIR not in roots:
        roots.append(SAMPLE_DIR)
    cfg["data_roots"] = roots
    return cfg
