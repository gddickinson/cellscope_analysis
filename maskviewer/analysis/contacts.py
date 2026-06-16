"""Cell–cell **contact** detection + classification (GUI-free).

Distinct from `neighbors.py` (centroid-to-centroid *proximity*): this measures
where two cells' masks actually **share a boundary** — the physical membrane
interface — and how extensive it is. Relevant to contact-inhibition of
locomotion, collective vs single-cell migration, and PIEZO1 mechanosensing at
junctions.

For each frame, two cells are *in contact* where a boundary pixel of one lies
within ``max_gap_px`` of a boundary pixel of the other. (In these masks touching
cells sit edge-to-edge — their boundary pixels are 1 px apart — so the small
default tolerance captures genuine contacts without reaching to merely-nearby
cells.) Per cell we report, per frame:

  * **contact_fraction** — fraction of the cell's boundary engaged with *any*
    other cell (its perimeter pixels in contact ÷ its boundary pixels);
  * **n_contacts** — number of other cells it touches;
  * **contact_length** — interface length (contacting boundary pixels × µm/px);
  * **max_contact_fraction** — the single largest neighbour interface;
  * **contact_class** — ``free`` / ``point`` / ``extensive`` (a small point of
    contact vs an extensive shared interface), split on ``max_contact_fraction``.

Pure functions over ``(H, W)`` / ``(T, H, W)`` int label arrays. The maths is
recomputed in-project from the loaded masks (single source of truth).
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
from scipy.spatial import cKDTree

# touching cells sit at 1 px boundary separation; 1.5 px captures 4- and
# 8-connected adjacency without reaching merely-nearby cells (tunable).
DEFAULT_GAP_PX = 1.5
# a neighbour interface ≥ this fraction of the cell's boundary is "extensive".
EXTENSIVE_FRAC = 0.25
# ignore sub-this contacts (single-pixel diagonal touches → noise).
MIN_CONTACT_PX = 2

CONTACT_CLASSES = ("free", "point", "extensive")
CONTACT_CODE = {"free": 0, "point": 1, "extensive": 2}
CONTACT_COLOR = {"free": (130, 130, 130), "point": (31, 119, 180),
                 "extensive": (214, 39, 40)}


def _resolve(max_gap_px, extensive_frac, min_px):
    """Fill ``None`` args from the (GUI-configurable) module-level defaults, read at
    call time so a Config ▸ Analysis-parameters change applies everywhere."""
    return (DEFAULT_GAP_PX if max_gap_px is None else max_gap_px,
            EXTENSIVE_FRAC if extensive_frac is None else extensive_frac,
            MIN_CONTACT_PX if min_px is None else min_px)


def classify_contact(max_partner_frac, contact_px, extensive_frac=EXTENSIVE_FRAC,
                     min_px=MIN_CONTACT_PX) -> str:
    """Classify a cell's contact state from its largest neighbour interface.

    ``free`` (no real contact), ``point`` (small contact below ``extensive_frac``
    of the boundary) or ``extensive`` (a large shared interface)."""
    if contact_px < min_px or max_partner_frac <= 0.0:
        return "free"
    return "extensive" if max_partner_frac >= extensive_frac else "point"


def _boundary_mask(lab) -> np.ndarray:
    """Cell pixels adjacent (4-connectivity, no wrap) to a different label or
    background — the cells' boundary pixels."""
    diff = np.zeros(lab.shape, bool)
    diff[:-1, :] |= lab[:-1, :] != lab[1:, :]
    diff[1:, :] |= lab[1:, :] != lab[:-1, :]
    diff[:, :-1] |= lab[:, :-1] != lab[:, 1:]
    diff[:, 1:] |= lab[:, 1:] != lab[:, :-1]
    return diff & (lab > 0)


def _free_record(boundary_px, scale) -> dict:
    return {"n_contacts": 0, "boundary_px": int(boundary_px), "contact_px": 0,
            "contact_fraction": 0.0, "max_contact_fraction": 0.0,
            "contact_length": 0.0, "contact_class": "free", "contact_code": 0,
            "partners": {}}


def _contact_pixels(lab, max_gap_px):
    """``(ys, xs, blab, {pix_idx: {partner labels}})`` — boundary pixels, their
    cell labels, and for each the *other* cells within ``max_gap_px``."""
    bmask = _boundary_mask(lab)
    ys, xs = np.nonzero(bmask)
    blab = lab[ys, xs]
    pix_partners: dict[int, set] = {}
    if ys.size >= 2:
        tree = cKDTree(np.column_stack([ys, xs]))
        for i, j in tree.query_pairs(r=float(max_gap_px)):
            a, b = int(blab[i]), int(blab[j])
            if a != b:
                pix_partners.setdefault(i, set()).add(b)
                pix_partners.setdefault(j, set()).add(a)
    return ys, xs, blab, pix_partners


def _boundary_counts(ids, blab):
    bc = {c: 0 for c in ids}
    for c, n in zip(*np.unique(blab, return_counts=True)):
        bc[int(c)] = int(n)
    return bc


def _aggregate(ids, blab, pix_partners, bcount, scale, extensive_frac, min_px):
    """Per-cell contact records from the shared pixel/partner data."""
    out = {c: _free_record(bcount[c], scale) for c in ids}
    if not pix_partners:
        return out
    contact_px = defaultdict(int)                  # cell -> distinct boundary px in contact
    pair_px = defaultdict(lambda: defaultdict(int))  # cell -> {partner: px}
    for i, parts in pix_partners.items():
        c = int(blab[i])
        contact_px[c] += 1
        for p in parts:
            pair_px[c][p] += 1
    for c in ids:
        bc = bcount[c] or 1
        partners = {p: px for p, px in pair_px.get(c, {}).items() if px >= min_px}
        if not partners:
            continue                               # stays the default free record
        cpx = int(contact_px.get(c, 0))
        partner_fracs = {p: px / bc for p, px in partners.items()}
        max_frac = max(partner_fracs.values())
        cls = classify_contact(max_frac, cpx, extensive_frac, min_px)
        out[c] = {"n_contacts": len(partners), "boundary_px": int(bc),
                  "contact_px": cpx, "contact_fraction": float(cpx / bc),
                  "max_contact_fraction": float(max_frac),
                  "contact_length": float(cpx) * float(scale),
                  "contact_class": cls, "contact_code": CONTACT_CODE[cls],
                  "partners": {int(p): float(f) for p, f in partner_fracs.items()}}
    return out


def frame_contacts(lab, scale=1.0, max_gap_px=None,
                   extensive_frac=None, min_px=None) -> dict:
    """``{cell_id: record}`` of contact metrics for every cell in one frame.

    ``scale`` is µm/px (1.0 → px). Every present cell gets a record (``free``
    with zeros when it touches nothing). ``None`` gap/threshold args use the
    configurable module defaults."""
    max_gap_px, extensive_frac, min_px = _resolve(max_gap_px, extensive_frac, min_px)
    lab = np.asarray(lab)
    ids = [int(i) for i in np.unique(lab) if i > 0]
    ys, xs, blab, pix_partners = _contact_pixels(lab, max_gap_px)
    return _aggregate(ids, blab, pix_partners, _boundary_counts(ids, blab),
                      scale, extensive_frac, min_px)


def frame_interfaces(lab, scale=1.0, max_gap_px=None,
                     extensive_frac=None, min_px=None):
    """``(ys, xs, codes)`` of the contacting boundary pixels for one frame — for the
    contact overlay. ``codes`` is the owning cell's contact-class code (1 = point,
    2 = extensive); pixels of cells classed ``free`` are dropped."""
    max_gap_px, extensive_frac, min_px = _resolve(max_gap_px, extensive_frac, min_px)
    lab = np.asarray(lab)
    ids = [int(i) for i in np.unique(lab) if i > 0]
    ys, xs, blab, pix_partners = _contact_pixels(lab, max_gap_px)
    if not pix_partners:
        return np.empty(0, int), np.empty(0, int), np.empty(0, int)
    recs = _aggregate(ids, blab, pix_partners, _boundary_counts(ids, blab),
                      scale, extensive_frac, min_px)
    idx = [i for i in sorted(pix_partners) if recs[int(blab[i])]["contact_code"] > 0]
    codes = np.array([recs[int(blab[i])]["contact_code"] for i in idx], int)
    return ys[idx], xs[idx], codes


def contact_episodes(frames, in_contact):
    """``(n_events, [durations_in_frames])`` of contiguous in-contact runs over a
    cell's present frames — a frame gap (the cell vanished) also breaks a run."""
    frames = np.asarray(frames)
    ic = np.asarray(in_contact, bool)
    durations: list = []
    run = 0
    prev = None
    for f, c in zip(frames.tolist(), ic.tolist()):
        if prev is not None and f != prev + 1 and run:   # a gap closes the run
            durations.append(run)
            run = 0
        if c:
            run += 1
        elif run:
            durations.append(run)
            run = 0
        prev = f
    if run:
        durations.append(run)
    return len(durations), durations


def contacts_over_time(labels, scale=1.0, max_gap_px=None,
                       extensive_frac=None, min_px=None,
                       progress_cb=None) -> list:
    """Per-frame list of ``frame_contacts`` dicts across a ``(T, H, W)`` stack."""
    labels = np.asarray(labels)
    out = []
    for t in range(labels.shape[0]):
        out.append(frame_contacts(labels[t], scale, max_gap_px, extensive_frac, min_px))
        if progress_cb:
            progress_cb(t + 1, labels.shape[0])
    return out


def contact_summary(labels, scale=1.0, max_gap_px=None,
                    extensive_frac=None, min_px=None,
                    per_frame=None, dt_min=None) -> dict:
    """``{cell_id: summary}`` over each track's present frames.

    Summary: ``frac_in_contact`` / ``frac_point_contact`` / ``frac_extensive_contact``
    (time-in-class), ``mean_contact_fraction`` / ``max_contact_fraction``,
    ``mean_n_contacts`` / ``mean_contact_length``, and **contact-episode dynamics**:
    ``n_contact_events`` (distinct in-contact episodes), ``mean_contact_duration``
    (frames, or min if ``dt_min``) and ``contact_event_rate`` (episodes per frame /
    per min). Pass a precomputed ``per_frame`` (``contacts_over_time``) to reuse it."""
    labels = np.asarray(labels)
    pf = per_frame if per_frame is not None else contacts_over_time(
        labels, scale, max_gap_px, extensive_frac, min_px)
    dt = float(dt_min) if dt_min else 1.0
    acc: dict[int, list] = defaultdict(list)
    for t, fc in enumerate(pf):
        for cid, rec in fc.items():
            acc[cid].append((t, rec))
    summary = {}
    for cid, tr in acc.items():
        tr.sort()
        frames = [t for t, _ in tr]
        recs = [r for _, r in tr]
        n = len(recs)
        classes = [r["contact_class"] for r in recs]
        fr = np.array([r["contact_fraction"] for r in recs], float)
        n_ev, durs = contact_episodes(frames, [c != "free" for c in classes])
        summary[int(cid)] = {
            "frac_in_contact": float(sum(c != "free" for c in classes) / n) if n else np.nan,
            "frac_point_contact": float(classes.count("point") / n) if n else np.nan,
            "frac_extensive_contact": float(classes.count("extensive") / n) if n else np.nan,
            "mean_contact_fraction": float(fr.mean()) if n else np.nan,
            "max_contact_fraction": float(max((r["max_contact_fraction"] for r in recs),
                                              default=0.0)),
            "mean_n_contacts": float(np.mean([r["n_contacts"] for r in recs])) if n else np.nan,
            "mean_contact_length": float(np.mean([r["contact_length"] for r in recs])) if n else np.nan,
            "n_contact_events": int(n_ev),
            "mean_contact_duration": (float(np.mean(durs)) * dt) if durs else 0.0,
            "contact_event_rate": float(n_ev / (n * dt)) if n else np.nan,
        }
    return summary


def contact_pairs(labels, scale=1.0, dt_min=None, max_gap_px=None,
                  extensive_frac=None, min_px=None,
                  per_frame=None) -> list:
    """**Which cells touch, when, and how much** — one record per unordered cell pair
    that is in contact in ≥1 frame.

    Each record: ``cell_a`` / ``cell_b``, ``first_frame`` / ``last_frame``,
    ``n_frames_in_contact``, ``n_episodes`` (contiguous contact runs),
    ``mean_episode`` (frames, or min if ``dt_min``), and the contact **degree** over
    the in-contact frames (``mean_contact_fraction`` / ``max_contact_fraction``). The
    per-frame pair degree is the larger of the two cells' boundary fractions engaged
    with the other. Pass a precomputed ``per_frame`` (``contacts_over_time``) to reuse."""
    labels = np.asarray(labels)
    pf = per_frame if per_frame is not None else contacts_over_time(
        labels, scale, max_gap_px, extensive_frac, min_px)
    dt = float(dt_min) if dt_min else 1.0
    pair_deg: dict = defaultdict(dict)                  # (a, b) -> {frame: degree}
    for t, fc in enumerate(pf):
        for cid, rec in fc.items():
            for p, frac in rec.get("partners", {}).items():
                key = (min(int(cid), int(p)), max(int(cid), int(p)))
                pair_deg[key][t] = max(pair_deg[key].get(t, 0.0), float(frac))
    out = []
    for (a, b), fd in sorted(pair_deg.items()):
        frames = sorted(fd)
        degs = np.array([fd[t] for t in frames], float)
        n_ev, durs = contact_episodes(frames, [True] * len(frames))
        out.append({
            "cell_a": a, "cell_b": b,
            "first_frame": frames[0], "last_frame": frames[-1],
            "n_frames_in_contact": len(frames), "n_episodes": int(n_ev),
            ("mean_episode_min" if dt_min else "mean_episode_frames"):
                (float(np.mean(durs)) * dt) if durs else 0.0,
            "mean_contact_fraction": float(degs.mean()),
            "max_contact_fraction": float(degs.max()),
        })
    return out
