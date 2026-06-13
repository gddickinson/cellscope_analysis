"""Dynamic / event-based analyses — where a mechanosensor effect may hide.

Time-averaged metrics wash out dynamics. These read the per-cell time series
(states + positions + neighbour counts per frame) and probe processes that a
Piezo1-type perturbation could modulate even with unchanged means:

  transition_rate      rounded<->spread switches per classifiable frame
  dwell_median         median time (min) a cell stays in a state
  contact_response     change in step speed after a cell first gains a
                       neighbour (contact inhibition of locomotion)
  rounding_on_contact  fraction of contact-onset events followed by a
                       spread->rounded switch within the window

Each is reduced to ONE value per recording (mean over its cells), then run
through the arm-structured test (recording = experimental unit).
"""
from __future__ import annotations

import numpy as np

from . import feature_tables as ft

DT = ft.DT_MIN
SPEED_CAP = 15.0
WIN = 3                       # frames each side of a contact event (= 30 min)
MIN_EVENTS = 3                # need >= this many events for a contact metric
ROUNDED, SPREAD = "rounded", "spread"


def _step_speed(cents):
    """(T-1,) step speed µm/min; NaN where a frame is absent or speed > cap."""
    d = np.linalg.norm(np.diff(cents, axis=0), axis=1) / DT
    d[~np.isfinite(d)] = np.nan
    d[d > SPEED_CAP] = np.nan
    return d


def _is(states, s):
    return np.array([str(x) == s for x in states])


def transition_rate(rec):
    st = rec["states"]
    cls = _is(st, ROUNDED) | _is(st, SPREAD)
    pairs = cls[:-1] & cls[1:]                         # consecutive classifiable
    if pairs.sum() < 2:
        return np.nan
    changed = np.array([str(st[i]) != str(st[i + 1])
                        for i in np.where(pairs)[0]])
    return changed.mean()


def dwell_median(rec, state):
    """Median run length (min) of consecutive `state` frames."""
    mask = _is(rec["states"], state).astype(int)
    runs, c = [], 0
    for m in mask:
        if m:
            c += 1
        elif c:
            runs.append(c); c = 0
    if c:
        runs.append(c)
    return float(np.median(runs) * DT) if runs else np.nan


def _contact_onsets(rec):
    nb = np.asarray(rec["n_neighbors"], float)
    ok = np.isfinite(nb)
    return [t for t in range(1, len(nb))
            if ok[t] and ok[t - 1] and nb[t - 1] == 0 and nb[t] >= 1]


def contact_response(rec):
    """Mean (post − pre) step speed around contact onset; <0 = slows on contact."""
    sp = _step_speed(rec["cents"])
    deltas = []
    for t0 in _contact_onsets(rec):
        pre = sp[max(0, t0 - WIN):t0]
        post = sp[t0:t0 + WIN]
        if np.isfinite(pre).sum() and np.isfinite(post).sum():
            deltas.append(np.nanmean(post) - np.nanmean(pre))
    return float(np.mean(deltas)) if len(deltas) >= MIN_EVENTS else np.nan


def rounding_on_contact(rec):
    """Fraction of contact-onset events followed by spread→rounded in WIN."""
    st = rec["states"]
    hits = []
    for t0 in _contact_onsets(rec):
        if str(st[t0 - 1]) == SPREAD:
            after = [str(st[t]) for t in range(t0, min(t0 + WIN + 1, len(st)))]
            hits.append(1.0 if ROUNDED in after else 0.0)
    return float(np.mean(hits)) if len(hits) >= MIN_EVENTS else np.nan


def _per_recording(recs, fn):
    """{cond: [per-recording mean of fn over its cells]}."""
    by = {}
    for r in recs:
        by.setdefault((r["cond"], r["label"]), []).append(r)
    out = {c: [] for c in ft.CONDITIONS}
    for (cond, _label), cells in by.items():
        if cond not in out:
            continue
        vals = np.array([fn(c) for c in cells], float)
        vals = vals[np.isfinite(vals)]
        if vals.size:
            out[cond].append(float(vals.mean()))
    return out


METRICS = [
    ("state-transition rate (per frame)", transition_rate),
    ("dwell time spread (min)", lambda r: dwell_median(r, SPREAD)),
    ("dwell time rounded (min)", lambda r: dwell_median(r, ROUNDED)),
    ("contact response Δspeed (µm/min)", contact_response),
    ("rounding-on-contact fraction", rounding_on_contact),
]


def run():
    recs = ft.tracks()
    print("=== DYNAMICS (recording-level arm tests) ===")
    results = {}
    for name, fn in METRICS:
        by = _per_recording(recs, fn)
        ns = {c: len(v) for c, v in by.items()}
        meds = {c: (float(np.median(v)) if v else float("nan"))
                for c, v in by.items()}
        print(f"\n  {name}")
        print("    median by cond: " +
              ", ".join(f"{c}={meds[c]:.3g}(n={ns[c]})" for c in ft.CONDITIONS))
        results[name] = {"by_cond_median": meds, "n": ns,
                         "tests": ft.print_arm_tests(name, by)}
    return results
