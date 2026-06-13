"""cellscope_analysis — view & analyse CellScope detection results.

Top-level package. See INTERFACE.md for the navigation map.

  config.py    load_config() — where recordings/masks live (data_roots)
  io/          load_recording / load_masks / discover
  gui/         ViewerWindow (PyQt5 + pyqtgraph)
  analysis/    label_stats — pure-function stats over label stacks (expand here)
"""
__version__ = "0.1.0"
