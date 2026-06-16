"""Contact-inhibition of locomotion (CIL) — does touching another cell change how a
cell moves? (GUI-free.)

Builds on the cell–cell contact state (`contacts`) + centroid velocities to ask the
classic keratinocyte question: cells should **slow, repolarise, and/or move more
coherently** when they contact a neighbour. Per cell, over a recording:

  * **speed_free / speed_contact** — mean step speed in free vs in-contact frames;
    ``speed_ratio_contact`` = contact ÷ free (CIL → < 1, the cell slows on contact);
  * **delta_speed_onset** — mean (speed *after* − speed *before*) a contact **onset**
    over a ±``window`` frame window (negative = slowing as contact forms);
  * **velocity_alignment** — mean cosine between the cell's step direction and its
    *contacting neighbours'* step directions (coordinated / collective migration);
  * **n_contact_onsets**.

Recording-level (needs all cells); the per-cell table flows into the comparison
behind its own Contact-inhibition (CIL) analysis toggle.
"""
from __future__ import annotations

import numpy as np

from . import contacts as _contacts
from . import cell_metrics as _cm

DEFAULT_WINDOW = 3
_KEYS = ("speed_free", "speed_contact", "speed_ratio_contact", "delta_speed_onset",
         "velocity_alignment", "n_contact_onsets")


def _unit_steps(cen: np.ndarray):
    """``((T-1, 2) unit step vectors, (T-1,) step length)`` — NaN where undefined."""
    d = cen[1:] - cen[:-1]
    norm = np.sqrt((d ** 2).sum(axis=1))
    units = np.full_like(d, np.nan)
    ok = np.isfinite(norm) & (norm > 0)
    units[ok] = d[ok] / norm[ok][:, None]
    return units, norm


def contact_locomotion(labels, scale=1.0, dt_min=None,
                       max_gap_px=_contacts.DEFAULT_GAP_PX, window=DEFAULT_WINDOW,
                       per_frame=None) -> dict:
    """``{cell_id: CIL readouts}`` for one recording (see module docstring)."""
    labels = np.asarray(labels)
    T = labels.shape[0]
    scale = float(scale) if scale else 1.0
    dt = float(dt_min) if dt_min else 1.0
    pf = per_frame if per_frame is not None else _contacts.contacts_over_time(
        labels, scale, max_gap_px)
    cents = _cm.centroid_history(labels)
    in_contact, units, speeds = {}, {}, {}
    for cid, cen in cents.items():
        ic = np.array([bool((r := pf[t].get(cid)) and r["contact_class"] != "free")
                       for t in range(T)], bool)
        in_contact[cid] = ic
        u, norm = _unit_steps(cen)
        units[cid] = u
        speeds[cid] = norm * scale / dt                  # speed of the step starting at t
    out = {}
    for cid in cents:
        ic, sp, u = in_contact[cid], speeds[cid], units[cid]
        step_state = ic[:-1]                             # state at the step's start frame
        fin = np.isfinite(sp)
        sf, sc = sp[(~step_state) & fin], sp[step_state & fin]
        speed_free = float(sf.mean()) if sf.size else np.nan
        speed_contact = float(sc.mean()) if sc.size else np.nan
        ratio = (speed_contact / speed_free
                 if np.isfinite(speed_free) and speed_free > 0 else np.nan)
        onsets = [t for t in range(1, T) if ic[t] and not ic[t - 1]]
        deltas = []
        for f in onsets:
            before = sp[max(0, f - window):f]
            after = sp[f:min(sp.size, f + window)]
            before, after = before[np.isfinite(before)], after[np.isfinite(after)]
            if before.size and after.size:
                deltas.append(float(after.mean() - before.mean()))
        cos = []
        for t in range(T - 1):
            r = pf[t].get(cid)
            if not ic[t] or not r or not np.isfinite(u[t]).all():
                continue
            for p in r["partners"]:
                up = units.get(p)
                if up is not None and t < up.shape[0] and np.isfinite(up[t]).all():
                    cos.append(float(u[t] @ up[t]))
        out[int(cid)] = {
            "speed_free": speed_free, "speed_contact": speed_contact,
            "speed_ratio_contact": ratio,
            "delta_speed_onset": float(np.mean(deltas)) if deltas else np.nan,
            "velocity_alignment": float(np.mean(cos)) if cos else np.nan,
            "n_contact_onsets": len(onsets),
        }
    return out


def contact_locomotion_table(labels, um_per_px=None, dt_min=None, per_frame=None):
    """DataFrame (one row per cell) of CIL readouts — for merging / CSV."""
    import pandas as pd
    scale = float(um_per_px) if um_per_px else 1.0
    cl = contact_locomotion(labels, scale, dt_min, per_frame=per_frame)
    cols = ["cell_id"] + list(_KEYS)
    return pd.DataFrame([{"cell_id": c, **v} for c, v in cl.items()], columns=cols)
