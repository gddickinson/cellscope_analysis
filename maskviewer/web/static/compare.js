// Compare (#/compare): the Comparison window's core in the browser. Recording = experimental unit: per-cell rows are
// averaged per recording (compare.aggregate), grouped by condition, shown as a superplot (recording means over the
// cells), summarised (n, mean, SEM, median), tested pairwise (Mann-Whitney U + Bonferroni / BH-FDR + Cohen's d),
// and the DiPer ensemble curves are averaged over recordings per condition (mean +/- SEM).
import { $, app, download, esc, route } from './core.js';
import { legend, lineChart, strip } from './charts.js';
import { colour, f, label, pval, tip } from './fmt.js';
import { toCsv } from './tables_engine.js';
import { aggregate, ensembleByCondition, perConditionSummary, rankedComparisons } from './stats_engine.js';
import { allPerCell, analyseAll, ensureWorkspace, ws } from './state.js';

const ui = { metric: 'persistence_dir_autocorr', minFrames: 1, minCells: 1 };

route('compare', async () => {
  await ensureWorkspace();
  app().innerHTML = `<h1>Compare conditions</h1>
    <p class="lead">Every recording in the workspace, grouped by its condition. Each recording contributes one value (the mean over its
      cells), as in the desktop Comparison window.</p>
    ${ws.demo ? '<div class="callout">The demo conditions are two <b>simulated motion models</b> (persistent vs random walk), not treatments: they show how the comparison works, nothing more.</div>' : ''}
    <div class="progress" id="k-prog"><div></div></div><div id="k-body"></div>`;
  await analyseAll(p => { $('#k-prog > div').style.width = `${p * 100}%`; });
  if (!$('#k-prog')) return;                        // page left while computing
  $('#k-prog').classList.add('hide');
  const conds = [...new Set(ws.recordings.map(r => r.condition))].sort(), cc = c => colour(conds.indexOf(c));

  function body() {
    const cells = allPerCell().filter(r => r.frames_tracked >= ui.minFrames);
    let perRec = aggregate(cells).filter(r => r.n_cells >= ui.minCells);
    const cols = Object.keys(perRec[0] || {}).filter(c => !['recording', 'condition', 'n_cells', 'cell_id', 'first_frame', 'last_frame'].includes(c)
      && perRec.some(r => Number.isFinite(r[c])));
    if (!cols.includes(ui.metric)) ui.metric = cols.find(c => c.startsWith('persistence')) || cols[0];
    const m = ui.metric, lagU = ws.recordings.every(r => r.dtMin) ? 'min' : 'frames';
    const groups = conds.map(c => ({ name: c, color: cc(c), values: perRec.filter(r => r.condition === c).map(r => r[m]), labels: perRec.filter(r => r.condition === c).map(r => r.recording) }));
    const under = conds.map(c => ({ name: c, color: cc(c), values: cells.filter(r => r.condition === c).map(r => r[m]) }));
    const summ = perConditionSummary(perRec, m), ranked = rankedComparisons(perRec, m, conds);
    const keep = new Set(perRec.map(r => r.recording));
    const curve = key => {
      const long = ws.recordings.filter(r => keep.has(r.label)).flatMap(r => r.analysis.curves[key].map(p => ({ condition: r.condition, tau: p.tau, value: p.value })));
      const ens = ensembleByCondition(long);
      return Object.entries(ens).map(([c, e]) => ({ name: c, color: cc(c), x: e.tau, y: e.centre, lo: e.lo, hi: e.hi }));
    };
    $('#k-body').innerHTML = `
      <div class="row small-ctl">
        <div><label for="k-m">Metric (per-recording mean)</label><select id="k-m">${cols.map(c => `<option value="${esc(c)}"${c === m ? ' selected' : ''}>${esc(label(c))}</option>`).join('')}</select></div>
        <div><label for="k-mf">Min frames per cell</label><input id="k-mf" type="number" min="1" value="${ui.minFrames}"></div>
        <div><label for="k-mc">Min cells per recording</label><input id="k-mc" type="number" min="1" value="${ui.minCells}"></div>
      </div>
      <p class="small mute">${esc(tip(m))}</p>
      <div class="two">
        <div class="panel"><h3>${esc(label(m))}</h3>${strip(groups, { ylabel: label(m), under })}
          <p class="small mute">Large points: recordings (the unit); faint points: their cells; bar: mean ± SEM over recordings.</p></div>
        <div class="panel"><h3>By condition</h3><div class="scroll"><table class="tbl"><thead><tr><th>condition</th><th>n rec.</th><th>mean</th><th>SEM</th><th>median</th></tr></thead>
          <tbody>${summ.map(s => `<tr><td><span class="cls" style="--c:${cc(s.group)}">${esc(s.group)}</span></td><td>${s.n}</td><td>${f(s.mean)}</td><td>${f(s.sem)}</td><td>${f(s.median)}</td></tr>`).join('')}</tbody></table></div>
          <h3>Pairwise tests</h3><div class="scroll"><table class="tbl"><thead><tr><th>A</th><th>B</th><th>n</th><th>p (MWU)</th><th>Bonferroni</th><th>q (BH)</th><th>Cohen's d</th></tr></thead>
          <tbody>${ranked.map(r => `<tr><td>${esc(r.group_a)}</td><td>${esc(r.group_b)}</td><td>${r.n_a}/${r.n_b}</td><td>${pval(r.p)}</td><td>${pval(r.p_bonferroni)}</td><td>${pval(r.q_fdr)}</td><td>${f(r.cohen_d)}</td></tr>`).join('') || '<tr><td colspan="7" class="mute">Needs at least two conditions.</td></tr>'}</tbody></table></div>
          <p class="small mute">Two-sided Mann-Whitney U on recording means (exact null distribution for small samples without ties, as SciPy); d = (B − A) / pooled SD. With 3 recordings per group the smallest possible two-sided p is 0.1.</p></div>
      </div>
      ${legend(conds.map(c => [c, cc(c)]))}
      <div class="charts">
        <div class="panel"><h3>Ensemble MSD</h3>${lineChart(curve('msd'), { xlabel: `lag (${lagU})`, ylabel: 'MSD (µm² or px²)', logx: true, logy: true })}</div>
        <div class="panel"><h3>Direction autocorrelation</h3>${lineChart(curve('autocorr'), { xlabel: `lag (${lagU})`, ylabel: 'mean cos θ', zero: true })}</div>
        <div class="panel"><h3>Directionality ratio d/D</h3>${lineChart(curve('dir_ratio'), { xlabel: `elapsed (${lagU})`, ylabel: 'd / D' })}</div>
        <div class="panel"><h3>Velocity autocorrelation</h3>${lineChart(curve('velcorr'), { xlabel: `lag (${lagU})`, ylabel: 'normalised ⟨v·v⟩', zero: true })}</div>
      </div>
      <p class="small mute">Curves: per-recording means over cells (all cells, no filters, as <code>build_comparison</code>), then mean ± SEM over the
        recordings of each condition (<code>ensemble_by_condition</code>). Recordings with too few cells are left out.</p>
      <button id="k-dl">Download per-recording table (CSV)</button>`;
    $('#k-m').onchange = e => { ui.metric = e.target.value; body(); };
    $('#k-mf').onchange = e => { ui.minFrames = +e.target.value || 1; body(); };
    $('#k-mc').onchange = e => { ui.minCells = +e.target.value || 1; body(); };
    $('#k-dl').onclick = () => download('per_recording.csv', toCsv(perRec), 'text/csv');
  }
  if (ws.recordings.length) body(); else $('#k-body').innerHTML = '<p>No recordings. <a href="#/data">Load data</a>.</p>';
});
