// Population (#/population): every cell of one recording (the desktop Population dock): flower plot of
// origin-centred tracks, a per-frame metric over time (each cell faint + mean +/- SEM), and this recording's
// DiPer curves (mean over cells: MSD, direction autocorrelation, directionality ratio, velocity autocorrelation).
import { $, app, esc, route } from './core.js';
import { flower, lineChart } from './charts.js';
import { cellRgb, label, tip } from './fmt.js';
import { analyse, current, ensureWorkspace, getRec, ws } from './state.js';

const ui = { metric: null, minFrames: 1, state: 'all', noEdge: true };

route('population', async args => {
  await ensureWorkspace();
  if (args[0] && getRec(args[0])) ws.current = args[0];
  const rec = current();
  if (!rec) { app().innerHTML = '<h1>Population</h1><p>No recordings loaded. <a href="#/data">Load data</a>.</p>'; return; }
  const hash = location.hash, a = await analyse(rec);
  if (location.hash !== hash) return;               // page left while computing
  const u = rec.umPerPx ? 'µm' : 'px', s = rec.umPerPx || 1, tl = rec.dtMin ? 'time (min)' : 'frame', lagU = rec.dtMin ? 'min' : 'frames';
  const metrics = (rec.umPerPx ? ['area_um2', 'perimeter_um'] : ['area_px', 'perimeter_px'])
    .concat(['circularity', 'convexity', 'eccentricity', 'aspect_ratio', 'extent', rec.umPerPx ? 'nn_dist_um' : 'nn_dist_px', 'n_neighbors']);
  if (!metrics.includes(ui.metric)) ui.metric = metrics[0];
  app().innerHTML = `<h1>Population</h1>
    <div class="row small-ctl">
      <div><label for="p-rec">Recording</label><select id="p-rec">${ws.recordings.map(r => `<option value="${esc(r.label)}"${r === rec ? ' selected' : ''}>${esc(r.label)} · ${esc(r.condition)}</option>`).join('')}</select></div>
      <div><label for="p-m">Per-frame metric</label><select id="p-m">${metrics.map(m => `<option value="${m}"${m === ui.metric ? ' selected' : ''}>${esc(label(m))}</option>`).join('')}</select></div>
      <div><label for="p-st">Frames in state</label><select id="p-st">${['all', 'spread', 'rounded'].map(v => `<option${v === ui.state ? ' selected' : ''}>${v}</option>`).join('')}</select></div>
      <div><label for="p-mf">Min frames tracked</label><input id="p-mf" type="number" min="1" value="${ui.minFrames}"></div>
    </div>
    <label class="check"><input type="checkbox" id="p-ne"${ui.noEdge ? ' checked' : ''}> exclude edge-truncated cell-frames</label>
    ${rec.source === 'demo' ? '<p><span class="badge syn">synthetic demo</span></p>' : ''}
    <div id="p-body"></div>`;
  $('#p-rec').onchange = e => { location.hash = '#/population/' + encodeURIComponent(e.target.value); };
  $('#p-m').onchange = e => { ui.metric = e.target.value; body(); };
  $('#p-st').onchange = e => { ui.state = e.target.value; body(); };
  $('#p-mf').onchange = e => { ui.minFrames = +e.target.value || 1; body(); };
  $('#p-ne').onchange = e => { ui.noEdge = e.target.checked; body(); };

  function body() {
    const keep = new Set(a.perCell.filter(r => r.frames_tracked >= ui.minFrames).map(r => r.cell_id));
    const ids = [...keep].sort((p, q) => p - q);
    const tracks = ids.map(id => {
      const c = a.cents[id].filter(p => Number.isFinite(p[0]));
      return { name: `cell ${id}`, color: `rgb(${cellRgb(id).join(',')})`, pts: c.map(p => [(p[1] - c[0][1]) * s, (p[0] - c[0][0]) * s]) };
    });
    const T = rec.masks.T, time = Array.from({ length: T }, (_, t) => (rec.dtMin ? t * rec.dtMin : t));
    const grid = Object.fromEntries(ids.map(id => [id, new Array(T).fill(NaN)]));
    for (const r of a.perFrame) {
      if (!keep.has(r.cell_id) || (ui.noEdge && r.state === 'edge') || (ui.state !== 'all' && r.state !== ui.state)) continue;
      grid[r.cell_id][r.frame] = r[ui.metric];
    }
    const mean = [], lo = [], hi = [];
    for (let t = 0; t < T; t++) {
      const v = ids.map(id => grid[id][t]).filter(Number.isFinite), m = v.reduce((p, q) => p + q, 0) / v.length;
      const sem = v.length > 1 ? Math.sqrt(v.reduce((p, q) => p + (q - m) ** 2, 0) / (v.length - 1) / v.length) : 0;
      mean.push(v.length ? m : NaN); lo.push(v.length ? m - sem : NaN); hi.push(v.length ? m + sem : NaN);
    }
    const series = ids.map(id => ({ name: `cell ${id}`, color: `rgb(${cellRgb(id).join(',')})`, x: time, y: grid[id], width: 1, opacity: 0.35 }))
      .concat([{ name: 'mean ± SEM', color: '#ffffff', x: time, y: mean, lo, hi, width: 2.2 }]);
    const c = a.curves, one = (rows, name, col) => [{ name, color: col, x: rows.map(r => r.tau), y: rows.map(r => r.value) }];
    $('#p-body').innerHTML = `<p class="small mute">${ids.length} of ${a.perCell.length} cells tracked for at least ${ui.minFrames} frames.</p>
      <div class="charts">
        <div class="panel"><h3>${esc(label(ui.metric))} over time</h3>${lineChart(series, { xlabel: tl, ylabel: label(ui.metric) })}<p class="small mute">${esc(tip(ui.metric))}</p></div>
        <div class="panel"><h3>Flower plot</h3>${flower(tracks, { unit: u })}<p class="small mute">Every track moved to start at the origin (y down, as in the image).</p></div>
        <div class="panel"><h3>MSD (mean over cells)</h3>${lineChart(one(c.msd, 'MSD', '#2ee6ff'), { xlabel: `lag (${lagU})`, ylabel: `MSD (${u}²)`, logx: true, logy: true, markers: true })}</div>
        <div class="panel"><h3>Direction autocorrelation</h3>${lineChart(one(c.autocorr, 'autocorrelation', '#ff4fd8'), { xlabel: `lag (${lagU})`, ylabel: 'mean cos θ', zero: true, markers: true })}</div>
        <div class="panel"><h3>Directionality ratio d/D</h3>${lineChart(one(c.dir_ratio, 'd/D', '#ffb02e'), { xlabel: `elapsed (${lagU})`, ylabel: 'd / D', markers: true })}</div>
        <div class="panel"><h3>Velocity autocorrelation</h3>${lineChart(one(c.velcorr, 'velocity autocorrelation', '#7dff6a'), { xlabel: `lag (${lagU})`, ylabel: 'normalised ⟨v·v⟩', zero: true, markers: true })}</div>
      </div>
      <p class="small mute">The four curves are this recording's rows of <code>compare.build_comparison</code> (mean over all its cells; DiPer
        definitions, matched to <code>diper_clone</code> in the Python tests). They ignore the filters above, as in the desktop app.</p>`;
  }
  body();
});
