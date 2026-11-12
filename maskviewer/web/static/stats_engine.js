// Cross-recording statistics (recording = experimental unit): a JS port of compare.py (aggregate,
// per_condition_summary, ensemble_by_condition with mean +/- SEM, cohens_d, ranked_group_comparisons without the
// bootstrap CI / mixed-model columns), stats_extra.benjamini_hochberg, and scipy.stats.mannwhitneyu (two-sided,
// method 'auto': exact null distribution when either sample has <= 8 values and there are no ties, else the normal
// approximation with tie and continuity corrections). Checked against the Python code by stats_engine.test.mjs.

const fin = a => a.filter(Number.isFinite);
const mean = a => a.reduce((s, v) => s + v, 0) / a.length;
const variance = a => { const m = mean(a); return a.reduce((s, v) => s + (v - m) ** 2, 0) / (a.length - 1); };
const median = a => { const s = a.slice().sort((p, q) => p - q), n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; };

// compare.aggregate: one row per recording, mean over cells of every numeric column (+ condition, n_cells).
export function aggregate(perCell) {
  const groups = new Map();
  for (const r of perCell) { if (!groups.has(r.recording)) groups.set(r.recording, []); groups.get(r.recording).push(r); }
  const cols = [...new Set(perCell.flatMap(r => Object.keys(r)))].filter(c => c !== 'recording' && c !== 'condition'
    && perCell.some(r => typeof r[c] === 'number'));
  const out = [];
  for (const [rec, rows] of [...groups].sort((a, b) => (a[0] < b[0] ? -1 : 1))) {
    const o = { recording: rec };
    for (const c of cols) { const v = fin(rows.map(r => r[c])); o[c] = v.length ? mean(v) : NaN; }
    o.condition = rows[0].condition; o.n_cells = rows.length;
    out.push(o);
  }
  return out;
}

// Normal survival function via erfc (series for small x, continued fraction for large x).
function erfc(x) {
  if (x < 0) return 2 - erfc(-x);
  if (x < 2.5) {                                   // erf Taylor series
    let sum = x, term = x, n = 0;
    while (Math.abs(term) > 1e-17 * Math.abs(sum)) { n++; term *= -x * x / n; sum += term / (2 * n + 1); }
    return 1 - 2 / Math.sqrt(Math.PI) * sum;
  }
  let f = x, C = x, D = 0;                          // Lentz continued fraction for erfc
  for (let i = 1; i < 300; i++) {
    const a = i / 2;
    D = x + a * D; C = x + a / C; D = 1 / D;
    const delta = C * D; f *= delta;
    if (Math.abs(delta - 1) < 1e-16) break;
  }
  return Math.exp(-x * x) / Math.sqrt(Math.PI) / f;
}
export const normSf = z => 0.5 * erfc(z / Math.SQRT2);

function rankAvg(v) {
  const idx = v.map((x, i) => i).sort((a, b) => v[a] - v[b]), ranks = new Array(v.length), ties = [];
  for (let i = 0; i < idx.length;) {
    let j = i;
    while (j + 1 < idx.length && v[idx[j + 1]] === v[idx[i]]) j++;
    for (let k = i; k <= j; k++) ranks[idx[k]] = (i + j) / 2 + 1;
    ties.push(j - i + 1); i = j + 1;
  }
  return { ranks, ties };
}

// Number of arrangements with each U value for sample sizes (m, n) -> Float64Array of length m*n+1.
function uCounts(m, n) {
  let prev = Array.from({ length: n + 1 }, () => new Float64Array([1]));   // m = 0
  for (let i = 1; i <= m; i++) {
    const cur = [new Float64Array([1])];
    for (let j = 1; j <= n; j++) {
      const a = cur[j - 1], b = prev[j], out = new Float64Array(i * j + 1);   // f(i,j,k) = f(i,j-1,k) + f(i-1,j,k-j)
      for (let k = 0; k < out.length; k++) out[k] = (k < a.length ? a[k] : 0) + (k - j >= 0 && k - j < b.length ? b[k - j] : 0);
      cur.push(out);
    }
    prev = cur;
  }
  return prev[n];
}

// scipy.stats.mannwhitneyu(x, y, alternative='two-sided') -> {U, p, method}
export function mannWhitney(x, y) {
  const n1 = x.length, n2 = y.length, { ranks, ties } = rankAvg(x.concat(y));
  const R1 = ranks.slice(0, n1).reduce((a, b) => a + b, 0), U1 = R1 - n1 * (n1 + 1) / 2, U2 = n1 * n2 - U1;
  const U = Math.max(U1, U2), hasTies = ties.some(t => t > 1);
  let p, method;
  if ((n1 > 8 && n2 > 8) || hasTies) {
    method = 'asymptotic';
    const nn = n1 + n2, tie = ties.reduce((s, t) => s + t ** 3 - t, 0);
    const s = Math.sqrt(n1 * n2 / 12 * ((nn + 1) - tie / (nn * (nn - 1))));
    let num = U1 - n1 * n2 / 2;
    num -= 0.5 * Math.sign(num);
    p = 2 * normSf(Math.abs(num / s));
  } else {
    method = 'exact';
    const c = uCounts(Math.min(n1, n2), Math.max(n1, n2)), tot = c.reduce((a, b) => a + b, 0);
    let tail = 0;
    for (let k = Math.round(U); k < c.length; k++) tail += c[k];
    p = 2 * tail / tot;
  }
  return { U: U1, p: Math.min(1, Math.max(0, p)), method };
}

export function cohensD(control, test) {
  const a = fin(control), b = fin(test);
  if (a.length < 2 || b.length < 2) return NaN;
  const sp = Math.sqrt(((a.length - 1) * variance(a) + (b.length - 1) * variance(b)) / (a.length + b.length - 2));
  return sp > 0 ? (mean(b) - mean(a)) / sp : NaN;
}

// stats_extra.benjamini_hochberg (NaN-aware step-up q-values)
export function benjaminiHochberg(ps) {
  const ok = ps.map((p, i) => [p, i]).filter(([p]) => Number.isFinite(p)).sort((a, b) => a[0] - b[0]);
  const m = ok.length, q = ps.map(() => NaN);
  let run = 1;
  for (let k = m - 1; k >= 0; k--) { run = Math.min(run, ok[k][0] * m / (k + 1)); q[ok[k][1]] = Math.min(run, 1); }
  return q;
}

const valuesBy = (perRec, metric, g) => fin(perRec.filter(r => r.condition === g).map(r => r[metric]));

// compare.ranked_group_comparisons (p, Bonferroni, BH-FDR, Cohen's d), p-ascending.
export function rankedComparisons(perRec, metric, groups = null) {
  const conds = groups || [...new Set(perRec.map(r => r.condition))].sort();
  const rows = [];
  for (let i = 0; i < conds.length; i++) for (const b of conds.slice(i + 1)) {
    const a = conds[i], va = valuesBy(perRec, metric, a), vb = valuesBy(perRec, metric, b), all = va.concat(vb);
    let p = NaN;
    if (va.length && vb.length && all.length >= 3 && Math.max(...all) - Math.min(...all) > 0) p = mannWhitney(va, vb).p;
    rows.push({ group_a: a, group_b: b, n_a: va.length, n_b: vb.length, mean_a: va.length ? mean(va) : NaN,
      mean_b: vb.length ? mean(vb) : NaN, p, cohen_d: cohensD(va, vb) });
  }
  const m = rows.filter(r => Number.isFinite(r.p)).length, qs = benjaminiHochberg(rows.map(r => r.p));
  rows.forEach((r, i) => { r.p_bonferroni = Number.isFinite(r.p) && m ? Math.min(r.p * m, 1) : NaN; r.q_fdr = qs[i]; });
  return rows.sort((x, y) => (Number.isFinite(x.p) ? x.p : 2) - (Number.isFinite(y.p) ? y.p : 2));
}

// compare.per_condition_summary -> [{group, n, mean, sem, median}]
export function perConditionSummary(perRec, metric) {
  const out = [];
  for (const g of [...new Set(perRec.map(r => r.condition))].sort()) {
    const v = valuesBy(perRec, metric, g);
    if (!v.length) continue;
    out.push({ group: g, n: v.length, mean: mean(v), sem: v.length > 1 ? Math.sqrt(variance(v)) / Math.sqrt(v.length) : 0, median: median(v) });
  }
  return out;
}

// compare.ensemble_by_condition(stat='mean'): long rows [{condition, tau, value}] -> {cond: {tau, centre, lo, hi}}
export function ensembleByCondition(long) {
  const out = {};
  for (const cond of [...new Set(long.map(r => r.condition))].sort()) {
    const g = long.filter(r => r.condition === cond), taus = [...new Set(g.map(r => r.tau))].sort((a, b) => a - b);
    const e = { tau: [], centre: [], lo: [], hi: [] };
    for (const t of taus) {
      const v = fin(g.filter(r => r.tau === t).map(r => r.value));
      e.tau.push(t);
      if (!v.length) { e.centre.push(NaN); e.lo.push(NaN); e.hi.push(NaN); continue; }
      const m = mean(v), sem = v.length > 1 ? Math.sqrt(variance(v)) / Math.sqrt(v.length) : 0;
      e.centre.push(m); e.lo.push(m - sem); e.hi.push(m + sem);
    }
    out[cond] = e;
  }
  return out;
}
