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


def _resolve_channel(rec, channel):
    """Channel index for a name/index against a recording, or None if absent."""
    if channel is None or rec is None:
        return None
    names = list(getattr(rec, "channel_names", []) or [])
    if isinstance(channel, str):
        return names.index(channel) if channel in names else None
    ch = int(channel)
    return ch if 0 <= ch < rec.n_channels else None


def _mean_curve_rows(arrays, width, tau_of, label, cond, value_col, skip=0):
    """Mean-over-cells ensemble curve → long rows {recording, condition, tau, value}.
    Each array is one cell's curve (indexed from 0); padded to `width`, NaN-averaged over
    cells; `tau_of(k)` maps the column index to the τ value; `skip` drops leading columns."""
    import warnings
    if not arrays or width <= 0:
        return []
    mat = np.full((len(arrays), width), np.nan)
    for j, a in enumerate(arrays):
        m = min(a.size, width)
        mat[j, :m] = a[:m]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        ens = np.nanmean(mat, axis=0)
    return [{"recording": label, "condition": cond, "tau": tau_of(k), value_col: float(ens[k])}
            for k in range(skip, width) if np.isfinite(ens[k])]


def build_comparison(entries, progress_cb=None, with_solidity=False, max_lag=MAX_LAG,
                     piezo_channel=None, corrections=None, scale_override=None,
                     with_contacts=True, with_state_segmented=True, with_edge=False,
                     with_cil=False, with_fluor_metrics=False, with_shape_modes=False):
    """(per_cell_df, msd, autocorr, dir_ratio, velcorr) across all entries with masks.

    per_cell_df: per-cell rows + recording + condition. The other four are
    per-recording ensemble curves (mean over cells) in long form
    (recording, condition, tau, value) — the **DiPer** family, all matched to
    `diper_clone`: ensemble **MSD**, **direction autocorrelation**, **directionality
    ratio** d/D over elapsed time (`tau`=elapsed min, `dir_ratio`), and **normalized
    velocity autocorrelation** (`velcorr`). MSD / autocorr go up to ``max_lag``
    lags. ``with_contacts`` / ``with_state_segmented`` / ``with_solidity`` gate the
    optional (heavier) analysis families — the Config ▸ Comparison-analysis toggles.
    ``piezo_channel`` (channel name or index) → also add
    per-cell **edge-movement ↔ fluorescence-intensity** columns (`edge_piezo_corr`
    = Pearson r, `edge_piezo_slope`, `piezo_protr_minus_retr`; via `edge_intensity`,
    the faithful ``cell_edge_analysis`` reproduction). ``progress_cb(done, total)``
    is called per recording; returning False cancels. Recordings w/o cells skip.
    """
    import pandas as pd
    from . import edge_intensity, fov as fov_mod
    from ..io import recording as _recording
    max_lag = int(max_lag) if max_lag and max_lag > 0 else MAX_LAG
    corrections = corrections or {}
    parts, msd_rows, ac_rows, dr_rows, vc_rows = [], [], [], [], []
    n = len(entries)
    for i, e in enumerate(entries):
        if progress_cb and progress_cb(i, n) is False:
            break
        masks = e.load_masks()
        if masks is None:
            continue
        rec = e.load_recording()
        if scale_override:                            # manual µm/px + min/frame overrides
            px, dt = scale_override
            if px:
                rec.um_per_px = float(px)
            if dt:
                rec.time_interval_min = float(dt)
        # pre-analysis corrections: align fluor channels + crop to the FOV
        _recording.apply_correction(rec, corrections.get(e.label))
        labels = fov_mod.apply_fov(masks.labels, rec.fov) if rec.fov else masks.labels
        cents = cell_metrics.centroid_history(labels)         # reused below + by per_cell
        pf = exporters.per_frame_table(labels, rec.um_per_px,
                                       rec.time_interval_min, with_solidity,
                                       with_contacts=with_contacts)
        df = exporters.per_cell_table(labels, rec.um_per_px,
                                      rec.time_interval_min, with_solidity,
                                      per_frame_df=pf, centroids=cents, with_edge=with_edge)
        if df.empty:
            continue
        df = df.copy()
        # state-segmented metrics (rounded vs spread) — match the original
        # CellScope state-aware analysis; merged alongside the whole-track ones.
        if with_state_segmented:
            sdf = state_metrics.per_cell_state_metrics(
                labels, rec.um_per_px, rec.time_interval_min, per_frame_df=pf)
            if not sdf.empty:
                df = df.merge(sdf, on="cell_id", how="left")
        if with_cil:                                  # contact-inhibition of locomotion
            from . import cil
            cldf = cil.contact_locomotion_table(labels, rec.um_per_px,
                                                rec.time_interval_min)
            if not cldf.empty:
                df = df.merge(cldf, on="cell_id", how="left")
        if with_fluor_metrics and getattr(rec, "n_channels", 0):  # per-channel intensity
            from . import intensity_metrics
            fldf = intensity_metrics.per_cell_fluor_table(labels, rec)
            if not fldf.empty:
                df = df.merge(fldf, on="cell_id", how="left")
        if with_shape_modes:                          # VAMPIRE per-cell shape usage
            from . import shape_modes, cache as _cache
            model = _cache.load_or_compute(
                _cache.content_key("shape_modes", labels, n_modes=shape_modes.N_MODES,
                                   n_pcs=shape_modes.N_PCS),
                lambda: shape_modes.fit_shape_modes(labels))
            sm = shape_modes.per_cell_shape_summary(model)
            if sm:
                smdf = pd.DataFrame([{"cell_id": c, **v} for c, v in sm.items()])
                df = df.merge(smdf, on="cell_id", how="left")
        ch = _resolve_channel(rec, piezo_channel)
        if ch is not None:                            # edge movement ↔ intensity
            image = rec.aligned_channel(ch)
            prows = []
            for cid in df["cell_id"]:
                *_, summ = edge_intensity.analyze_cell(
                    labels, image, int(cid), rec.um_per_px, rec.time_interval_min)
                prows.append({"cell_id": int(cid),
                              "edge_piezo_corr": summ["edge_move_intensity_r"],
                              "edge_piezo_slope": summ["edge_move_intensity_slope"],
                              "piezo_protr_minus_retr": summ["piezo_protr_minus_retr"],
                              "edge_piezo_peak_lag": summ.get("edge_intensity_peak_lag"),
                              "edge_piezo_peak_r": summ.get("edge_intensity_peak_r")})
            df = df.merge(pd.DataFrame(prows), on="cell_id", how="left")
        df["recording"] = e.label
        df["condition"] = e.condition or "?"
        parts.append(df)
        scale = rec.um_per_px or 1.0
        dt = rec.time_interval_min or 1.0
        cc, cond = list(cents.values()), e.condition or "?"
        # ensemble curves per recording (mean over cells), all matched to diper_clone
        msd_rows += _mean_curve_rows(
            [motion.msd(c * scale, None, max_lag=max_lag)[1] for c in cc],
            max_lag, lambda k: (k + 1) * dt, e.label, cond, "msd")        # MSD (µm²)
        ac_rows += _mean_curve_rows(
            [motion.direction_autocorrelation(c, max_lag=max_lag) for c in cc],
            max_lag + 1, lambda k: k * dt, e.label, cond, "autocorr", skip=1)
        vc_rows += _mean_curve_rows(
            [motion.velocity_autocorrelation(c, max_lag=max_lag) for c in cc],
            max_lag, lambda k: (k + 1) * dt, e.label, cond, "velcorr")
        dr = [motion.directionality_ratio(c * scale)[1] for c in cc]      # vs elapsed t
        dr_rows += _mean_curve_rows(dr, max((a.size for a in dr), default=0),
                                    lambda k: k * dt, e.label, cond, "dir_ratio")
    if progress_cb:
        progress_cb(n, n)
    per_cell = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    frame = lambda rows: pd.DataFrame(rows) if rows else pd.DataFrame()
    return (per_cell, frame(msd_rows), frame(ac_rows), frame(dr_rows), frame(vc_rows))


def ensemble_by_condition(msd_long, stat="mean", n_boot=400, bin_min=0, max_lag=0,
                          value_col="msd"):
    """{condition: (tau, centre, lo, hi)} ensemble curve across recordings —
    MSD (``value_col='msd'``) or direction autocorrelation (``'autocorr'``).

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
            v = sub[value_col].to_numpy(float)
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


def save_results(path, per_cell, msd, meta=None, autocorr=None, dir_ratio=None,
                 velcorr=None):
    """Pickle the computed comparison results (per-cell + the ensemble DiPer curve
    frames: MSD, direction autocorrelation, directionality ratio, velocity
    autocorrelation + a small meta dict) for reload/replot without the raw masks."""
    import pickle
    with open(path, "wb") as f:
        pickle.dump({"per_cell": per_cell, "msd": msd, "autocorr": autocorr,
                     "dir_ratio": dir_ratio, "velcorr": velcorr, "meta": meta or {}}, f)
    return path


def load_results(path):
    """Inverse of `save_results` → {'per_cell', 'msd', 'autocorr', 'meta'}."""
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


def ranked_group_comparisons(per_recording, metric, groups=None, per_cell=None,
                             with_ci=True) -> list:
    """**Every** group pair compared on one metric, ranked by the likelihood of a
    significant difference (smallest p first). Recording = unit; Mann-Whitney U
    (two-sided) + Cohen's d, with a **Bonferroni** *and* a **Benjamini-Hochberg FDR**
    correction over the tested pairs, a percentile **bootstrap CI** on Cohen's d, and
    (when ``per_cell`` is given) a cell-nested-in-recording **mixed-model** p.

    Unlike the design-driven per-contrast Stats table (control-vs-test within arms),
    this enumerates *all* unordered group pairs. Returns a list of dicts (group_a,
    group_b, n_a, n_b, mean_a, mean_b, p, p_bonferroni, q_fdr, cohen_d, cohen_d_lo,
    cohen_d_hi, cluster_p), p-ascending."""
    from scipy import stats as _ss
    from . import stats_extra as _se
    cols = getattr(per_recording, "columns", [])
    if per_recording is None or metric not in cols or "condition" not in cols:
        return []
    conds = list(groups) if groups else sorted(
        per_recording["condition"].dropna().unique())
    vals = {}
    for g in conds:
        v = per_recording.loc[per_recording["condition"] == g, metric].to_numpy(float)
        vals[g] = v[np.isfinite(v)]
    rows = []
    for i, a in enumerate(conds):
        for b in conds[i + 1:]:
            va, vb = vals.get(a, np.array([])), vals.get(b, np.array([]))
            p = np.nan
            if (va.size and vb.size and va.size + vb.size >= 3
                    and np.ptp(np.concatenate([va, vb])) > 0):    # skip only all-tied
                try:
                    p = float(_ss.mannwhitneyu(va, vb, alternative="two-sided").pvalue)
                except ValueError:
                    p = np.nan
            rows.append({"group_a": a, "group_b": b,
                         "n_a": int(va.size), "n_b": int(vb.size),
                         "mean_a": float(va.mean()) if va.size else np.nan,
                         "mean_b": float(vb.mean()) if vb.size else np.nan,
                         "p": p, "cohen_d": cohens_d(va, vb)})
    m = sum(1 for r in rows if np.isfinite(r["p"]))
    qs = _se.benjamini_hochberg([r["p"] for r in rows])
    for r, q in zip(rows, qs):
        r["p_bonferroni"] = (min(r["p"] * m, 1.0)
                             if np.isfinite(r["p"]) and m else np.nan)
        r["q_fdr"] = float(q) if np.isfinite(q) else np.nan
        if with_ci:
            r["cohen_d_lo"], r["cohen_d_hi"] = _se.bootstrap_ci(
                vals.get(r["group_a"]), vals.get(r["group_b"]), cohens_d)
        else:
            r["cohen_d_lo"] = r["cohen_d_hi"] = np.nan
        r["cluster_p"] = (_se.cluster_robust_p(
            per_cell[per_cell["condition"].isin([r["group_a"], r["group_b"]])],
            metric) if per_cell is not None and metric in getattr(
            per_cell, "columns", []) else np.nan)
    rows.sort(key=lambda r: (not np.isfinite(r["p"]),
                             r["p"] if np.isfinite(r["p"]) else 1.0))
    return rows


def forest_data(per_recording, group_a, group_b, metrics=None) -> list:
    """For an **effect-size forest plot**: Cohen's d (``group_b`` vs ``group_a``) with a
    95% bootstrap CI + Mann-Whitney p for **every metric**, sorted by |d| descending —
    a one-figure view of where two groups differ most (the multivariate phenotype).
    Recording = unit."""
    from scipy import stats as _ss
    from . import stats_extra as _se
    cols = metrics if metrics is not None else metric_columns(per_recording)
    am = per_recording["condition"] == group_a
    bm = per_recording["condition"] == group_b
    rows = []
    for m in cols:
        va = per_recording.loc[am, m].to_numpy(float); va = va[np.isfinite(va)]
        vb = per_recording.loc[bm, m].to_numpy(float); vb = vb[np.isfinite(vb)]
        if va.size < 2 or vb.size < 2:
            continue
        lo, hi = _se.bootstrap_ci(va, vb, cohens_d)
        try:
            p = float(_ss.mannwhitneyu(va, vb, alternative="two-sided").pvalue)
        except ValueError:
            p = np.nan
        rows.append({"metric": m, "d": cohens_d(va, vb), "lo": lo, "hi": hi, "p": p})
    rows.sort(key=lambda r: -abs(r["d"]) if np.isfinite(r["d"]) else 0.0)
    return rows


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


def multivariate_contrasts(per_recording, arms=None):
    """Per-arm multivariate separation: PERMANOVA p + leave-one-recording-out AUC
    over ALL numeric per-recording metrics (z-scored). Recording = unit. Surfaces
    the multivariate phenotype that single-metric tests can miss (e.g. KO vs WT).
    Returns [{arm, contrast, n_ctrl, n_test, n_features, permanova_p, loro_auc}];
    p/auc are None when a contrast has < 2 recordings/group or < 2 usable metrics.
    """
    from . import feature_tables, multivariate as mv
    use_arms = feature_tables.ARMS if arms is None else arms
    if per_recording is None or per_recording.empty:
        return []
    cols = metric_columns(per_recording)
    out = []
    for arm, spec in use_arms.items():
        ctrl = spec["control"]
        for t in [c for c in spec["conditions"] if c != ctrl]:
            sub = per_recording[per_recording["condition"].isin([ctrl, t])]
            g = sub["condition"]
            n_c, n_t = int((g == ctrl).sum()), int((g == t).sum())
            row = {"arm": arm, "contrast": f"{t} vs {ctrl}", "n_ctrl": n_c,
                   "n_test": n_t, "n_features": 0, "permanova_p": None,
                   "loro_auc": None}
            feats = [c for c in cols
                     if np.isfinite(sub[c].to_numpy(float)).all()
                     and float(np.nanstd(sub[c].to_numpy(float))) > 0]
            if n_c >= 2 and n_t >= 2 and len(feats) >= 2:
                X = sub[feats].to_numpy(float)
                X = (X - X.mean(0)) / X.std(0)
                row["n_features"] = len(feats)
                row["permanova_p"] = float(mv.permanova(X, g.to_numpy())[1])
                row["loro_auc"] = float(mv.loro_auc(X, (g == t).to_numpy(int))[0])
            out.append(row)
    return out


def by_condition(per_recording, metric):
    """{condition: [per-recording values]} for arm tests (recording = unit)."""
    out = {}
    for cond, g in per_recording.groupby("condition"):
        vals = g[metric].to_numpy(float)
        out[cond] = vals[np.isfinite(vals)].tolist()
    return out
