"""Analysis subpackage — pure-function stats over label stacks.

  label_stats.py  n_cells_per_frame / cell_areas_px / track_lengths /
                  centroids / summary  — basic counts & areas, GUI-free.
  cell_metrics.py regionprops_frame / per_frame_records — moment-based shape
                  morphometry (area, eccentricity, axes, solidity), no skimage.
  motion.py       instantaneous_speed / displacement_metrics / msd / fit_msd /
                  direction_autocorrelation / persistence / turning_angles.
  state.py        classify_state — per-frame rounded/spread (CellScope IC295 rule).
  neighbors.py    frame_nn — per-cell nearest-neighbour distance + count.
  edge_dynamics.py edge_velocity_kymograph / radius_kymograph / edge_summary —
                  radial protrusion/retraction membrane dynamics (no cv2).
  shape_modes.py  fit_shape_modes / cell_mode_series / mode_contour — VAMPIRE-
                  style population shape-mode clustering (PCA + K-means, sklearn).
  exporters.py    per_frame_table / per_cell_table / track_table / export_all —
                  tidy DataFrames + CSV writers for Origin etc.

Grow analysis here (GUI-free, testable). The CellScope-IC295-specific layer
(feature_tables / multivariate / dynamics / interactions / edges) lives
alongside but couples to those result artifacts.
"""
from .label_stats import (
    n_cells_per_frame, cell_ids, cell_areas_px, track_lengths, centroids,
    summary)
from . import (cell_metrics, motion, state, neighbors, edge_dynamics,
               shape_modes, metric_docs, exporters)

__all__ = ["n_cells_per_frame", "cell_ids", "cell_areas_px", "track_lengths",
           "centroids", "summary", "cell_metrics", "motion", "state",
           "neighbors", "edge_dynamics", "shape_modes", "metric_docs",
           "exporters"]
