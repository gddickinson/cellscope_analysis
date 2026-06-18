#!/usr/bin/env python
"""Launch the cellscope_analysis recording + mask viewer.

    conda run -n cellpose4 python main_viewer.py            # per Startup settings
    python main_viewer.py --data-root /path/to/by_condition  # override roots
    python main_viewer.py --recording R.ome.tif --masks M.npz  # one recording

With no data CLI args the viewer honours the persisted **Startup** toggles
(Config ▸ Settings ▸ Startup): load the demo sample and/or the config.json
roots, or — both off (the default) — open on a **blank slate** (no recordings;
use File ▸ Open Project Folder / Recent Projects). Explicit CLI args always win.
"""
from __future__ import annotations

import os
import sys
import argparse

from maskviewer.config import load_config, startup_roots
from maskviewer.io import discover, Entry


def _name_of(roots):
    return os.path.basename(os.path.normpath(roots[0])) if roots else "(no project)"


def _resolve(args):
    """Return ``(entries, roots, name, explicit)`` for launch. ``explicit`` is
    True when the user named data on the command line (then an empty result is
    an error); otherwise we follow the Startup settings and a blank result is
    an intentional blank-slate launch."""
    if args.recording:
        label = os.path.splitext(os.path.basename(args.recording))[0]
        return ([Entry(label=label, condition="", recording_path=args.recording,
                       mask_path=args.masks)], [], label, True)
    if args.data_root:
        roots = args.data_root
        return discover(roots), roots, _name_of(roots), True
    if args.config:                               # explicit config file → load it
        roots = load_config(args.config, include_sample=False)["data_roots"]
        return discover(roots), roots, _name_of(roots), True
    # No data CLI args → follow the persisted Startup toggles.
    from PyQt5 import QtCore
    s = QtCore.QSettings("cellscope_analysis", "viewer")
    roots = startup_roots(s.value("startup/load_config_roots", False, type=bool),
                          s.value("startup/load_demo", False, type=bool))
    return (discover(roots) if roots else []), roots, _name_of(roots), False


def main(argv=None):
    ap = argparse.ArgumentParser(description="View CellScope recordings + masks.")
    ap.add_argument("--config", help="path to config.json (default: project root)")
    ap.add_argument("--data-root", action="append",
                    help="recording root(s) to scan (repeatable; overrides config)")
    ap.add_argument("--recording", help="open a single .ome.tif directly")
    ap.add_argument("--masks", help="masks.npz for --recording")
    args = ap.parse_args(argv)

    from PyQt5 import QtWidgets             # imported late so --help needs no Qt
    from maskviewer.gui import ViewerWindow
    from maskviewer import project as projmod
    app = QtWidgets.QApplication(sys.argv)

    entries, roots, name, explicit = _resolve(args)
    if explicit and not entries:
        print("No recordings found. Point at data with --data-root or "
              "config.json (see config.example.json).", file=sys.stderr)
        return 2

    win = ViewerWindow(projmod.from_entries(entries, name=name, data_roots=roots))
    win.show()
    if entries:
        print(f"Loaded {len(entries)} recording(s).")
    else:
        print("Opened on a blank slate — use File ▸ Open Project Folder to load data.")
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
