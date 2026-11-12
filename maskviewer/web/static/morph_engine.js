// Per-cell shape metrics from a label stack: a JS port of maskviewer/analysis/cell_metrics.py (regionprops_frame,
// per_frame_records, centroid_history), state.py (classify_state) and neighbors.py (frame_nn). Second-moment
// shape descriptors use the same normalised central moments (+1/12) as scikit-image; perimeter is skimage's
// Benkrid-Crookes nb=4 estimator; convexity / solidity use the convex hull of pixel centres (as the SciPy hull).
// Checked against the Python code by morph_engine.test.mjs. Coordinates: pixel centres, origin at pixel (0, 0).

export const STATE = { ROUNDED_AREA_UM2: 960, ROUNDED_ECC: 0.85, FALLBACK_CIRCULARITY: 0.80, FALLBACK_SOLIDITY: 0.92, MIN_AREA_PX: 200 };
export const STATE_CODE = { unknown: 0, spread: 1, rounded: 2, edge: 3 };
export const NN_RADIUS_UM = 50;

// state.py::classify_state
export function classifyState(areaPx, areaUm2, ecc, circ, solidity, edge, p = STATE) {
  if (edge) return 'edge';
  if (areaPx == null || areaPx < p.MIN_AREA_PX || ecc == null) return 'unknown';
  if (areaUm2 != null) return areaUm2 <= p.ROUNDED_AREA_UM2 && ecc <= p.ROUNDED_ECC ? 'rounded' : 'spread';
  if (circ != null && solidity != null) return circ >= p.FALLBACK_CIRCULARITY && solidity >= p.FALLBACK_SOLIDITY ? 'rounded' : 'spread';
  return 'unknown';
}

// Perimeter weights indexed by the 3x3 convolution code (skimage measure.perimeter, neighborhood=4).
const PW = new Float64Array(50);
[5, 7, 15, 17, 25, 27].forEach(i => { PW[i] = 1; });
[21, 33].forEach(i => { PW[i] = Math.SQRT2; });
[13, 23].forEach(i => { PW[i] = (1 + Math.SQRT2) / 2; });

// Perimeter (px) of the region `lab` in frame f (Int32Array view H*W), within bbox [y0,y1) x [x0,x1).
function perimeter(f, H, W, lab, y0, y1, x0, x1) {
  const inm = (y, x) => y >= y0 && y < y1 && x >= x0 && x < x1 && f[y * W + x] === lab;
  const isBorder = (y, x) => inm(y, x) && !(inm(y - 1, x) && inm(y + 1, x) && inm(y, x - 1) && inm(y, x + 1));
  let total = 0;
  for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) {
    if (!isBorder(y, x)) continue;          // only border pixels have odd codes (non-zero weight)
    let c = 1;
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      if (!dy && !dx) continue;
      if (isBorder(y + dy, x + dx)) c += dy && dx ? 10 : 2;
    }
    total += c < 50 ? PW[c] : 0;
  }
  return total;
}

// Convex hull (Andrew's monotone chain) of points [[x, y], ...] -> {area, perim}; null if degenerate.
export function hull(pts) {
  if (pts.length < 3) return null;
  const p = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower = [], upper = [];
  for (const q of p) { while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], q) <= 0) lower.pop(); lower.push(q); }
  for (let i = p.length - 1; i >= 0; i--) { const q = p[i]; while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], q) <= 0) upper.pop(); upper.push(q); }
  const h = lower.slice(0, -1).concat(upper.slice(0, -1));
  if (h.length < 3) return null;
  let a = 0, per = 0;
  for (let i = 0; i < h.length; i++) {
    const u = h[i], v = h[(i + 1) % h.length];
    a += u[0] * v[1] - v[0] * u[1];
    per += Math.hypot(v[0] - u[0], v[1] - u[1]);
  }
  a = Math.abs(a) / 2;
  return a > 0 ? { area: a, perim: per } : null;
}

// regionprops_frame for one frame: {id: props}. f = Int32Array (H*W). Options: umPerPx, withSolidity, withPerimeter.
export function regionpropsFrame(f, H, W, { umPerPx = null, withSolidity = false, withPerimeter = true, state = STATE } = {}) {
  const acc = new Map();
  for (let y = 0, i = 0; y < H; y++) for (let x = 0; x < W; x++, i++) {
    const l = f[i];
    if (l <= 0) continue;
    let a = acc.get(l);
    if (!a) { a = { n: 0, sy: 0, sx: 0, y0: y, y1: y, x0: x, x1: x, rowMin: new Map(), rowMax: new Map() }; acc.set(l, a); }
    a.n++; a.sy += y; a.sx += x;
    if (y < a.y0) a.y0 = y; if (y > a.y1) a.y1 = y; if (x < a.x0) a.x0 = x; if (x > a.x1) a.x1 = x;
    if (!a.rowMin.has(y)) a.rowMin.set(y, x);
    a.rowMax.set(y, x);
  }
  for (const a of acc.values()) { a.cy = a.sy / a.n; a.cx = a.sx / a.n; a.mrr = 0; a.mcc = 0; a.mrc = 0; }
  for (let y = 0, i = 0; y < H; y++) for (let x = 0; x < W; x++, i++) {
    const l = f[i];
    if (l <= 0) continue;
    const a = acc.get(l), dr = y - a.cy, dc = x - a.cx;
    a.mrr += dr * dr; a.mcc += dc * dc; a.mrc += dr * dc;
  }
  const scale = umPerPx || null, out = {};
  for (const lab of [...acc.keys()].sort((p, q) => p - q)) {
    const a = acc.get(lab), area = a.n;
    let major = 0, minor = 0, ecc = 0, orient = 0;
    if (area >= 3) {
      const mrr = a.mrr / area + 1 / 12, mcc = a.mcc / area + 1 / 12, mrc = a.mrc / area;
      const half = (mrr + mcc) / 2, diff = Math.sqrt(((mrr - mcc) / 2) ** 2 + mrc * mrc);
      const l1 = half + diff, l2 = Math.max(half - diff, 0);
      major = 4 * Math.sqrt(l1); minor = 4 * Math.sqrt(l2);
      ecc = l1 > 0 ? Math.sqrt(1 - l2 / l1) : 0;
      orient = 0.5 * Math.atan2(2 * mrc, mrr - mcc);
    }
    const bh = a.y1 - a.y0 + 1, bw = a.x1 - a.x0 + 1;
    const rec = {
      cell_id: lab, area_px: area, centroid_x: a.cx, centroid_y: a.cy,
      bbox_x0: a.x0, bbox_y0: a.y0, bbox_x1: a.x1 + 1, bbox_y1: a.y1 + 1,
      major_axis_px: major, minor_axis_px: minor, eccentricity: ecc,
      aspect_ratio: minor > 0 ? major / minor : NaN, orientation_rad: orient,
      extent: area / (bh * bw), equiv_diameter_px: Math.sqrt(4 * area / Math.PI),
      edge: a.x0 === 0 || a.y0 === 0 || a.x1 + 1 >= W || a.y1 + 1 >= H,
    };
    if (scale) {
      rec.area_um2 = area * scale * scale; rec.centroid_x_um = a.cx * scale; rec.centroid_y_um = a.cy * scale;
      rec.major_axis_um = major * scale; rec.minor_axis_um = minor * scale; rec.equiv_diameter_um = rec.equiv_diameter_px * scale;
    }
    let hl;
    const getHull = () => {
      if (hl === undefined) {
        const pts = [];
        for (const [y, x] of a.rowMin) { pts.push([x, y]); const xm = a.rowMax.get(y); if (xm !== x) pts.push([xm, y]); }
        hl = hull(pts);
      }
      return hl;
    };
    if (withSolidity) { const h = getHull(); rec.solidity = h ? Math.min(area / h.area, 1) : NaN; }
    if (withPerimeter) {
      const per = perimeter(f, H, W, lab, a.y0, a.y1 + 1, a.x0, a.x1 + 1);
      rec.perimeter_px = per;
      rec.circularity = per > 0 ? 4 * Math.PI * area / (per * per) : NaN;
      const h = getHull();
      rec.convexity = per > 0 && h ? Math.min(h.perim / per, 1) : NaN;
      if (scale) rec.perimeter_um = per * scale;
    }
    rec.state = classifyState(area, rec.area_um2 ?? null, ecc, rec.circularity ?? null, rec.solidity ?? null, rec.edge, state);
    out[lab] = rec;
  }
  return out;
}

// neighbors.py::frame_nn -> {nn, cnt}; distances in scaled units.
export function frameNN(cys, cxs, scale = 1, radius = NN_RADIUS_UM) {
  const n = cys.length, nn = new Array(n).fill(NaN), cnt = new Array(n).fill(0);
  if (n < 2) return { nn, cnt };
  for (let i = 0; i < n; i++) {
    let best = Infinity, c = 0;
    for (let j = 0; j < n; j++) {
      if (j === i) continue;
      const d = Math.hypot((cys[j] - cys[i]) * scale, (cxs[j] - cxs[i]) * scale);
      if (d < best) best = d;
      if (radius && d <= radius) c++;
    }
    nn[i] = best; cnt[i] = c;
  }
  return { nn, cnt };
}

// The frame view of a stack {labels, T, H, W}.
export const frameOf = (m, t) => m.labels.subarray(t * m.H * m.W, (t + 1) * m.H * m.W);

// per_frame_records without the contact columns: [{frame, time_min, ...props, nn_dist_um|px, n_neighbors}].
export function perFrameRecords(m, { umPerPx = null, dtMin = null, withSolidity = false, state = STATE, nnRadius = NN_RADIUS_UM, onFrame } = {}) {
  const scale = umPerPx || 1, nnKey = `nn_dist_${umPerPx ? 'um' : 'px'}`, rows = [];
  for (let t = 0; t < m.T; t++) {
    const props = regionpropsFrame(frameOf(m, t), m.H, m.W, { umPerPx, withSolidity, withPerimeter: true, state });
    const ids = Object.keys(props).map(Number).sort((a, b) => a - b);
    const { nn, cnt } = frameNN(ids.map(i => props[i].centroid_y), ids.map(i => props[i].centroid_x), scale, nnRadius);
    ids.forEach((id, j) => {
      const row = { frame: t };
      if (dtMin) row.time_min = t * dtMin;
      Object.assign(row, props[id]);
      row[nnKey] = nn[j]; row.n_neighbors = cnt[j];
      rows.push(row);
    });
    if (onFrame) onFrame(t + 1, m.T);
  }
  return rows;
}

// {id: [[y, x] | [NaN, NaN] per frame]} centroid history in px, from per-frame records.
export function centroidHistory(records, T) {
  const out = {};
  for (const r of records) {
    if (!out[r.cell_id]) out[r.cell_id] = Array.from({ length: T }, () => [NaN, NaN]);
    out[r.cell_id][r.frame] = [r.centroid_y, r.centroid_x];
  }
  return out;
}
