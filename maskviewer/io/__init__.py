"""IO subpackage — load recordings, masks, and discover datasets.

  recording.py  load_recording(tif) -> Recording  (.ome.tif + .ome.json)
  masks.py      load_masks(npz)     -> Masks       (labels (T,H,W))
  dataset.py    discover(roots)     -> [Entry]     (recording + mask paths)

The mask label stack is the single analysis input — all metrics (incl. lineage)
are derived from it in-project; the pipeline's pre-cleaning `divisions.json` is
not read.
"""
from .recording import load_recording, Recording
from .masks import load_masks, Masks
from .dataset import discover, Entry

__all__ = ["load_recording", "Recording", "load_masks", "Masks",
           "discover", "Entry"]
