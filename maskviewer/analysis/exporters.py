"""Assemble analysis tables from a label stack and write CSV for Origin etc.

Three tidy tables (one row = one observation, headers carry units) suitable for
direct import into Origin / Prism / pandas:

  * ``per_frame_table`` — one row per (cell, frame): area + shape morphometry.
    This is the "masks as data" export (region properties of every mask).
  * ``per_cell_table``  — one row per cell: track summary + shape + motion.
  * ``track_table``     — long-format centroid trajectories (px and µm).

All return pandas DataFrames; ``write_csv`` / ``export_all`` persist them.
Pure / GUI-free — driven only by a ``(T, H, W)`` int label array plus optional
physical scale (µm/px) and frame interval (min). Build new exports here.
"""
from __future__ import annotations

import os

import numpy as np

from . import label_stats, cell_metrics, motion, edge_dynamics, contacts


def per_frame_table(labels, um_per_px=None, dt_min=None, with_solidity=False,
                    progress_cb=None, with_contacts=True):
    """DataFrame: one row per (cell, frame) with region/shape metrics."""
    import pandas as pd
    recs = cell_metrics.per_frame_records(np.asarray(labels), um_per_px, dt_min,
                                          with_solidity, progress_cb=progress_cb,
                                          with_contacts=with_contacts)
    return pd.DataFrame(recs)


def track_table(labels, um_per_px=None, dt_min=None):
    """DataFrame: long-format centroid trajectories (skips absent frames)."""
    import pandas as pd
    labels = np.asarray(labels)
    cents = label_stats.centroids(labels)            # {cid: (T,2) row,col px}
    scale = float(um_per_px) if um_per_px else None
    rows = []
    for cid in sorted(cents):
        cen = cents[cid]
        for t in range(cen.shape[0]):
            r, c = cen[t]
            if not np.isfinite(r):
                continue
            row = {"cell_id": int(cid), "frame": int(t)}
            if dt_min:
                row["time_min"] = t * float(dt_min)
            row["centroid_x"] = float(c)
            row["centroid_y"] = float(r)
            if scale:
                row["centroid_x_um"] = float(c) * scale
                row["centroid_y_um"] = float(r) * scale
            rows.append(row)
    return pd.DataFrame(rows)


def contact_pairs_table(labels, um_per_px=None, dt_min=None):
    """DataFrame: one row per cell **pair** that touches — which cells, when
    (first/last frame, frames-in-contact, episodes) and the contact degree.

    Always carries the full column header (even with no contacts) so the CSV is
    readable when a recording has 0 cell pairs (e.g. a single-cell crop)."""
    import pandas as pd
    scale = float(um_per_px) if um_per_px else 1.0
    cols = ["cell_a", "cell_b", "first_frame", "last_frame", "n_frames_in_contact",
            "n_episodes", "mean_episode_min" if dt_min else "mean_episode_frames",
            "mean_contact_fraction", "max_contact_fraction"]
    return pd.DataFrame(contacts.contact_pairs(np.asarray(labels), scale, dt_min),
                        columns=cols)


def per_cell_table(labels, um_per_px=None, dt_min=None, with_solidity=False,
                   per_frame_df=None, with_edge=False, centroids=None,
                   progress_cb=None):
    """DataFrame: one row per cell — track length, shape aggregates, motion.

    Shape columns are per-track means/medians of the per-frame morphometry;
    motion columns come from the centroid trajectory (µm if scaled, per-minute
    if a frame interval is given). ``straightness`` is the speed-biased net/path
    ratio; ``persistence_dir_autocorr`` is the unbiased lag-1 measure. Pass
    ``per_frame_df`` to reuse an already-computed per-frame table (avoids a
    second regionprops pass when exporting both tables). ``progress_cb(done,
    total)`` drives a GUI progress bar (per frame, during the regionprops pass).
    """
    import pandas as pd
    labels = np.asarray(labels)
    pf = per_frame_table(labels, um_per_px, dt_min, with_solidity,
                         progress_cb=progress_cb) \
        if per_frame_df is None else per_frame_df
    cents = label_stats.centroids(labels) if centroids is None else centroids
    scale = float(um_per_px) if um_per_px else 1.0
    u = "um" if um_per_px else "px"
    speed_u = f"{u}_per_min" if dt_min else f"{u}_per_frame"
    agg_cols = ["area_px", "area_um2", f"perimeter_{u}", "circularity",
                "eccentricity", "aspect_ratio", "major_axis_px", "minor_axis_px",
                "extent", "solidity", f"nn_dist_{u}", "n_neighbors",
                "contact_fraction", "n_contacts", "max_contact_fraction",
                f"contact_length_{u}"]
    rows = []
    for cid in sorted(cents):
        cen = cents[cid]
        present = np.isfinite(cen).all(axis=1)
        frames = np.where(present)[0]
        sub = pf[pf["cell_id"] == cid] if not pf.empty else pf
        row = {
            "cell_id": int(cid),
            "first_frame": int(frames[0]) if frames.size else -1,
            "last_frame": int(frames[-1]) if frames.size else -1,
            "frames_tracked": int(present.sum()),
        }
        # distance from the centroid to the nearest image border (crowding /
        # edge-proximity QC) — min over present frames + the mean
        if labels.ndim == 3 and cen.ndim == 2 and frames.size:
            H, W = labels.shape[1], labels.shape[2]
            bd = np.minimum.reduce([cen[present, 1], cen[present, 0],
                                    (W - 1) - cen[present, 1],
                                    (H - 1) - cen[present, 0]])
            row[f"min_border_dist_{u}"] = float(bd.min()) * scale
            row[f"mean_border_dist_{u}"] = float(bd.mean()) * scale
        for col in agg_cols:
            if col in getattr(sub, "columns", []):
                vals = sub[col].to_numpy(dtype=float)
                if np.isfinite(vals).any():
                    row[f"mean_{col}"] = float(np.nanmean(vals))
                    row[f"median_{col}"] = float(np.nanmedian(vals))
        if "state" in getattr(sub, "columns", []):       # time-in-state fractions
            st = sub["state"].to_numpy()
            cls = st[(st == "rounded") | (st == "spread")]
            n = cls.size
            row["frac_rounded"] = float((cls == "rounded").sum() / n) if n else np.nan
            row["frac_spread"] = float((cls == "spread").sum() / n) if n else np.nan
        if "contact_state" in getattr(sub, "columns", []):   # time-in-contact-class
            ss_c = sub.sort_values("frame")
            cs = ss_c["contact_state"].to_numpy()
            n = cs.size
            row["frac_in_contact"] = float((cs != "free").sum() / n) if n else np.nan
            row["frac_point_contact"] = float((cs == "point").sum() / n) if n else np.nan
            row["frac_extensive_contact"] = float((cs == "extensive").sum() / n) if n else np.nan
            # contact-episode dynamics (formation/breakage frequency + duration)
            n_ev, durs = contacts.contact_episodes(ss_c["frame"].to_numpy(), cs != "free")
            row["n_contact_events"] = int(n_ev)
            md = float(np.mean(durs)) if durs else 0.0
            tot = n * (float(dt_min) if dt_min else 1.0)
            if dt_min:
                row["mean_contact_duration_min"] = md * float(dt_min)
                row["contact_events_per_min"] = float(n_ev / tot) if tot else 0.0
            else:
                row["mean_contact_duration_frames"] = md
                row["contact_events_per_frame"] = float(n_ev / tot) if tot else 0.0
        m = motion.motion_summary(cen * scale, dt_min)
        row[f"net_disp_{u}"] = m["net_disp"]
        row[f"total_path_{u}"] = m["total_path"]
        row["straightness"] = m["straightness"]
        row[f"mean_speed_{speed_u}"] = m["mean_speed"]
        row["persistence_dir_autocorr"] = m["dir_autocorr_lag1"]
        # Fürth / persistent-random-walk fit (D + persistence time)
        tau, msdv = motion.msd(cen * scale, dt_min)
        fu = motion.fit_furth(tau, msdv)
        row[f"furth_D_{u}2_per_min" if dt_min else "furth_D"] = fu["D"]
        row["persistence_time_min" if dt_min else "persistence_time"] = \
            fu["persistence_time"]
        # run-and-tumble decomposition (directed runs vs reorientation tumbles)
        rt = motion.run_and_tumble(cen * scale, dt_min)
        row["n_runs"] = rt["n_runs"]
        row["mean_run_steps"] = rt["mean_run_steps"]
        row["frac_tumble"] = rt["frac_tumble"]
        row["mean_tumble_angle_deg"] = rt["mean_tumble_angle_deg"]
        if dt_min:
            row["mean_run_duration_min"] = rt["mean_run_duration"]
            row["tumble_rate_per_min"] = rt["tumble_rate"]
        else:
            row["tumble_rate_per_frame"] = rt["tumble_rate"]
        # track-continuity QC: displacement-outlier steps (suspected ID swaps)
        nj, max_step, frac_j = motion.jump_steps(cen * scale)
        row["n_track_jumps"] = nj
        row[f"max_step_{u}"] = max_step
        row["frac_track_jumps"] = frac_j
        # density-stratified speed + isolation (contact-inhibition readout)
        area_col = "area_um2" if um_per_px else "area_px"
        if not getattr(sub, "empty", True):
            ss = sub.sort_values("frame")
            fr_present = ss["frame"].to_numpy()
            nn = ss.get("n_neighbors")
            cp = cen[fr_present] * scale
            if nn is not None and cp.shape[0] >= 2:
                nn = nn.to_numpy()
                seg = np.sqrt((np.diff(cp, axis=0) ** 2).sum(axis=1))
                sp = seg / float(dt_min) if dt_min else seg
                iso, crd = sp[nn[1:] == 0], sp[nn[1:] > 0]
                row[f"speed_isolated_{speed_u}"] = float(iso.mean()) if iso.size else np.nan
                row[f"speed_crowded_{speed_u}"] = float(crd.mean()) if crd.size else np.nan
                row["frac_isolated"] = float((nn == 0).mean())
            ac = ss[area_col].to_numpy(float)
            ac = ac[np.isfinite(ac)]
            if ac.size:
                mean_a = ac.mean()
                row["area_cv"] = float(ac.std() / mean_a) if mean_a else np.nan
                row["area_max_min_ratio"] = float(ac.max() / ac.min()) if ac.min() > 0 else np.nan
                rel = np.abs(np.diff(ac)) / ac[:-1] if ac.size > 1 else np.array([])
                row["n_large_area_jumps"] = int((rel > 0.3).sum())
        # composite track-quality score (0–1)
        frames_score = present.sum() / labels.shape[0]
        area_score = max(0.0, 1.0 - row.get("area_cv", 1.0))
        path_score = min((m["total_path"] or 0.0) / 50.0, 1.0)
        row["track_quality"] = float(0.5 * frames_score + 0.3 * area_score
                                     + 0.2 * path_score)
        if with_edge:
            for k, v in edge_dynamics.edge_summary_for_cell(
                    labels, int(cid), um_per_px, dt_min).items():
                row[f"edge_{k}"] = v
        rows.append(row)
    return pd.DataFrame(rows)


# --------------------------------------------------------------- writing
def write_csv(df, path: str) -> str:
    df.to_csv(path, index=False)
    return path


def export_all(labels, um_per_px=None, dt_min=None, out_dir=".", prefix="",
               which=("per_frame", "per_cell", "tracks"), with_solidity=False,
               with_edge=False, progress_cb=None):
    """Write the requested tables as ``<out_dir>/<prefix><name>.csv``.

    The per-frame regionprops pass (the slow part) runs once and is shared by
    the per_frame and per_cell tables. ``progress_cb(done, total)`` drives a GUI
    bar from that pass. Returns {name: path}.
    """
    os.makedirs(out_dir, exist_ok=True)
    labels = np.asarray(labels)
    paths = {}
    pf = None
    if "per_frame" in which or "per_cell" in which:
        pf = per_frame_table(labels, um_per_px, dt_min, with_solidity,
                             progress_cb=progress_cb)
    if "per_frame" in which:
        paths["per_frame"] = write_csv(pf, os.path.join(out_dir, f"{prefix}per_frame.csv"))
    if "per_cell" in which:
        pc = per_cell_table(labels, um_per_px, dt_min, with_solidity,
                            per_frame_df=pf, with_edge=with_edge)
        paths["per_cell"] = write_csv(pc, os.path.join(out_dir, f"{prefix}per_cell.csv"))
    if "tracks" in which:
        tr = track_table(labels, um_per_px, dt_min)
        paths["tracks"] = write_csv(tr, os.path.join(out_dir, f"{prefix}tracks.csv"))
    if "contact_pairs" in which:
        cp = contact_pairs_table(labels, um_per_px, dt_min)
        paths["contact_pairs"] = write_csv(
            cp, os.path.join(out_dir, f"{prefix}contact_pairs.csv"))
    if progress_cb:
        progress_cb(1, 1)
    return paths
