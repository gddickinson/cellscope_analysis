"""Per-cell fluorescence-intensity + membrane aggregates across a recording (GUI-free).

The Cell-Info panel can plot per-channel **mean intensity** and **membrane** metrics
(cortical enrichment) over a cell's track, but those never reached the per-cell table,
so they couldn't be **compared across conditions**. This computes them once per
recording — for every channel, the track-mean of: mean in-mask intensity, membrane
score, boundary gradient and membrane contrast — so they flow into the comparison
(e.g. compare SiR-actin / tagged-PIEZO1 levels + cortical enrichment between groups).
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
from scipy import ndimage

from . import membrane as _membrane

# membrane-fn → comparison column stem (matches the Cell-Info per-channel keys)
_FUNCS = (("intensity", None),
          ("membrane_score", _membrane.membrane_score),
          ("boundary_grad", _membrane.boundary_confidence),
          ("membrane_contrast", _membrane.intensity_contrast))


def per_cell_fluor(labels, recording, pad=3) -> dict:
    """``{cell_id: {mean_<stem>_<channel>: value}}`` over each track's present frames.

    For every channel: the track-mean of in-mask intensity + the three membrane
    metrics. Cropped to each cell's bounding box (+``pad``) for speed."""
    labels = np.asarray(labels)
    nch = int(getattr(recording, "n_channels", 0))
    if nch == 0:
        return {}
    names = [(recording.channel_names[c] or f"ch{c}") for c in range(nch)]
    acc: dict = defaultdict(lambda: defaultdict(list))
    for t in range(labels.shape[0]):
        lab = labels[t]
        objs = ndimage.find_objects(lab)
        imgs = [np.asarray(recording.frame(t, c), float) for c in range(nch)]
        for idx, sl in enumerate(objs):
            if sl is None:
                continue
            cid = idx + 1
            ys = slice(max(sl[0].start - pad, 0), min(sl[0].stop + pad, lab.shape[0]))
            xs = slice(max(sl[1].start - pad, 0), min(sl[1].stop + pad, lab.shape[1]))
            m = lab[ys, xs] == cid
            if not m.any():
                continue
            d = acc[cid]
            for c in range(nch):
                sub = imgs[c][ys, xs]
                d[f"intensity_{names[c]}"].append(float(sub[m].mean()))
                d[f"membrane_score_{names[c]}"].append(_membrane.membrane_score(m, sub))
                d[f"boundary_grad_{names[c]}"].append(_membrane.boundary_confidence(m, sub))
                d[f"membrane_contrast_{names[c]}"].append(_membrane.intensity_contrast(m, sub))
    out = {}
    for cid, d in acc.items():
        out[int(cid)] = {f"mean_{k}": float(np.nanmean(v)) if len(v) else np.nan
                         for k, v in d.items()}
    return out


def per_cell_fluor_table(labels, recording):
    """DataFrame (one row per cell) of the fluorescence aggregates — for merging."""
    import pandas as pd
    fl = per_cell_fluor(labels, recording)
    rows = [{"cell_id": c, **v} for c, v in fl.items()]
    return pd.DataFrame(rows)
