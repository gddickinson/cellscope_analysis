#!/usr/bin/env python
"""Launch the cellscope_analysis recording + mask viewer.

    conda run -n cellpose4 python main_viewer.py            # discover from config
    python main_viewer.py --data-root /path/to/by_condition  # override roots
    python main_viewer.py --recording R.ome.tif --masks M.npz  # one recording

With no config + no args it falls back to the bundled synthetic sample_data/,
so it always launches.
"""
from __future__ import annotations

import os
import sys
import argparse

from maskviewer.config import load_config
from maskviewer.io import discover, Entry


def _entries(args):
    if args.recording:
        label = os.path.splitext(os.path.basename(args.recording))[0]
        return [Entry(label=label, condition="", recording_path=args.recording,
                      mask_path=args.masks)]
    roots = args.data_root or load_config(args.config)["data_roots"]
    return discover(roots)


def main(argv=None):
    ap = argparse.ArgumentParser(description="View CellScope recordings + masks.")
    ap.add_argument("--config", help="path to config.json (default: project root)")
    ap.add_argument("--data-root", action="append",
                    help="recording root(s) to scan (repeatable; overrides config)")
    ap.add_argument("--recording", help="open a single .ome.tif directly")
    ap.add_argument("--masks", help="masks.npz for --recording")
    args = ap.parse_args(argv)

    entries = _entries(args)
    if not entries:
        print("No recordings found. Point at data with --data-root or "
              "config.json (see config.example.json).", file=sys.stderr)
        return 2

    from PyQt5 import QtWidgets               # imported late so --help needs no Qt
    from maskviewer.gui import ViewerWindow
    app = QtWidgets.QApplication(sys.argv)
    win = ViewerWindow(entries)
    win.show()
    print(f"Loaded {len(entries)} recording(s).")
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
