// JS vs Python check (#/validate): the browser analysis of the demo recordings compared, value by value, with the
// repo's Python code (per-cell tables from exporters.per_cell_table, and compare.build_comparison's per-recording
// means, ensemble curves and Mann-Whitney tests), exported by the API.
import { $, api, app, esc, route } from './core.js';
import { f, label } from './fmt.js';
import { aggregate, ensembleByCondition, rankedComparisons } from './stats_engine.js';
import { analyse, ensureWorkspace, loadDemo, ws } from './state.js';

const RTOL = 1e-9;
const rel = (a, b) => (a === b ? 0 : Math.abs(a - b) / Math.max(Math.abs(b), 1e-12));

function compareRows(js, py, key = 'cell_id') {
  const stats = {}, map = new Map(js.map(r => [r[key], r]));
  let n = 0, bad = 0, missing = new Set();
  for (const p of py) {
    const j = map.get(p[key]);
    if (!j) { bad++; continue; }
    for (const [c, v] of Object.entries(p)) {
      if (typeof v !== 'number' && v !== null) continue;
      if (!(c in j)) { missing.add(c); continue; }
      const jv = j[c], pNaN = v === null, jNaN = !Number.isFinite(jv);
      const d = pNaN && jNaN ? 0 : pNaN !== jNaN ? Infinity : rel(jv, v);
      n++; if (d > RTOL) bad++;
      stats[c] = Math.max(stats[c] ?? 0, d);
    }
  }
  return { n, bad, stats, missing: [...missing].sort() };
}

route('validate', async () => {
  await ensureWorkspace();
  await loadDemo();
  app().innerHTML = `<h1>JS vs Python check</h1>
    <p class="lead">The browser recomputes every demo recording with the JS ports and compares each value with what the repo's Python code
      produced on the same masks (tolerance: relative difference ≤ ${RTOL}). The node test <code>engine.test.mjs</code> runs the same kind of check in CI.</p>
    <div id="v-out"><p class="mute">Computing…</p></div>`;
  const demo = ws.recordings.filter(r => r.source === 'demo');
  const out = [];
  let total = 0, fails = 0, missing = new Set();
  for (const r of demo) {
    const a = await analyse(r), ref = await api(`/demo/${encodeURIComponent(r.label)}/reference`);
    const c = compareRows(a.perCell, ref.per_cell);
    total += c.n; fails += c.bad; c.missing.forEach(m => missing.add(m));
    out.push({ label: r.label, ...c });
  }
  // the cross-recording comparison
  const py = await api('/demo/compare');
  const cells = demo.flatMap(r => r.analysis.perCell.map(c => ({ ...c, recording: r.label, condition: r.condition })));
  const perRec = aggregate(cells);
  const cr = compareRows(perRec, py.per_recording, 'recording');
  const ranked = py.headline.filter(m => py.ranked[m]?.length).map(m => {
    const j = rankedComparisons(perRec, m)[0], p = py.ranked[m][0];
    return { m, jp: j.p, pp: p.p, jd: j.cohen_d, pd: p.cohen_d, ok: rel(j.p, p.p) <= 1e-7 && rel(j.cohen_d, p.cohen_d) <= RTOL };
  });
  let curveMax = 0, curveN = 0;
  for (const key of ['msd', 'autocorr', 'dir_ratio', 'velcorr']) {
    const long = demo.flatMap(r => r.analysis.curves[key].map(p => ({ condition: r.condition, tau: p.tau, value: p.value })));
    const ens = ensembleByCondition(long);
    for (const [cond, e] of Object.entries(py.curves[key])) e.centre.forEach((v, i) => {
      if (v === null) return;
      curveN++; curveMax = Math.max(curveMax, rel(ens[cond].centre[i], v));
    });
  }
  if (!$('#v-out')) return;                         // page left while computing
  const ok = fails === 0 && cr.bad === 0 && ranked.every(r => r.ok) && curveMax <= RTOL;
  $('#v-out').innerHTML = `
    <div class="tiles"><div class="tile"><b class="${ok ? 'good' : 'bad'}">${ok ? 'agree' : 'differ'}</b><span>overall</span></div>
      <div class="tile"><b>${total.toLocaleString()}</b><span>per-cell values compared</span></div>
      <div class="tile"><b>${cr.n}</b><span>per-recording means compared</span></div>
      <div class="tile"><b>${curveN}</b><span>ensemble-curve points compared (max rel. diff ${f(curveMax)})</span></div></div>
    <h2>Per-cell tables</h2>
    <div class="scroll"><table class="tbl"><thead><tr><th>recording</th><th>values</th><th>outside tolerance</th><th>largest relative difference</th></tr></thead><tbody>
      ${out.map(o => { const worst = Object.entries(o.stats).sort((a, b) => b[1] - a[1])[0];
        return `<tr><td>${esc(o.label)}</td><td>${o.n}</td><td class="${o.bad ? 'bad' : 'good'}">${o.bad}</td><td>${worst ? `${f(worst[1])} (${esc(label(worst[0]))})` : '–'}</td></tr>`; }).join('')}
    </tbody></table></div>
    <h2>Pairwise tests on the headline metrics</h2>
    <div class="scroll"><table class="tbl"><thead><tr><th>metric</th><th>p (JS)</th><th>p (Python)</th><th>Cohen's d (JS)</th><th>d (Python)</th><th></th></tr></thead><tbody>
      ${ranked.map(r => `<tr><td>${esc(label(r.m))}</td><td>${f(r.jp, 6)}</td><td>${f(r.pp, 6)}</td><td>${f(r.jd, 6)}</td><td>${f(r.pd, 6)}</td><td class="${r.ok ? 'good' : 'bad'}">${r.ok ? 'agree' : 'differ'}</td></tr>`).join('')}
    </tbody></table></div>
    <h2>Columns only in the Python table</h2>
    <p>${[...missing].map(m => `<code>${esc(m)}</code>`).join(' ') || 'none'}</p>
    <p class="small mute">These need the desktop app (or the local web app's "Python table" on Load data): cell–cell contact columns
      (<code>contacts.py</code>) and the Fürth persistent-random-walk fit (<code>scipy.optimize.curve_fit</code>) are not ported.</p>`;
});
