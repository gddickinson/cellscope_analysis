"""Motion metrics from centroid tracks (GUI-free).

Works on a per-cell centroid time series ``(T, 2)`` (NaN where the cell is
absent). Distances are Euclidean so the axis order (row,col vs x,y) does not
matter as long as it is consistent and the array is already in physical units.

Two notes carried from the migration literature (see docs/FINDINGS_followup):

* **Straightness** = net / total path length is the classic "persistence
  index", but it is **biased by speed** (Gorelik & Gautreau, Nat Protoc 2014).
  Reported for completeness, but prefer ``direction_autocorrelation``.
* **Direction autocorrelation** (mean cosine between step directions separated
  by a lag) depends only on turning angles, not speed — the unbiased
  persistence measure. Lag-1 is the single-number "directional persistence".
"""
from __future__ import annotations

import numpy as np

# Configurable thresholds (read at call time so a GUI override propagates).
RUN_TUMBLE_TURN_DEG = 60.0       # turning angle above which a step is a "tumble"
JUMP_FACTOR = 5.0                # step length / median above which a step is a "jump"


def _finite_points(cen: np.ndarray) -> np.ndarray:
    cen = np.asarray(cen, float)
    return cen[np.isfinite(cen).all(axis=1)]


def instantaneous_speed(cen: np.ndarray, dt_min: float | None = None) -> np.ndarray:
    """Per-step speed between consecutive finite frames (units/min if dt given).

    Returns one value per consecutive finite step (gaps are bridged as a single
    step). Length 0 if fewer than two finite points.
    """
    pts = _finite_points(cen)
    if pts.shape[0] < 2:
        return np.array([])
    seg = np.sqrt((np.diff(pts, axis=0) ** 2).sum(axis=1))
    return seg / float(dt_min) if dt_min else seg


def displacement_metrics(cen: np.ndarray, dt_min: float | None = None) -> dict:
    """Net displacement, total path, straightness and mean speed for a track.

    ``mean_speed`` is total path ÷ **elapsed time over the track** (the span between
    the first and last present frame), so a track with internal gaps (the cell
    briefly untracked) is not over-stated by dividing by step count alone. Identical
    to the per-step mean for gapless tracks.
    """
    cen = np.asarray(cen, float)
    ok = np.isfinite(cen).all(axis=1)
    pts = cen[ok]
    if pts.shape[0] < 2:
        return {"net_disp": np.nan, "total_path": np.nan, "straightness": np.nan,
                "mean_speed": np.nan, "n_steps": 0}
    seg = np.sqrt((np.diff(pts, axis=0) ** 2).sum(axis=1))
    total = float(seg.sum())
    net = float(np.sqrt(((pts[-1] - pts[0]) ** 2).sum()))
    idx = np.where(ok)[0]
    elapsed = float(idx[-1] - idx[0])                 # frames actually spanned (≥ n_steps)
    return {"net_disp": net, "total_path": total,
            "straightness": net / total if total > 0 else np.nan,
            "mean_speed": (total / (elapsed * float(dt_min))) if dt_min else total / elapsed,
            "n_steps": int(seg.size)}


def direction_autocorrelation(cen: np.ndarray, max_lag: int | None = None) -> np.ndarray:
    """Mean cos(angle) between unit step vectors separated by each lag.

    Index 0 is 1.0; index k is the lag-k directional autocorrelation. Empty if
    fewer than three finite points. Zero-length steps are excluded.
    """
    pts = _finite_points(cen)
    if pts.shape[0] < 3:
        return np.array([])
    steps = np.diff(pts, axis=0)
    norms = np.sqrt((steps ** 2).sum(axis=1))
    ok = norms > 0
    units = np.zeros_like(steps)
    units[ok] = steps[ok] / norms[ok][:, None]
    n = units.shape[0]
    max_lag = min(max_lag or (n - 1), n - 1)
    out = np.full(max_lag + 1, np.nan)
    out[0] = 1.0
    for lag in range(1, max_lag + 1):
        valid = ok[:-lag] & ok[lag:]
        if valid.any():
            out[lag] = float((units[:-lag][valid] * units[lag:][valid]).sum(axis=1).mean())
    return out


def persistence(cen: np.ndarray) -> float:
    """Lag-1 directional autocorrelation — the speed-unbiased persistence."""
    ac = direction_autocorrelation(cen, max_lag=1)
    return float(ac[1]) if ac.size > 1 else np.nan


def msd(cen: np.ndarray, dt_min: float | None = None,
        max_lag: int | None = None) -> tuple:
    """Mean squared displacement curve: (tau, msd). tau in minutes if dt given."""
    pts = _finite_points(cen)
    n = pts.shape[0]
    if n < 2:
        return np.array([]), np.array([])
    lags = np.arange(1, min(max_lag or (n - 1), n - 1) + 1)
    vals = np.array([((pts[lag:] - pts[:-lag]) ** 2).sum(axis=1).mean() for lag in lags])
    tau = lags * float(dt_min) if dt_min else lags.astype(float)
    return tau, vals


def turning_angles(cen: np.ndarray) -> np.ndarray:
    """Signed turn (rad, [-π, π]) between consecutive step directions.

    A joint adjacent to a **zero-length step** (the cell paused — identical
    consecutive centroids) has no defined direction, so it returns NaN rather than
    a phantom turn. (``arctan2(0, 0)`` is 0/"due-east", which would otherwise make a
    straight-but-paused track register two large fake turns — and `run_and_tumble`
    then mis-report it as fully tumbling.)"""
    pts = _finite_points(cen)
    if pts.shape[0] < 3:
        return np.array([])
    steps = np.diff(pts, axis=0)
    norms = np.sqrt((steps ** 2).sum(axis=1))
    ang = np.arctan2(steps[:, 0], steps[:, 1])
    turns = (np.diff(ang) + np.pi) % (2 * np.pi) - np.pi
    turns[(norms[:-1] == 0) | (norms[1:] == 0)] = np.nan   # pause → undefined, not 90°
    return turns


def fit_msd(tau: np.ndarray, msd_vals: np.ndarray) -> dict:
    """Fit MSD = 4·D·τ^α in log-log → {D, alpha, r2}.

    α > 1 superdiffusive/directed, ≈ 1 Brownian, < 1 confined (Saxton; the
    CellScope diffusion fit). NaNs if fewer than two positive points.
    """
    tau = np.asarray(tau, float)
    m = np.asarray(msd_vals, float)
    ok = (tau > 0) & (m > 0) & np.isfinite(tau) & np.isfinite(m)
    if ok.sum() < 2:
        return {"D": np.nan, "alpha": np.nan, "r2": np.nan}
    from scipy.stats import linregress
    lr = linregress(np.log10(tau[ok]), np.log10(m[ok]))
    return {"D": float(10 ** lr.intercept / 4.0), "alpha": float(lr.slope),
            "r2": float(lr.rvalue ** 2)}


def fit_furth(tau: np.ndarray, msd_vals: np.ndarray) -> dict:
    """Fit the Fürth / persistent-random-walk MSD → {D, persistence_time}.

    MSD(t) = 4·D·(t − P·(1 − e^(−t/P))): motility coefficient D (units²/min) and
    a directional-memory **persistence time** P (min) — more interpretable for
    migrating cells than the power-law exponent. NaNs if the fit fails.
    """
    tau = np.asarray(tau, float)
    m = np.asarray(msd_vals, float)
    ok = (tau > 0) & np.isfinite(tau) & np.isfinite(m)
    if ok.sum() < 3:
        return {"D": np.nan, "persistence_time": np.nan}
    t, y = tau[ok], m[ok]

    def furth(tt, d, p):
        return 4.0 * d * (tt - p * (1.0 - np.exp(-tt / p)))

    try:
        from scipy.optimize import curve_fit
        p0 = [max(y[-1] / (4.0 * t[-1]), 1e-6), max(t[len(t) // 4], t[0])]
        popt, _ = curve_fit(furth, t, y, p0=p0, maxfev=5000,
                            bounds=([1e-9, 1e-9], [np.inf, np.inf]))
        return {"D": float(popt[0]), "persistence_time": float(popt[1])}
    except Exception:
        return {"D": np.nan, "persistence_time": np.nan}


def run_and_tumble(cen: np.ndarray, dt_min: float | None = None,
                   turn_threshold_deg: float | None = None) -> dict:
    """Decompose a track into directed **runs** and reorientation **tumbles**.

    A step whose turning angle (vs the previous step) exceeds ``turn_threshold_deg``
    is a *tumble*; the directed segments between tumbles are *runs*. Returns
    ``n_runs``, ``mean_run_steps`` / ``mean_run_duration`` (min), ``tumble_rate``
    (tumbles per min), ``frac_tumble`` (fraction of step-joints that are tumbles) and
    ``mean_tumble_angle_deg``. A more sensitive persistence readout than a single
    autocorrelation number. NaNs for < 3 finite points."""
    if turn_threshold_deg is None:
        turn_threshold_deg = RUN_TUMBLE_TURN_DEG
    keys = ("n_runs", "mean_run_steps", "mean_run_duration", "tumble_rate",
            "frac_tumble", "mean_tumble_angle_deg")
    turns = turning_angles(cen)                       # one per step-joint
    if turns.size == 0:
        return {k: np.nan for k in keys}
    dt = float(dt_min) if dt_min else 1.0
    defined = np.isfinite(turns)                       # pause-joints (NaN) are excluded
    is_tumble = defined & (np.abs(turns) > np.deg2rad(turn_threshold_deg))
    run_steps, cur = [], 1                             # first step opens a run
    for t in is_tumble:
        if t:
            run_steps.append(cur); cur = 1
        else:
            cur += 1
    run_steps.append(cur)
    run_steps = np.asarray(run_steps, float)
    n_steps = turns.size + 1                           # steps = joints + 1
    tumble_ang = np.abs(turns[is_tumble])
    return {
        "n_runs": int(run_steps.size),
        "mean_run_steps": float(run_steps.mean()),
        "mean_run_duration": float(run_steps.mean()) * dt,
        "tumble_rate": float(is_tumble.sum() / (n_steps * dt)) if n_steps else np.nan,
        "frac_tumble": float(is_tumble.sum() / defined.sum()) if defined.any() else np.nan,
        "mean_tumble_angle_deg": (float(np.rad2deg(tumble_ang.mean()))
                                  if tumble_ang.size else np.nan),
    }


def jump_steps(cen: np.ndarray, factor: float | None = None,
               min_px: float = 0.0) -> tuple:
    """Track-continuity QC: step indices whose displacement is an outlier — a
    suspected tracking error / ID swap.

    A step is a *jump* when its length exceeds ``factor``× the median step length
    (and ≥ ``min_px``). Returns ``(n_jumps, max_step, frac_jumps)``. Operates on the
    raw centroid units (px unless ``cen`` is pre-scaled). ``factor=None`` reads the
    (configurable) module-level ``JUMP_FACTOR``."""
    if factor is None:
        factor = JUMP_FACTOR
    seg = instantaneous_speed(cen)                    # per-step length (no dt → length)
    if seg.size == 0:
        return 0, np.nan, np.nan
    med = float(np.median(seg))
    thr = max(factor * med, float(min_px))
    jumps = seg > thr if thr > 0 else np.zeros(seg.size, bool)
    return int(jumps.sum()), float(seg.max()), float(jumps.mean())


def motion_summary(cen: np.ndarray, dt_min: float | None = None) -> dict:
    """One-row motion summary for a track: displacement metrics + persistence."""
    out = displacement_metrics(cen, dt_min)
    out["dir_autocorr_lag1"] = persistence(cen)
    return out
