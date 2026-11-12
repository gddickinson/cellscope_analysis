// Number formatting, colours (state colours from analysis/state.py) and metric labels.

export function f(v, d = 3) {
  if (v === null || v === undefined || (typeof v === 'number' && !Number.isFinite(v))) return '–';
  if (typeof v !== 'number') return String(v);
  if (Number.isInteger(v)) return v.toLocaleString('en');
  const a = Math.abs(v);
  if (a !== 0 && (a < 1e-3 || a >= 1e5)) return v.toExponential(2);
  return (+v.toPrecision(d + (a >= 1 ? Math.floor(Math.log10(a)) : 0))).toString();
}
export const pval = p => (Number.isFinite(p) ? (p < 1e-4 ? p.toExponential(1) : p.toFixed(4)) : '–');

// state.py STATE_COLOR
export const STATE_COLOR = { unknown: 'rgb(130,130,130)', spread: 'rgb(44,160,44)', rounded: 'rgb(214,39,40)', edge: 'rgb(255,165,0)' };
export const STATE_RGB = { unknown: [130, 130, 130], spread: [44, 160, 44], rounded: [214, 39, 40], edge: [255, 165, 0] };

// Categorical palette (cells, conditions); index wraps.
export const PALETTE = ['#2ee6ff', '#ff4fd8', '#ffb02e', '#7dff6a', '#a78bff', '#ff6b6b', '#4fd1c5', '#f6e05e', '#f687b3', '#90cdf4'];
export const colour = i => PALETTE[((i % PALETTE.length) + PALETTE.length) % PALETTE.length];
export function cellRgb(id) {                         // stable bright colour per cell ID (golden-angle hues)
  const h = (id * 137.508) % 360, s = 0.75, l = 0.58;
  const k = n => (n + h / 30) % 12, a = s * Math.min(l, 1 - l);
  const c = n => Math.round(255 * (l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)))));
  return [c(0), c(8), c(4)];
}

// Sequential ramp for colour-by-metric (dark blue -> cyan -> yellow), t in [0, 1].
const STOPS = [[40, 30, 120], [30, 120, 200], [46, 230, 255], [180, 255, 120], [255, 210, 60]];
export function ramp(t) {
  if (!Number.isFinite(t)) return [120, 120, 120];
  const x = Math.max(0, Math.min(1, t)) * (STOPS.length - 1), i = Math.min(STOPS.length - 2, Math.floor(x)), u = x - i;
  return STOPS[i].map((v, k) => Math.round(v + (STOPS[i + 1][k] - v) * u));
}
export const rampCss = n => `linear-gradient(90deg, ${Array.from({ length: n }, (_, i) => `rgb(${ramp(i / (n - 1)).join(',')})`).join(',')})`;

// Metric docs (from /api/metrics, metric_docs.py) with a readable fallback.
let DOCS = {};
export const setDocs = d => { DOCS = d || {}; };
export const label = c => DOCS[c]?.label || c.replace(/_/g, ' ');
export const docOf = c => DOCS[c];
export const tip = c => { const d = DOCS[c]; return d && d.what ? `${d.what}${d.how ? ' How: ' + d.how : ''}` : ''; };
