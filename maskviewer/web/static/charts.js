// Small SVG charts (no library): line chart with optional bands, scatter, histogram and strip/box plot by group.
// All return an SVG string sized by viewBox; text uses the theme's mono font via .chart CSS.
import { esc } from './core.js';
import { f } from './fmt.js';

const W = 380, H = 240, M = { l: 58, r: 12, t: 12, b: 40 };
const finite = a => a.filter(Number.isFinite);

function ticks(lo, hi, n = 5) {
  const span = hi - lo || 1, step0 = span / n, mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= step0);
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9 * span; v += step) out.push(+v.toPrecision(12));
  return out;
}

function scale(d0, d1, r0, r1, log = false) {
  const t = log ? Math.log10 : v => v, a = t(d0), b = t(d1);
  const s = v => r0 + (t(v) - a) / ((b - a) || 1) * (r1 - r0);
  s.domain = [d0, d1];
  s.ticks = log ? ticks(Math.ceil(a), Math.floor(b), 6).filter(Number.isInteger).map(e => 10 ** e) : ticks(d0, d1);
  if (log && s.ticks.length < 2) s.ticks = [d0, d1];
  return s;
}

function pad(lo, hi, log) {
  if (!Number.isFinite(lo)) return [0, 1];
  if (hi <= lo) return log ? [lo / 2, hi * 2] : [lo - 0.5, hi + 0.5];
  if (log) return [lo, hi];
  const p = (hi - lo) * 0.05;
  return [lo - p, hi + p];
}

function axes(xs, ys, xl, yl, xt = null) {
  let s = `<line class="axis" x1="${M.l}" y1="${H - M.b}" x2="${W - M.r}" y2="${H - M.b}"/><line class="axis" x1="${M.l}" y1="${M.t}" x2="${M.l}" y2="${H - M.b}"/>`;
  if (xt) xt.forEach(([v, lab]) => { s += `<text x="${xs(v)}" y="${H - M.b + 14}" text-anchor="middle">${esc(lab)}</text>`; });
  else xs.ticks.forEach(v => { s += `<text x="${xs(v)}" y="${H - M.b + 14}" text-anchor="middle">${f(v)}</text>`; });
  ys.ticks.forEach(v => { s += `<text x="${M.l - 5}" y="${ys(v) + 4}" text-anchor="end">${f(v)}</text>`; });
  s += `<text x="${(M.l + W - M.r) / 2}" y="${H - 5}" text-anchor="middle">${esc(xl)}</text>`;
  s += `<text transform="translate(12 ${(M.t + H - M.b) / 2}) rotate(-90)" text-anchor="middle">${esc(yl)}</text>`;
  return s;
}

const svg = (body, label) => `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">${body}</svg>`;
export const legend = items => `<div class="legend">${items.map(([n, c]) => `<span class="cls" style="--c:${c}">${esc(n)}</span>`).join('')}</div>`;

// series: [{name, color, x, y, lo?, hi?, dash?, width?, opacity?}]
export function lineChart(series, { xlabel = '', ylabel = '', logx = false, logy = false, zero = false, markers = false } = {}) {
  const okx = v => Number.isFinite(v) && (!logx || v > 0), oky = v => Number.isFinite(v) && (!logy || v > 0);
  const xsAll = [], ysAll = [];
  for (const s of series) s.x.forEach((x, i) => { if (okx(x) && oky(s.y[i])) { xsAll.push(x); ysAll.push(s.y[i]); if (s.lo && oky(s.lo[i])) ysAll.push(s.lo[i]); if (s.hi && oky(s.hi[i])) ysAll.push(s.hi[i]); } });
  if (!xsAll.length) return '<p class="mute small">Nothing to plot.</p>';
  let [y0, y1] = pad(Math.min(...ysAll), Math.max(...ysAll), logy);
  if (zero && !logy) { y0 = Math.min(y0, 0); y1 = Math.max(y1, 0); }
  const xs = scale(...pad(Math.min(...xsAll), Math.max(...xsAll), logx), M.l, W - M.r, logx);
  const ys = scale(y0, y1, H - M.b, M.t, logy);
  let b = axes(xs, ys, xlabel, ylabel);
  if (zero && !logy && y0 < 0 && y1 > 0) b += `<line class="axis" stroke-dasharray="3 3" x1="${M.l}" x2="${W - M.r}" y1="${ys(0)}" y2="${ys(0)}"/>`;
  for (const s of series) {
    if (s.lo && s.hi) {
      const idx = s.x.map((x, i) => i).filter(i => okx(s.x[i]) && oky(s.lo[i]) && oky(s.hi[i]));
      if (idx.length > 1) {
        const top = idx.map(i => `${xs(s.x[i]).toFixed(1)},${ys(s.hi[i]).toFixed(1)}`), bot = idx.slice().reverse().map(i => `${xs(s.x[i]).toFixed(1)},${ys(s.lo[i]).toFixed(1)}`);
        b += `<polygon points="${top.concat(bot).join(' ')}" fill="${s.color}" fill-opacity=".18"/>`;
      }
    }
    let d = '', pen = false;
    s.x.forEach((x, i) => { if (okx(x) && oky(s.y[i])) { d += `${pen ? 'L' : 'M'}${xs(x).toFixed(1)} ${ys(s.y[i]).toFixed(1)}`; pen = true; } else pen = false; });
    b += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width || 1.6}" stroke-opacity="${s.opacity ?? 1}"${s.dash ? ' stroke-dasharray="4 3"' : ''}><title>${esc(s.name)}</title></path>`;
    if (markers) s.x.forEach((x, i) => { if (okx(x) && oky(s.y[i])) b += `<circle cx="${xs(x).toFixed(1)}" cy="${ys(s.y[i]).toFixed(1)}" r="2" fill="${s.color}"/>`; });
  }
  return svg(b, `${ylabel} against ${xlabel}`);
}

// points: [{x, y, c, t?}]
export function scatter(points, { xlabel = '', ylabel = '', onClickAttr = null } = {}) {
  const pts = points.filter(p => Number.isFinite(p.x) && Number.isFinite(p.y));
  if (!pts.length) return '<p class="mute small">No points to plot.</p>';
  const xs = scale(...pad(Math.min(...pts.map(p => p.x)), Math.max(...pts.map(p => p.x))), M.l, W - M.r);
  const ys = scale(...pad(Math.min(...pts.map(p => p.y)), Math.max(...pts.map(p => p.y))), H - M.b, M.t);
  let b = axes(xs, ys, xlabel, ylabel);
  for (const p of pts) b += `<circle cx="${xs(p.x).toFixed(1)}" cy="${ys(p.y).toFixed(1)}" r="3.2" fill="${p.c}" fill-opacity=".8"${onClickAttr && p.id != null ? ` ${onClickAttr}="${esc(p.id)}" class="pt"` : ''}>${p.t ? `<title>${esc(p.t)}</title>` : ''}</circle>`;
  return svg(b, `${ylabel} against ${xlabel}`);
}

// groups: [{name, color, values}] -> overlaid step histograms on shared bins
export function histogram(groups, { xlabel = '', bins = 20 } = {}) {
  const all = groups.flatMap(g => finite(g.values));
  if (!all.length) return '<p class="mute small">No finite values.</p>';
  let lo = Math.min(...all), hi = Math.max(...all);
  if (hi <= lo) { lo -= 0.5; hi += 0.5; }
  const w = (hi - lo) / bins, counts = groups.map(g => {
    const c = new Array(bins).fill(0);
    finite(g.values).forEach(v => { c[Math.min(bins - 1, Math.floor((v - lo) / w))]++; });
    return c;
  });
  const xs = scale(lo, hi, M.l, W - M.r), ys = scale(0, Math.max(...counts.flat()), H - M.b, M.t);
  let b = axes(xs, ys, xlabel, 'count');
  groups.forEach((g, k) => counts[k].forEach((c, i) => {
    if (c) b += `<rect x="${(xs(lo + i * w) + 0.5).toFixed(1)}" y="${ys(c).toFixed(1)}" width="${Math.max(0.5, xs(lo + w) - xs(lo) - 1).toFixed(1)}" height="${(ys(0) - ys(c)).toFixed(1)}" fill="${g.color}" fill-opacity="${groups.length > 1 ? 0.45 : 0.8}"><title>${esc(g.name)} ${f(lo + i * w)}–${f(lo + (i + 1) * w)}: ${c}</title></rect>`;
  }));
  return svg(b, `Histogram of ${xlabel}`);
}

// groups: [{name, color, values, labels?}] -> jittered strip + mean +/- SEM bar per group (a "superplot" when
// `under` gives per-group lighter points, e.g. cells beneath recording means).
export function strip(groups, { ylabel = '', under = null } = {}) {
  const all = groups.flatMap(g => finite(g.values)).concat(under ? under.flatMap(g => finite(g.values)) : []);
  if (!all.length) return '<p class="mute small">No finite values.</p>';
  const xs = v => M.l + (v + 0.5) * (W - M.l - M.r) / groups.length;
  xs.ticks = [];
  const ys = scale(...pad(Math.min(...all), Math.max(...all)), H - M.b, M.t);
  let b = axes(xs, ys, '', ylabel, groups.map((g, i) => [i, g.name]));
  const jit = (i, n) => (n > 1 ? (i / (n - 1) - 0.5) * 0.5 : 0) * (W - M.l - M.r) / groups.length;
  if (under) under.forEach((g, gi) => finite(g.values).forEach((v, i, a) => {
    b += `<circle cx="${(xs(gi) + jit(i, a.length) * 1.3).toFixed(1)}" cy="${ys(v).toFixed(1)}" r="1.8" fill="${g.color}" fill-opacity=".3"/>`;
  }));
  groups.forEach((g, gi) => {
    const v = g.values.map((x, i) => [x, g.labels?.[i]]).filter(([x]) => Number.isFinite(x));
    v.forEach(([x, lab], i) => { b += `<circle cx="${(xs(gi) + jit(i, v.length)).toFixed(1)}" cy="${ys(x).toFixed(1)}" r="4.5" fill="${g.color}" stroke="#05060c"><title>${esc(lab || '')} ${f(x)}</title></circle>`; });
    if (v.length) {
      const vals = v.map(p => p[0]), m = vals.reduce((a, c) => a + c, 0) / vals.length;
      const sem = vals.length > 1 ? Math.sqrt(vals.reduce((a, c) => a + (c - m) ** 2, 0) / (vals.length - 1) / vals.length) : 0;
      const hw = 0.3 * (W - M.l - M.r) / groups.length;
      b += `<line x1="${xs(gi) - hw}" x2="${xs(gi) + hw}" y1="${ys(m)}" y2="${ys(m)}" stroke="var(--ink)" stroke-width="2"/>`;
      b += `<line x1="${xs(gi)}" x2="${xs(gi)}" y1="${ys(m - sem)}" y2="${ys(m + sem)}" stroke="var(--ink)" stroke-width="1.2"/>`;
    }
  });
  return svg(b, `${ylabel} by group`);
}

// Flower plot: tracks [{color, pts:[[x,y]...]}] already origin-centred.
export function flower(tracks, { unit = 'µm' } = {}) {
  const all = tracks.flatMap(t => t.pts.flat()).filter(Number.isFinite);
  if (!all.length) return '<p class="mute small">No tracks.</p>';
  const r = Math.max(...all.map(Math.abs)) * 1.05 || 1, S = 240, c = S / 2, k = (S / 2 - 16) / r;
  let b = `<line class="axis" x1="${c}" x2="${c}" y1="8" y2="${S - 8}"/><line class="axis" y1="${c}" y2="${c}" x1="8" x2="${S - 8}"/>`;
  b += `<text x="${S - 10}" y="${c - 4}" text-anchor="end">${f(r)} ${esc(unit)}</text>`;
  for (const t of tracks) {
    const d = t.pts.filter(p => Number.isFinite(p[0])).map((p, i) => `${i ? 'L' : 'M'}${(c + p[0] * k).toFixed(1)} ${(c + p[1] * k).toFixed(1)}`).join('');
    b += `<path d="${d}" fill="none" stroke="${t.color}" stroke-width="1.3" stroke-opacity=".85"><title>${esc(t.name || '')}</title></path>`;
  }
  return `<svg class="chart flower" viewBox="0 0 ${S} ${S}" role="img" aria-label="Flower plot of origin-centred tracks">${b}</svg>`;
}
