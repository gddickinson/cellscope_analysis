"""Cross-recording comparison — aggregate per-cell metrics over many recordings,
grouped by condition, with **recording = experimental unit**.

`build_comparison` loads each recording's masks (via its `Entry`) and reuses
`exporters.per_cell_table`, tagging rows with the recording label + condition.
`aggregate` reduces to one row per recording (mean over cells = the unit).
`by_condition` + the IC295 arm structure (`feature_tables.ARMS` / `arm_tests`)
give per-arm Kruskal-Wallis + within-arm Bonferroni + the vehicle test. GUI-free.

Heavy (a per-frame regionprops pass per recording) — call with a progress
callback from a worker thread and cache the result.
"""
from __future__ import annotations

import numpy as np

from . import exporters, cell_metrics, motion, state_metrics

# arm-ordered conditions for display (IC295); others appended alphabetically
ARM_ORDER = ["WT", "GOF", "KO", "DMSO", "Y1", "OT"]
MAX_LAG = 30                      # lags for the ensemble-MSD-by-condition curves
_SKIP = {"cell_id", "first_frame", "last_frame"}


def build_comparison(entries, progress_cb=None, with_solidity=False):
    """(per_cell_df, msd_long_df) across all entries with masks.

    per_cell_df: per-cell rows + recording + condition. msd_long_df: per-recording
    ensemble MSD (mean over cells) in long form (recording, condition, tau, msd).
    ``progress_cb(done, total)`` is called per recording; returning False cancels.
    Recordings without masks/cells are skipped.
    """
    import pandas as pd
    parts, msd_rows = [], []
    n = len(entries)
    for i, e in enumerate(entries):
        if progress_cb and progress_cb(i, n) is False:
            break
        masks = e.load_masks()
        if masks is None:
            continue
        rec = e.load_recording()
        cents = cell_metrics.centroid_history(masks.labels)   # reused below + by per_cell
        pf = exporters.per_frame_table(masks.labels, rec.um_per_px,
                                       rec.time_interval_min, with_solidity)
        df = exporters.per_cell_table(masks.labels, rec.um_per_px,
                                      rec.time_interval_min, with_solidity,
                                      per_frame_df=pf, centroids=cents)
        if df.empty:
            continue
        df = df.copy()
        # state-segmented metrics (rounded vs spread) — match the original
        # CellScope state-aware analysis; merged alongside the whole-track ones.
        sdf = state_metrics.per_cell_state_metrics(
            masks.labels, rec.um_per_px, rec.time_interval_min, per_frame_df=pf)
        if not sdf.empty:
            df = df.merge(sdf, on="cell_id", how="left")
        df["recording"] = e.label
        df["condition"] = e.condition or "?"
        parts.append(df)
        scale = rec.um_per_px or 1.0
        dt = rec.time_interval_min or 1.0
        mat = np.full((len(cents), MAX_LAG), np.nan)
        for j, cen in enumerate(cents.values()):
            _, vals = motion.msd(cen * scale, rec.time_interval_min, max_lag=MAX_LAG)
            mat[j, :vals.size] = vals
        import warnings
        with warnings.catch_warnings():               # all-NaN lag columns are fine
            warnings.simplefilter("ignore", RuntimeWarning)
            ens = np.nanmean(mat, axis=0) if mat.shape[0] else np.full(MAX_LAG, np.nan)
        for k in range(MAX_LAG):
            if np.isfinite(ens[k]):
                msd_rows.append({"recording": e.label, "condition": e.condition or "?",
                                 "tau": (k + 1) * dt, "msd": float(ens[k])})
    if progress_cb:
        progress_cb(n, n)
    per_cell = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    msd = pd.DataFrame(msd_rows) if msd_rows else pd.DataFrame()
    return per_cell, msd


def ensemble_by_condition(msd_long, stat="mean", n_boot=400, bin_min=0, max_lag=0):
    """{condition: (tau, centre, lo, hi)} ensemble MSD across recordings.

    stat='mean' → mean ± SEM; stat='median' → median + bootstrap 95% CI (over
    recordings). Recording = unit (each recording contributes one MSD curve).
    ``bin_min`` > 0 coarsens the lag axis: lags are grouped into ``bin_min``-wide
    bins and pooled (smooths noisy long lags); each bin is plotted at the *mean*
    of the real lags it holds (so the x never drops below the smallest lag) — a
    display-time rebinning, no recompute. With ``bin_min`` = 0 the native lags
    (one frame interval apart) are used unchanged. ``max_lag`` > 0 keeps only the
    first ``max_lag`` lags/bins (drops noisy long τ) — also display-time.
    """
    out = {}
    if msd_long is None or msd_long.empty:
        return out
    binned = bool(bin_min and bin_min > 0)
    if binned:
        msd_long = msd_long.copy()
        msd_long["_bin"] = np.floor(msd_long["tau"] / bin_min).astype(int)
    rng = np.random.default_rng(0)
    for cond, g in msd_long.groupby("condition"):
        if binned:
            buckets = [(float(sub["tau"].mean()), sub)
                       for _, sub in g.groupby("_bin")]
            buckets.sort()
        else:
            buckets = [(t, g[g["tau"] == t]) for t in np.sort(g["tau"].unique())]
        taus, centre, lo, hi = [], [], [], []
        for tau, sub in buckets:
            taus.append(tau)
            v = sub["msd"].to_numpy(float)
            v = v[np.isfinite(v)]
            if v.size == 0:
                centre.append(np.nan); lo.append(np.nan); hi.append(np.nan)
            elif stat == "median":
                centre.append(float(np.median(v)))
                if v.size > 1:
                    bs = np.median(rng.choice(v, size=(n_boot, v.size)), axis=1)
                    lo.append(float(np.percentile(bs, 2.5)))
                    hi.append(float(np.percentile(bs, 97.5)))
                else:
                    lo.append(centre[-1]); hi.append(centre[-1])
            else:
                mean = float(v.mean())
                sem = float(v.std(ddof=1) / np.sqrt(v.size)) if v.size > 1 else 0.0
                centre.append(mean); lo.append(mean - sem); hi.append(mean + sem)
        n = max_lag if (max_lag and max_lag > 0) else None     # keep first N lags
        out[cond] = (np.array(taus[:n]), np.array(centre[:n]),
                     np.array(lo[:n]), np.array(hi[:n]))
    return out


def ols_adjusted(per_recording, outcome, covariates=("frac_spread", "mean_n_neighbors"),
                 arms=None):
    """Per-arm OLS: outcome ~ treatment dummies (vs control) + covariates.

    The covariate-adjusted treatment effect (does it survive the state-time +
    crowding confounds?). Returns [{arm, contrast, coef, p, ci_lo, ci_hi, covs}];
    dependency-free (np.linalg.lstsq + t-tests).
    """
    from . import feature_tables
    from scipy.stats import t as tdist
    use_arms = feature_tables.ARMS if arms is None else arms
    df = per_recording
    out = []
    for arm, spec in use_arms.items():
        conds, ctrl = spec["conditions"], spec["control"]
        tests = [c for c in conds if c != ctrl]
        sub = df[df["condition"].isin(conds)]
        cov = []
        for c in covariates:                              # keep covariates that vary
            if c in sub.columns:
                vv = sub[c].to_numpy(float)
                vv = vv[np.isfinite(vv)]
                if vv.size > 1 and vv.std() > 0:
                    cov.append(c)
        if sub.empty or not tests:
            continue
        y = sub[outcome].to_numpy(float)
        X = np.column_stack([np.ones(len(sub))]
                            + [(sub["condition"] == t).to_numpy(float) for t in tests]
                            + [sub[c].to_numpy(float) for c in cov])
        ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
        y, X = y[ok], X[ok]
        dof = X.shape[0] - X.shape[1]
        if dof <= 0:
            continue
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        resid = y - X @ beta
        try:
            cov_b = (resid @ resid) / dof * np.linalg.inv(X.T @ X)
        except np.linalg.LinAlgError:
            continue
        se = np.sqrt(np.diag(cov_b))
        crit = float(tdist.ppf(0.975, dof))
        for ti, t_ in enumerate(tests, start=1):
            b, s = float(beta[ti]), float(se[ti])
            p = float(2 * tdist.sf(abs(b / s), dof)) if s > 0 else np.nan
            out.append({"arm": arm, "contrast": f"{t_} vs {ctrl}", "coef": b,
                        "p": p, "ci_lo": b - crit * s, "ci_hi": b + crit * s,
                        "covs": cov})
    return out


def save_results(path, per_cell, msd, meta=None):
    """Pickle the computed comparison results (per-cell + ensemble-MSD frames +
    a small meta dict: project name, design, exclusions) so they can be reloaded
    and re-plotted later without the raw masks. GUI-free."""
    import pickle
    with open(path, "wb") as f:
        pickle.dump({"per_cell": per_cell, "msd": msd, "meta": meta or {}}, f)
    return path


def load_results(path):
    """Inverse of `save_results` → {'per_cell', 'msd', 'meta'}."""
    import pickle
    with open(path, "rb") as f:
        return pickle.load(f)


def aggregate(per_cell):
    """One row per recording: mean over cells of every numeric metric (+ n_cells)."""
    if per_cell is None or per_cell.empty:
        return per_cell
    num = per_cell.select_dtypes(include="number")
    per_rec = num.groupby(per_cell["recording"]).mean()
    per_rec["condition"] = per_cell.groupby("recording")["condition"].first()
    per_rec["n_cells"] = per_cell.groupby("recording").size()
    return per_rec.reset_index()


def metric_columns(per_cell):
    return [c for c in per_cell.columns
            if c not in _SKIP and c not in ("recording", "condition")
            and np.issubdtype(per_cell[c].dtype, np.number)]


def order_conditions(conditions, order=None):
    order = order or ARM_ORDER
    conds = list(conditions)
    return ([c for c in order if c in conds]
            + sorted(c for c in conds if c not in order))


def cohens_d(control, test):
    """Cohen's d (test − control), pooled SD. NaN if either group < 2."""
    a = np.asarray(control, float)
    a = a[np.isfinite(a)]
    b = np.asarray(test, float)
    b = b[np.isfinite(b)]
    if a.size < 2 or b.size < 2:
        return np.nan
    sp = np.sqrt(((a.size - 1) * a.var(ddof=1) + (b.size - 1) * b.var(ddof=1))
                 / (a.size + b.size - 2))
    return float((b.mean() - a.mean()) / sp) if sp > 0 else np.nan


def effect_sizes(by_cond, arms=None):
    """[{arm, contrast, n_ctrl, n_test, cohen_d}] per within-arm test vs control."""
    from . import feature_tables
    use_arms = feature_tables.ARMS if arms is None else arms
    out = []
    for arm, spec in use_arms.items():
        ctrl = spec["control"]
        for t in [c for c in spec["conditions"] if c != ctrl]:
            a, b = by_cond.get(ctrl, []), by_cond.get(t, [])
            out.append({"arm": arm, "contrast": f"{t} vs {ctrl}",
                        "n_ctrl": len(a), "n_test": len(b),
                        "cohen_d": cohens_d(a, b)})
    return out


def per_condition_summary(per_recording, metric):
    """[{group, n, mean, sem, median}] over recordings, per condition (unit=rec).

    The tabular companion to the distribution plots (the Data tab); ``n`` is the
    number of recordings contributing, not cells.
    """
    out = []
    if (per_recording is None or per_recording.empty
            or metric not in per_recording.columns):
        return out
    for cond, g in per_recording.groupby("condition"):
        v = g[metric].to_numpy(float)
        v = v[np.isfinite(v)]
        if v.size == 0:
            continue
        sem = float(v.std(ddof=1) / np.sqrt(v.size)) if v.size > 1 else 0.0
        out.append({"group": cond, "n": int(v.size), "mean": float(v.mean()),
                    "sem": sem, "median": float(np.median(v))})
    return out


def by_condition(per_recording, metric):
    """{condition: [per-recording values]} for arm tests (recording = unit)."""
    out = {}
    for cond, g in per_recording.groupby("condition"):
        vals = g[metric].to_numpy(float)
        out[cond] = vals[np.isfinite(vals)].tolist()
    return out
