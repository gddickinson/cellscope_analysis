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

from . import exporters, cell_metrics, motion

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
        df = exporters.per_cell_table(masks.labels, rec.um_per_px,
                                      rec.time_interval_min, with_solidity,
                                      centroids=cents)
        if df.empty:
            continue
        df = df.copy()
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


def ensemble_by_condition(msd_long, stat="mean", n_boot=400):
    """{condition: (tau, centre, lo, hi)} ensemble MSD across recordings.

    stat='mean' → mean ± SEM; stat='median' → median + bootstrap 95% CI (over
    recordings). Recording = unit (each recording contributes one MSD curve).
    """
    out = {}
    if msd_long is None or msd_long.empty:
        return out
    rng = np.random.default_rng(0)
    for cond, g in msd_long.groupby("condition"):
        taus = np.sort(g["tau"].unique())
        centre, lo, hi = [], [], []
        for tau in taus:
            v = g[g["tau"] == tau]["msd"].to_numpy(float)
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
        out[cond] = (taus, np.array(centre), np.array(lo), np.array(hi))
    return out


def ols_adjusted(per_recording, outcome, covariates=("frac_spread", "mean_n_neighbors")):
    """Per-arm OLS: outcome ~ treatment dummies (vs control) + covariates.

    The covariate-adjusted treatment effect (does it survive the state-time +
    crowding confounds?). Returns [{arm, contrast, coef, p, ci_lo, ci_hi, covs}];
    dependency-free (np.linalg.lstsq + t-tests).
    """
    from . import feature_tables
    from scipy.stats import t as tdist
    df = per_recording
    out = []
    for arm, spec in feature_tables.ARMS.items():
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


def order_conditions(conditions):
    conds = list(conditions)
    return ([c for c in ARM_ORDER if c in conds]
            + sorted(c for c in conds if c not in ARM_ORDER))


def by_condition(per_recording, metric):
    """{condition: [per-recording values]} for arm tests (recording = unit)."""
    out = {}
    for cond, g in per_recording.groupby("condition"):
        vals = g[metric].to_numpy(float)
        out[cond] = vals[np.isfinite(vals)].tolist()
    return out
