// Motion metrics from centroid tracks: a JS port of maskviewer/analysis/motion.py (displacement metrics, direction
// autocorrelation, MSD + power-law fit, directionality ratio, velocity autocorrelation, turning angles,
// run-and-tumble, jump steps). A track is an array of [y, x] per frame (NaN where the cell is absent), already in
// physical units when scaled. Checked against the Python code by morph_engine.test.mjs.

export const MOTION = { RUN_TUMBLE_TURN_DEG: 60, JUMP_FACTOR: 5 };

const finite = cen => cen.filter(p => Number.isFinite(p[0]) && Number.isFinite(p[1]));
const presentIdx = cen => cen.map((p, i) => (Number.isFinite(p[0]) && Number.isFinite(p[1]) ? i : -1)).filter(i => i >= 0);
const steps = pts => pts.slice(1).map((p, i) => [p[0] - pts[i][0], p[1] - pts[i][1]]);
const len = v => Math.sqrt(v[0] * v[0] + v[1] * v[1]);
const mean = a => a.reduce((s, v) => s + v, 0) / a.length;
export const scaleTrack = (cen, s) => cen.map(p => [p[0] * s, p[1] * s]);

export function instantaneousSpeed(cen, dtMin = null) {
  const idx = presentIdx(cen), pts = idx.map(i => cen[i]);
  if (pts.length < 2) return [];
  const seg = steps(pts).map(len);
  if (!dtMin) return seg;
  return seg.map((s, i) => s / ((idx[i + 1] - idx[i]) * dtMin));
}

export function displacementMetrics(cen, dtMin = null) {
  const idx = presentIdx(cen), pts = idx.map(i => cen[i]);
  if (pts.length < 2) return { net_disp: NaN, total_path: NaN, straightness: NaN, mean_speed: NaN, n_steps: 0 };
  const seg = steps(pts).map(len), total = seg.reduce((a, b) => a + b, 0);
  const net = len([pts[pts.length - 1][0] - pts[0][0], pts[pts.length - 1][1] - pts[0][1]]);
  const elapsed = idx[idx.length - 1] - idx[0];
  return { net_disp: net, total_path: total, straightness: total > 0 ? net / total : NaN,
    mean_speed: dtMin ? total / (elapsed * dtMin) : total / elapsed, n_steps: seg.length };
}

export function directionAutocorrelation(cen, maxLag = null) {
  const pts = finite(cen);
  if (pts.length < 3) return [];
  const st = steps(pts), norms = st.map(len), ok = norms.map(n => n > 0);
  const units = st.map((s, i) => (ok[i] ? [s[0] / norms[i], s[1] / norms[i]] : [0, 0]));
  const n = units.length, L = Math.min(maxLag || n - 1, n - 1), out = new Array(L + 1).fill(NaN);
  out[0] = 1;
  for (let lag = 1; lag <= L; lag++) {
    let s = 0, c = 0;
    for (let i = 0; i + lag < n; i++) if (ok[i] && ok[i + lag]) { s += units[i][0] * units[i + lag][0] + units[i][1] * units[i + lag][1]; c++; }
    if (c) out[lag] = s / c;
  }
  return out;
}

export function persistence(cen) {
  const ac = directionAutocorrelation(cen, 1);
  return ac.length > 1 ? ac[1] : NaN;
}

// -> {tau, msd}
export function msd(cen, dtMin = null, maxLag = null) {
  const pts = finite(cen), n = pts.length;
  if (n < 2) return { tau: [], msd: [] };
  const L = Math.min(maxLag || n - 1, n - 1), tau = [], vals = [];
  for (let lag = 1; lag <= L; lag++) {
    let s = 0;
    for (let i = 0; i + lag < n; i++) { const dy = pts[i + lag][0] - pts[i][0], dx = pts[i + lag][1] - pts[i][1]; s += dy * dy + dx * dx; }
    vals.push(s / (n - lag)); tau.push(dtMin ? lag * dtMin : lag);
  }
  return { tau, msd: vals };
}

// -> {t, ratio}
export function directionalityRatio(cen, dtMin = null) {
  const pts = finite(cen), n = pts.length;
  if (n < 2) return { t: [], ratio: [] };
  let path = 0;
  const ratio = [1];
  for (let i = 1; i < n; i++) {
    path += len([pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]]);
    const d = len([pts[i][0] - pts[0][0], pts[i][1] - pts[0][1]]);
    ratio.push(path > 0 ? d / path : 1);
  }
  return { t: ratio.map((_, i) => i * (dtMin || 1)), ratio };
}

// index 0 = lag 1
export function velocityAutocorrelation(cen, maxLag = null) {
  const pts = finite(cen);
  if (pts.length < 3) return [];
  const v = steps(pts), n = v.length, L = Math.min(maxLag || n - 1, n - 1);
  const ssq = v.reduce((s, q) => s + q[0] * q[0] + q[1] * q[1], 0), out = new Array(L).fill(NaN);
  if (ssq <= 0) return out;
  for (let k = 1; k <= L; k++) {
    let s = 0;
    for (let i = 0; i + k < n; i++) s += v[i][0] * v[i + k][0] + v[i][1] * v[i + k][1];
    out[k - 1] = s / (n - k) / ssq;
  }
  return out;
}

// numpy's (x + pi) % (2 pi) - pi with a floored modulo
const wrap = a => { const m = 2 * Math.PI, r = (a + Math.PI) % m; return (r < 0 ? r + m : r) - Math.PI; };

export function turningAngles(cen) {
  const pts = finite(cen);
  if (pts.length < 3) return [];
  const st = steps(pts), norms = st.map(len), ang = st.map(s => Math.atan2(s[0], s[1]));
  return ang.slice(1).map((a, i) => (norms[i] === 0 || norms[i + 1] === 0 ? NaN : wrap(a - ang[i])));
}

// Least-squares line y = a + b x -> {slope, intercept, r}
export function linregress(x, y) {
  const n = x.length, mx = mean(x), my = mean(y);
  let sxx = 0, sxy = 0, syy = 0;
  for (let i = 0; i < n; i++) { const dx = x[i] - mx, dy = y[i] - my; sxx += dx * dx; sxy += dx * dy; syy += dy * dy; }
  const slope = sxy / sxx, r = sxx > 0 && syy > 0 ? sxy / Math.sqrt(sxx * syy) : 0;
  return { slope, intercept: my - slope * mx, r: Math.max(-1, Math.min(1, r)) };
}

// MSD = 4 D tau^alpha, fitted in log-log -> {D, alpha, r2}
export function fitMsd(tau, m) {
  const x = [], y = [];
  tau.forEach((t, i) => { if (t > 0 && m[i] > 0 && Number.isFinite(t) && Number.isFinite(m[i])) { x.push(Math.log10(t)); y.push(Math.log10(m[i])); } });
  if (x.length < 2) return { D: NaN, alpha: NaN, r2: NaN };
  const lr = linregress(x, y);
  return { D: 10 ** lr.intercept / 4, alpha: lr.slope, r2: lr.r ** 2 };
}

export function runAndTumble(cen, dtMin = null, thrDeg = MOTION.RUN_TUMBLE_TURN_DEG) {
  const keys = ['n_runs', 'mean_run_steps', 'mean_run_duration', 'tumble_rate', 'frac_tumble', 'mean_tumble_angle_deg'];
  const turns = turningAngles(cen);
  if (!turns.length) return Object.fromEntries(keys.map(k => [k, NaN]));
  const dt = dtMin || 1, thr = thrDeg * Math.PI / 180;
  const defined = turns.map(Number.isFinite), tumble = turns.map((t, i) => defined[i] && Math.abs(t) > thr);
  const runs = [];
  let cur = 1;
  for (const t of tumble) { if (t) { runs.push(cur); cur = 1; } else cur++; }
  runs.push(cur);
  const nT = tumble.filter(Boolean).length, nDef = defined.filter(Boolean).length, nSteps = turns.length + 1;
  const angs = turns.filter((_, i) => tumble[i]).map(t => Math.abs(t) * 180 / Math.PI);
  return { n_runs: runs.length, mean_run_steps: mean(runs), mean_run_duration: mean(runs) * dt,
    tumble_rate: nT / (nSteps * dt), frac_tumble: nDef ? nT / nDef : NaN,
    mean_tumble_angle_deg: angs.length ? mean(angs) : NaN };
}

function median(a) {
  const s = a.slice().sort((p, q) => p - q), n = s.length;
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
}

// -> [n_jumps, max_step, frac_jumps]
export function jumpSteps(cen, factor = MOTION.JUMP_FACTOR, minPx = 0) {
  const seg = instantaneousSpeed(cen);
  if (!seg.length) return [0, NaN, NaN];
  const thr = Math.max(factor * median(seg), minPx);
  const j = seg.map(s => thr > 0 && s > thr);
  const n = j.filter(Boolean).length;
  return [n, Math.max(...seg), n / seg.length];
}

export function motionSummary(cen, dtMin = null) {
  return { ...displacementMetrics(cen, dtMin), dir_autocorr_lag1: persistence(cen) };
}
