"""IO subpackage — load recordings, masks, and discover datasets.

  recording.py  load_recording(tif) -> Recording  (.ome.tif + .ome.json)
  masks.py      load_masks(npz)     -> Masks       (labels (T,H,W))
  divisions.py  load_divisions(json) -> [events]   (parent→daughter, frame)
  dataset.py    discover(roots)     -> [Entry]     (recording + mask paths)
"""
from .recording import load_recording, Recording
from .masks import load_masks, Masks
from .divisions import load_divisions, divisions_path_for
from .dataset import discover, Entry

__all__ = ["load_recording", "Recording", "load_masks", "Masks",
           "load_divisions", "divisions_path_for", "discover", "Entry"]
