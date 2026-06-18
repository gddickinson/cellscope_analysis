"""Our built-in direction-autocorrelation + MSD must equal the DiPer method exactly.

`maskviewer.analysis.motion` is the in-GUI / programmatic implementation of DiPer's
direction autocorrelation and MSD. This test pins that equivalence with a *self-contained*
reference that re-implements DiPer's algorithm verbatim (from the `diper_clone` package:
`autocorrel.normalize_vectors` + `calculate_autocorrelation`, and `msd.calculate_msd`),
so a future edit to `motion` can never silently diverge. Verified against the real
`diper_clone` package on IC293 trajectories (max |diff| ~1e-15 per cell and ensemble).
"""
import numpy as np

from maskviewer.analysis import motion


# ---- DiPer reference (copied algorithm, not imported) ----------------------
def diper_autocorrelation(xy, max_lag):
    """diper_clone autocorrel.normalize_vectors + calculate_autocorrelation."""
    dx = np.diff(xy[:, 0])                 # forward step vectors (x.diff().shift(-1))
    dy = np.diff(xy[:, 1])
    mag = np.hypot(dx, dy)
    with np.errstate(invalid="ignore", divide="ignore"):
        xv = np.where(mag > 0, dx / mag, 0.0)  # unit vectors, 0 for zero-length
        yv = np.where(mag > 0, dy / mag, 0.0)
    n = len(xv)
    out = []
    for step in range(1, min(max_lag, n - 1) + 1):
        coefs = []
        for i in range(n - step):
            if (xv[i] == 0 and yv[i] == 0) or (xv[i + step] == 0 and yv[i + step] == 0):
                continue                   # skip zero-length vectors (DiPer)
            coefs.append(xv[i] * xv[i + step] + yv[i] * yv[i + step])
        out.append(np.mean(coefs) if coefs else np.nan)
    return np.array(out)


def diper_msd(xy, max_step):
    """diper_clone msd.calculate_msd (overlapping windows)."""
    out = []
    n = len(xy)
    for step in range(1, max_step + 1):
        if n - step <= 0:
            break
        d = xy[step:] - xy[:-step]
        out.append((d ** 2).sum(axis=1).mean())
    return np.array(out)


def diper_dir_ratio(xy):
    """diper_clone dir_ratio.calculate_directionality_ratio (d/D over time)."""
    seg = np.hypot(np.diff(xy[:, 0]), np.diff(xy[:, 1]))
    path = np.concatenate([[np.nan], np.cumsum(seg)])        # path_length[0] = NaN
    dist = np.hypot(xy[:, 0] - xy[0, 0], xy[:, 1] - xy[0, 1])
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = dist / path
    ratio[0] = 1.0
    return ratio


def diper_velcorr(xy, max_step):
    """diper_clone vel_cor.calculate_normalized_velocity_autocorrelation."""
    dx, dy = np.diff(xy[:, 0]), np.diff(xy[:, 1])
    ssq = float((dx ** 2 + dy ** 2).sum())                   # dt²·norm
    out = []
    for step in range(1, max_step + 1):
        if len(dx) - step <= 0:
            break
        num = dx[:-step] * dx[step:] + dy[:-step] * dy[step:]
        out.append(num.mean() / ssq)
    return np.array(out)


def _trajectories():
    """A few deterministic trajectories incl. a turn and a pause (zero-length step)."""
    rng = np.random.default_rng(0)
    out = []
    # straight + turn
    out.append(np.array([[0, 0], [1, 0], [2, 0], [3, 1], [4, 2], [5, 2], [6, 3.0]]))
    # with a pause (identical consecutive points → zero-length step)
    out.append(np.array([[0, 0], [1, 1], [1, 1], [2, 1], [3, 0], [4, 0], [5, 1.0]]))
    # a longer noisy walk
    steps = rng.normal(size=(25, 2))
    out.append(np.cumsum(np.vstack([[0, 0], steps]), axis=0).astype(float))
    return out


def test_direction_autocorrelation_matches_diper():
    for xy in _trajectories():
        ours = motion.direction_autocorrelation(xy, max_lag=15)
        assert ours[0] == 1.0                                # our lag-0 convention
        ref = diper_autocorrelation(xy, max_lag=15)
        k = min(ours.size - 1, ref.size)
        np.testing.assert_allclose(ours[1:k + 1], ref[:k], rtol=0, atol=1e-12,
                                   equal_nan=True)


def test_msd_matches_diper():
    for xy in _trajectories():
        _tau, ours = motion.msd(xy, dt_min=1.0, max_lag=15)
        ref = diper_msd(xy, max_step=15)
        k = min(ours.size, ref.size)
        np.testing.assert_allclose(ours[:k], ref[:k], rtol=0, atol=1e-9)


def test_persistence_is_lag1_autocorrelation():
    xy = _trajectories()[2]
    assert motion.persistence(xy) == motion.direction_autocorrelation(xy, max_lag=1)[1]


def test_directionality_ratio_matches_diper():
    for xy in _trajectories():
        _t, ours = motion.directionality_ratio(xy)
        ref = diper_dir_ratio(xy)
        np.testing.assert_allclose(ours, ref, rtol=0, atol=1e-12, equal_nan=True)


def test_velocity_autocorrelation_matches_diper():
    for xy in _trajectories():
        ours = motion.velocity_autocorrelation(xy, max_lag=15)
        ref = diper_velcorr(xy, max_step=15)
        k = min(ours.size, ref.size)
        np.testing.assert_allclose(ours[:k], ref[:k], rtol=0, atol=1e-12)
