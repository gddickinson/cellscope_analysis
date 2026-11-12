// Cells (#/cells): per-cell table of the current recording, all recordings, or a loaded CSV; filters (the
// Comparison window's track filters); histogram + scatter of any column; CSV downloads in exporters.py's layout.
import { $, app, download, esc, route } from './core.js';
import { histogram, legend, scatter } from './charts.js';
import { colour, f, label, tip } from './fmt.js';
import { toCsv, trackTable } from './tables_engine.js';
import { allPerCell, analyse, analyseAll, conditions, current, ensureWorkspace, ws } from './state.js';

const ui = { source: 'current', sort: null, dir: 1, minFrames: 1, minQuality: 0, noJumps: false, minBorder: 0, hx: null, sx: null, sy: null };
const DEFAULT_COLS = ['cell_id', 'frames_tracked', 'mean_area_um2', 'mean_area_px', 'mean_circularity', 'mean_eccentricity',
  'mean_speed_um_per_min', 'mean_speed_px_per_frame', 'persistence_dir_autocorr', 'straightness', 'frac_rounded', 'track_quality'];
const numericCols = rows => [...new Set(rows.flatMap(r => Object.keys(r)))].filter(c => rows.some(r => typeof r[c] === 'number' && Number.isFinite(r[c])));

route('cells', async () => {
  await ensureWorkspace();
  const rec = current();
  app().innerHTML = `<h1>Cells</h1>
    <p class="lead">One row per tracked cell: track, shape (means and medians over frames), motion, run-and-tumble and quality columns,
      computed in your browser by the JS port of <code>exporters.per_cell_table</code>.</p>
    <div class="row small-ctl">
      <div><label for="c-src">Table</label><select id="c-src"></select></div>
      <div><label for="c-mf">Min frames tracked</label><input id="c-mf" type="number" min="1" step="1"></div>
      <div><label for="c-mq">Min track quality (0–1)</label><input id="c-mq" type="number" min="0" max="1" step="0.05"></div>
      <div><label for="c-mb">Min distance from image edge</label><input id="c-mb" type="number" min="0" step="1"></div>
    </div>
    <label class="check"><input type="checkbox" id="c-nj"> only tracks without jump steps (no suspected ID swaps)</label>
    <div class="progress" id="c-prog"><div></div></div>
    <div id="c-body"></div>`;
  const srcs = [['current', `current recording (${rec ? esc(rec.label) : '–'})`], ['all', 'all recordings in the workspace'],
    ...ws.tables.map((t, i) => [`csv:${i}`, `CSV: ${esc(t.name)}`])];
  if (!srcs.some(s => s[0] === ui.source)) ui.source = 'current';
  $('#c-src').innerHTML = srcs.map(([v, l]) => `<option value="${v}"${v === ui.source ? ' selected' : ''}>${l}</option>`).join('');
  for (const [id, key] of [['c-mf', 'minFrames'], ['c-mq', 'minQuality'], ['c-mb', 'minBorder']]) {
    $('#' + id).value = ui[key]; $('#' + id).onchange = e => { ui[key] = +e.target.value || 0; body(); };
  }
  $('#c-nj').checked = ui.noJumps; $('#c-nj').onchange = e => { ui.noJumps = e.target.checked; body(); };
  $('#c-src').onchange = e => { ui.source = e.target.value; load(); };
  const prog = $('#c-prog > div');
  let rows = [];

  async function load() {
    $('#c-prog').classList.remove('hide');
    if (ui.source === 'current' && rec) rows = (await analyse(rec, p => { prog.style.width = `${p * 100}%`; })).perCell.map(r => ({ recording: rec.label, condition: rec.condition, ...r }));
    else if (ui.source === 'all') { await analyseAll(p => { prog.style.width = `${p * 100}%`; }); rows = allPerCell(); }
    else rows = ws.tables[+ui.source.split(':')[1]]?.rows || [];
    if (!$('#c-prog')) return;                      // page left while computing
    $('#c-prog').classList.add('hide');
    body();
  }

  function filtered() {
    const border = Object.keys(rows[0] || {}).find(c => c.startsWith('min_border_dist_'));
    return rows.filter(r => (r.frames_tracked == null || r.frames_tracked >= ui.minFrames)
      && (r.track_quality == null || !(r.track_quality < ui.minQuality))
      && (!ui.noJumps || !r.n_track_jumps)
      && (!border || !ui.minBorder || r[border] >= ui.minBorder));
  }

  function body() {
    const all = filtered(), cols = numericCols(rows);
    const scaled = cols.includes('mean_area_um2');            // show µm columns, not both unit variants
    const show = DEFAULT_COLS.filter(c => cols.includes(c) && !(scaled && /_px($|_per)/.test(c)));
    const head = ['recording', 'condition'].filter(c => rows.some(r => r[c] != null));
    const tcols = head.concat(show.length > 2 ? show : cols.slice(0, 12));
    if (ui.sort && tcols.includes(ui.sort)) all.sort((a, b) => ((a[ui.sort] > b[ui.sort]) - (a[ui.sort] < b[ui.sort])) * ui.dir);
    const pick = (k, d) => (cols.includes(ui[k]) ? ui[k] : cols.find(c => c.startsWith(d) && (!scaled || !/_px($|_per)/.test(c))) || cols.find(c => c.startsWith(d)) || cols[0]);
    ui.hx = pick('hx', 'persistence'); ui.sx = pick('sx', 'mean_area'); ui.sy = pick('sy', 'mean_speed');
    const groups = [...new Set(all.map(r => r.condition ?? 'all'))].sort();
    const gc = g => colour(conditions().indexOf(g) >= 0 ? conditions().indexOf(g) : groups.indexOf(g));
    const sel = (id, v) => `<select id="${id}">${cols.map(c => `<option value="${esc(c)}"${c === v ? ' selected' : ''}>${esc(label(c))}</option>`).join('')}</select>`;
    $('#c-body').innerHTML = `
      <p class="small mute">${all.length} of ${rows.length} cells pass the filters. Columns not computed in the browser (cell–cell contacts, solidity, Fürth fit, edge dynamics) are in the desktop app's export.</p>
      <div class="charts">
        <div class="panel"><h3>Histogram</h3><label for="c-hx">Column</label>${sel('c-hx', ui.hx)}
          ${histogram(groups.map(g => ({ name: g, color: gc(g), values: all.filter(r => (r.condition ?? 'all') === g).map(r => r[ui.hx]) })), { xlabel: label(ui.hx) })}
          ${groups.length > 1 ? legend(groups.map(g => [g, gc(g)])) : ''}<p class="small mute">${esc(tip(ui.hx))}</p></div>
        <div class="panel"><h3>Scatter</h3><div class="row"><div><label for="c-sx">X</label>${sel('c-sx', ui.sx)}</div><div><label for="c-sy">Y</label>${sel('c-sy', ui.sy)}</div></div>
          ${scatter(all.map(r => ({ x: r[ui.sx], y: r[ui.sy], c: gc(r.condition ?? 'all'), t: `${r.recording ?? ''} cell ${r.cell_id ?? ''}` })), { xlabel: label(ui.sx), ylabel: label(ui.sy) })}</div>
      </div>
      <div class="row"><div>
        <button id="c-dl">Download this table (CSV)</button>
        ${ui.source === 'current' && rec ? '<button class="alt" id="c-dlf">Per-frame CSV</button><button class="alt" id="c-dlt">Tracks CSV</button>' : ''}
      </div></div>
      <div class="scroll"><table class="tbl"><thead><tr>${tcols.map(c => `<th title="${esc(tip(c))}"><button data-sort="${esc(c)}">${esc(label(c))}${ui.sort === c ? (ui.dir > 0 ? ' ▲' : ' ▼') : ''}</button></th>`).join('')}</tr></thead>
      <tbody>${all.slice(0, 500).map(r => `<tr${r.recording && r.cell_id != null && ws.recordings.some(x => x.label === r.recording) ? ` class="click" tabindex="0" data-rec="${esc(r.recording)}"` : ''}>${tcols.map(c => `<td>${esc(typeof r[c] === 'number' ? f(r[c]) : r[c] ?? '')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
      ${all.length > 500 ? '<p class="small mute">First 500 rows shown; the download has all of them.</p>' : ''}`;
    for (const [id, key] of [['c-hx', 'hx'], ['c-sx', 'sx'], ['c-sy', 'sy']]) $('#' + id).onchange = e => { ui[key] = e.target.value; body(); };
    $('#c-body').querySelectorAll('[data-sort]').forEach(b => { b.onclick = () => { ui.dir = ui.sort === b.dataset.sort ? -ui.dir : 1; ui.sort = b.dataset.sort; body(); }; });
    $('#c-body').querySelectorAll('tr[data-rec]').forEach(tr => {
      const go = () => { location.hash = '#/viewer/' + encodeURIComponent(tr.dataset.rec); };
      tr.onclick = go; tr.onkeydown = e => { if (e.key === 'Enter') go(); };
    });
    $('#c-dl').onclick = () => download(`${ui.source === 'current' && rec ? rec.label + '_' : ''}per_cell.csv`, toCsv(all), 'text/csv');
    if ($('#c-dlf')) {
      $('#c-dlf').onclick = () => download(`${rec.label}_per_frame.csv`, toCsv(rec.analysis.perFrame), 'text/csv');
      $('#c-dlt').onclick = () => download(`${rec.label}_tracks.csv`, toCsv(trackTable(rec.analysis.cents, { umPerPx: rec.umPerPx, dtMin: rec.dtMin })), 'text/csv');
    }
  }
  if (rec || ws.tables.length) load(); else $('#c-body').innerHTML = '<p>No data loaded. <a href="#/data">Load data</a>.</p>';
});
