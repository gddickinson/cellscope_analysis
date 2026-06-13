"""Analysis subpackage — pure-function stats over label stacks.

  label_stats.py  n_cells_per_frame / cell_areas_px / track_lengths /
                  centroids / summary  — grow analysis here, GUI-free.
"""
from .label_stats import (
    n_cells_per_frame, cell_ids, cell_areas_px, track_lengths, centroids,
    summary)

__all__ = ["n_cells_per_frame", "cell_ids", "cell_areas_px", "track_lengths",
           "centroids", "summary"]
