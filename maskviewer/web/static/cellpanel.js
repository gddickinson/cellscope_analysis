// Cell inspector (the desktop Cell Info dock): summary of one tracked cell and a plot of any per-frame
// characteristic over time, or its MSD (log-log with the power-law fit) or direction autocorrelation.
import { esc } from './core.js';
import { lineChart } from './charts.js';
import { f, label, tip } from './fmt.js';
import * as mo from './motion_engine.js';
import { STATE_CODE } from './morph_engine.js';

// Per-frame series of one cell from the per-frame records + centroid track (cell_metrics.cell_frame_table subset).
export function cellSeries(rec, cid) {
  const a = rec.analysis, u = rec.umPerPx ? 'um' : 'px', s = rec.umPerPx || 1, dt = rec.dtMin || null;
  const rows = a.perFrame.filter(r => r.cell_id === cid).sort((p, q) => p.frame - q.frame);
  const frames = rows.map(r => r.frame), time = frames.map(t => (dt ? t * dt : t));
  const col = (k, k2) => rows.map(r => r[k] ?? r[k2]);
  const pts = rows.map(r => [r.centroid_y * s, r.centroid_x * s]);
  const speed = pts.map((p, i) => (i ? Math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]) / ((frames[i] - frames[i - 1]) * (dt || 1)) : NaN));
  const turn = mo.turningAngles(pts);
  const areaKey = rec.umPerPx ? 'area_um2' : 'area_px';
  const areas = col(areaKey).filter(Number.isFinite).sort((p, q) => p - q);
  const q = (arr, pp) => { const i = (arr.length - 1) * pp, lo = Math.floor(i); return arr[lo] + ((arr[Math.min(lo + 1, arr.length - 1)] ?? arr[lo]) - arr[lo]) * (i - lo); };
  const base = areas.length ? q(areas, 0.9) : NaN;   // np.nanpercentile(areas, 90)
  const series = {
    [areaKey]: col(areaKey), rel_area: col(areaKey).map(v => v / base), [`perimeter_${u}`]: col(`perimeter_${u}`),
    circularity: col('circularity'), convexity: col('convexity'), eccentricity: col('eccentricity'), aspect_ratio: col('aspect_ratio'),
    [`major_axis_${u}`]: col(`major_axis_${u}`, 'major_axis_px'), [`minor_axis_${u}`]: col(`minor_axis_${u}`, 'minor_axis_px'),
    orientation_rad: col('orientation_rad'), extent: col('extent'), state_code: rows.map(r => STATE_CODE[r.state]),
    speed, displacement_from_start: pts.map(p => Math.hypot(p[0] - pts[0][0], p[1] - pts[0][1])),
    turning_angle: pts.map((_, i) => (i && i < pts.length - 1 ? turn[i - 1] : NaN)),
    [`nn_dist_${u}`]: col(`nn_dist_${u}`), n_neighbors: col('n_neighbors'),
  };
  return { frames, time, series, pts, rows, unit: u };
}

const UNITS = { speed: r => `${r.umPerPx ? 'µm' : 'px'}/${r.dtMin ? 'min' : 'frame'}`, displacement_from_start: r => (r.umPerPx ? 'µm' : 'px'),
  turning_angle: () => 'rad', rel_area: () => '/90th pct', state_code: () => '0 unknown · 1 spread · 2 rounded · 3 edge' };

export function cellPanel(host, rec, cid, { metric = null, onMetric } = {}) {
  const cs = cellSeries(rec, cid), row = rec.analysis.perCell.find(r => r.cell_id === cid);
  if (!row) { host.innerHTML = '<p class="mute">Click a cell in the image to inspect it.</p>'; return; }
  const keys = [...Object.keys(cs.series), 'MSD', 'direction autocorrelation'];
  const m = keys.includes(metric) ? metric : (rec.umPerPx ? 'area_um2' : 'area_px');
  const u = cs.unit, su = `${u}_per_${rec.dtMin ? 'min' : 'frame'}`;
  const kv = [['frames tracked', `${row.frames_tracked} (${row.first_frame}–${row.last_frame})`],
    ['mean area', f(row[`mean_area_${rec.umPerPx ? 'um2' : 'px'}`]) + (rec.umPerPx ? ' µm²' : ' px')],
    ['mean speed', f(row[`mean_speed_${su}`]) + ` ${UNITS.speed(rec)}`], ['persistence (lag-1)', f(row.persistence_dir_autocorr)],
    ['straightness', f(row.straightness)], ['net displacement', f(row[`net_disp_${u}`]) + ` ${u === 'um' ? 'µm' : 'px'}`],
    ['time rounded / spread', `${f(row.frac_rounded, 2)} / ${f(row.frac_spread, 2)}`], ['track quality', f(row.track_quality)]];
  host.innerHTML = `<h3>Cell ${cid}</h3>
    <dl class="kv">${kv.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
    <label for="cp-metric">Plot</label><select id="cp-metric">${keys.map(k => `<option value="${esc(k)}"${k === m ? ' selected' : ''}>${esc(k === 'MSD' || k.startsWith('direction') ? k : label(k))}</option>`).join('')}</select>
    <div id="cp-plot"></div><p class="small mute" id="cp-note"></p>`;
  host.querySelector('#cp-metric').onchange = e => onMetric?.(e.target.value);
  const plot = host.querySelector('#cp-plot'), note = host.querySelector('#cp-note');
  const tl = rec.dtMin ? 'time (min)' : 'frame';
  if (m === 'MSD') {
    const r = mo.msd(cs.pts, rec.dtMin), fit = mo.fitMsd(r.tau, r.msd);
    const fitY = r.tau.map(t => 4 * fit.D * t ** fit.alpha);
    plot.innerHTML = lineChart([{ name: 'MSD', color: '#2ee6ff', x: r.tau, y: r.msd }, { name: 'fit', color: '#ffb02e', x: r.tau, y: fitY, dash: true }],
      { xlabel: `lag (${rec.dtMin ? 'min' : 'frames'})`, ylabel: `MSD (${u === 'um' ? 'µm²' : 'px²'})`, logx: true, logy: true, markers: true });
    note.textContent = `MSD = 4·D·τ^α fitted in log-log (motion.fit_msd): α = ${f(fit.alpha)}, D = ${f(fit.D)}, r² = ${f(fit.r2)}. α > 1 directed, ≈ 1 random, < 1 confined.`;
  } else if (m === 'direction autocorrelation') {
    const ac = mo.directionAutocorrelation(cs.pts);
    plot.innerHTML = lineChart([{ name: 'autocorrelation', color: '#ff4fd8', x: ac.map((_, i) => i * (rec.dtMin || 1)), y: ac }],
      { xlabel: `lag (${rec.dtMin ? 'min' : 'frames'})`, ylabel: 'mean cos θ', zero: true, markers: true });
    note.textContent = 'Mean cosine between step directions separated by each lag (speed-independent persistence; gaps bridged).';
  } else {
    const un = UNITS[m]?.(rec);
    plot.innerHTML = lineChart([{ name: m, color: '#2ee6ff', x: cs.time, y: cs.series[m] }], { xlabel: tl, ylabel: un ? `${label(m)} (${un})` : label(m), markers: true });
    note.textContent = tip(m);
  }
}
