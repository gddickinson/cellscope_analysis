// Tidy tables from a label stack: a JS port of maskviewer/analysis/exporters.py (per_cell_table without the contact,
// solidity, Fuerth-fit and edge columns; track_table) and the per-recording ensemble curves of compare.py
// (build_comparison: MSD, direction autocorrelation, directionality ratio, velocity autocorrelation). Plus CSV
// read/write. Checked against the Python code by morph_engine.test.mjs.
import { centroidHistory, perFrameRecords } from './morph_engine.js';
import * as mo from './motion_engine.js';

const fin = a => a.filter(Number.isFinite);
const mean = a => a.reduce((s, v) => s + v, 0) / a.length;
export function nanmedian(a) {
  const s = fin(a).sort((p, q) => p - q), n = s.length;
  if (!n) return NaN;
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
}

// Analyse one recording {labels, T, H, W} -> {perFrame, perCell, tracks, cents, units}
export function analyseStack(m, { umPerPx = null, dtMin = null, onFrame } = {}) {
  const perFrame = perFrameRecords(m, { umPerPx, dtMin, onFrame });
  const cents = centroidHistory(perFrame, m.T);
  return { perFrame, cents, perCell: perCellTable(m, perFrame, cents, { umPerPx, dtMin }), units: units(umPerPx, dtMin) };
}

export function units(umPerPx, dtMin) {
  const u = umPerPx ? 'um' : 'px';
  return { u, speed: `${u}_per_${dtMin ? 'min' : 'frame'}`, time: dtMin ? 'min' : 'frame' };
}

// exporters.per_cell_table (columns this port computes; see the module comment for those it leaves out)
export function perCellTable(m, perFrame, cents, { umPerPx = null, dtMin = null } = {}) {
  const scale = umPerPx || 1, { u, speed: su } = units(umPerPx, dtMin);
  const agg = ['area_px', 'area_um2', `perimeter_${u}`, 'circularity', 'convexity', 'eccentricity', 'aspect_ratio',
    'major_axis_px', 'minor_axis_px', 'extent', `nn_dist_${u}`, 'n_neighbors'];
  const byCell = {};
  for (const r of perFrame) (byCell[r.cell_id] ||= []).push(r);
  const rows = [];
  for (const cid of Object.keys(cents).map(Number).sort((a, b) => a - b)) {
    const cen = cents[cid], frames = cen.map((p, i) => (Number.isFinite(p[0]) ? i : -1)).filter(i => i >= 0);
    const sub = (byCell[cid] || []).slice().sort((a, b) => a.frame - b.frame);
    const row = { cell_id: cid, first_frame: frames.length ? frames[0] : -1, last_frame: frames.length ? frames[frames.length - 1] : -1,
      frames_tracked: frames.length };
    if (dtMin) row.track_length_min = frames.length * dtMin;
    if (frames.length) {
      const bd = frames.map(t => Math.min(cen[t][1], cen[t][0], (m.W - 1) - cen[t][1], (m.H - 1) - cen[t][0]));
      row[`min_border_dist_${u}`] = Math.min(...bd) * scale;
      row[`mean_border_dist_${u}`] = mean(bd) * scale;
    }
    for (const col of agg) {
      if (!sub.length || !(col in sub[0])) continue;
      const v = fin(sub.map(r => r[col]));
      if (v.length) { row[`mean_${col}`] = mean(v); row[`median_${col}`] = nanmedian(v); }
    }
    const cls = sub.map(r => r.state).filter(s => s === 'rounded' || s === 'spread');
    row.frac_rounded = cls.length ? cls.filter(s => s === 'rounded').length / cls.length : NaN;
    row.frac_spread = cls.length ? cls.filter(s => s === 'spread').length / cls.length : NaN;
    const sc = mo.scaleTrack(cen, scale), ms = mo.motionSummary(sc, dtMin);
    row[`net_disp_${u}`] = ms.net_disp; row[`total_path_${u}`] = ms.total_path; row.straightness = ms.straightness;
    row[`mean_speed_${su}`] = ms.mean_speed; row.persistence_dir_autocorr = ms.dir_autocorr_lag1;
    const rt = mo.runAndTumble(sc, dtMin);
    row.n_runs = rt.n_runs; row.mean_run_steps = rt.mean_run_steps; row.frac_tumble = rt.frac_tumble;
    row.mean_tumble_angle_deg = rt.mean_tumble_angle_deg;
    if (dtMin) { row.mean_run_duration_min = rt.mean_run_duration; row.tumble_rate_per_min = rt.tumble_rate; }
    else row.tumble_rate_per_frame = rt.tumble_rate;
    const [nj, maxStep, fj] = mo.jumpSteps(sc);
    row.n_track_jumps = nj; row[`max_step_${u}`] = maxStep; row.frac_track_jumps = fj;
    if (sub.length) {
      if (sub.length >= 2) {                            // density-stratified speed (gap-aware)
        const nn = sub.map(r => r.n_neighbors), iso = [], crd = [];
        for (let i = 1; i < sub.length; i++) {
          const a = sc[sub[i - 1].frame], b = sc[sub[i].frame];
          const gap = sub[i].frame - sub[i - 1].frame;
          const s = Math.hypot(b[0] - a[0], b[1] - a[1]) / (dtMin ? gap * dtMin : gap);
          (nn[i] === 0 ? iso : crd).push(s);
        }
        row[`speed_isolated_${su}`] = iso.length ? mean(iso) : NaN;
        row[`speed_crowded_${su}`] = crd.length ? mean(crd) : NaN;
        row.frac_isolated = nn.filter(v => v === 0).length / nn.length;
      }
      const ac = fin(sub.map(r => r[umPerPx ? 'area_um2' : 'area_px']));
      if (ac.length) {
        const ma = mean(ac), sd = Math.sqrt(mean(ac.map(v => (v - ma) ** 2)));
        row.area_cv = ma ? sd / ma : NaN;
        row.area_max_min_ratio = Math.min(...ac) > 0 ? Math.max(...ac) / Math.min(...ac) : NaN;
        let jumps = 0;
        for (let i = 1; i < ac.length; i++) if (Math.abs(ac[i] - ac[i - 1]) / ac[i - 1] > 0.3) jumps++;
        row.n_large_area_jumps = jumps;
      }
    }
    const tp = ms.total_path;
    row.track_quality = 0.5 * (frames.length / m.T) + 0.3 * Math.max(0, 1 - (row.area_cv ?? 1))
      + 0.2 * Math.min((Number.isFinite(tp) ? tp : 0) / 50, 1);
    rows.push(row);
  }
  return rows;
}

// exporters.track_table
export function trackTable(cents, { umPerPx = null, dtMin = null } = {}) {
  const rows = [];
  for (const cid of Object.keys(cents).map(Number).sort((a, b) => a - b)) {
    cents[cid].forEach(([y, x], t) => {
      if (!Number.isFinite(y)) return;
      const r = { cell_id: cid, frame: t };
      if (dtMin) r.time_min = t * dtMin;
      r.centroid_x = x; r.centroid_y = y;
      if (umPerPx) { r.centroid_x_um = x * umPerPx; r.centroid_y_um = y * umPerPx; }
      rows.push(r);
    });
  }
  return rows;
}

// compare._mean_curve_rows: NaN-mean over cells of per-cell curves padded to `width` -> [{tau, value}]
export function meanCurve(arrays, width, tauOf, skip = 0) {
  const out = [];
  for (let k = skip; k < width; k++) {
    const v = fin(arrays.map(a => (k < a.length ? a[k] : NaN)));
    if (v.length) out.push({ tau: tauOf(k), value: mean(v) });
  }
  return out;
}

// The four per-recording DiPer ensemble curves of compare.build_comparison.
export function recordingCurves(cents, { umPerPx = null, dtMin = null, maxLag = 30 } = {}) {
  const scale = umPerPx || 1, dt = dtMin || 1, cc = Object.values(cents);
  const dr = cc.map(c => mo.directionalityRatio(mo.scaleTrack(c, scale)).ratio);
  return {
    msd: meanCurve(cc.map(c => mo.msd(mo.scaleTrack(c, scale), null, maxLag).msd), maxLag, k => (k + 1) * dt),
    autocorr: meanCurve(cc.map(c => mo.directionAutocorrelation(c, maxLag)), maxLag + 1, k => k * dt, 1),
    velcorr: meanCurve(cc.map(c => mo.velocityAutocorrelation(c, maxLag)), maxLag, k => (k + 1) * dt),
    dir_ratio: meanCurve(dr, Math.max(0, ...dr.map(a => a.length)), k => k * dt),
  };
}

// ---- CSV ---------------------------------------------------------------------------------------------------------
const cell = v => {
  if (v === null || v === undefined || (typeof v === 'number' && !Number.isFinite(v))) return '';
  const s = typeof v === 'boolean' ? (v ? 'True' : 'False') : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};
export function toCsv(rows, cols = null) {
  if (!rows.length) return '';
  const c = cols || [...new Set(rows.flatMap(r => Object.keys(r)))];
  return [c.join(','), ...rows.map(r => c.map(k => cell(r[k])).join(','))].join('\n') + '\n';
}

// Parse CSV text (quoted fields allowed) -> {columns, rows}; numeric-looking fields become numbers, '' -> NaN.
export function parseCsv(text) {
  const recs = [];
  let row = [], f = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += ch;
    } else if (ch === '"') q = true;
    else if (ch === ',') { row.push(f); f = ''; }
    else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++;
      row.push(f); f = ''; if (row.length > 1 || row[0] !== '') recs.push(row); row = [];
    } else f += ch;
  }
  if (f !== '' || row.length) { row.push(f); recs.push(row); }
  if (!recs.length) throw new Error('empty CSV');
  const columns = recs[0].map(s => s.trim());
  const num = s => { const t = s.trim(); if (t === '' || /^nan$/i.test(t)) return NaN; const v = Number(t); return Number.isNaN(v) ? t : v; };
  const rows = recs.slice(1).map(r => Object.fromEntries(columns.map((c, i) => [c, num(r[i] ?? '')])));
  return { columns, rows };
}
