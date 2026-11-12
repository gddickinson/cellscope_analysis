// Load data (#/data): add the user's own CellScope results to the workspace (masks.npz + optional .ome.tif and
// .ome.json sidecar, read locally), load a CSV table, edit conditions and scale, remove recordings. On the local app a
// recording's masks can also go to the Python API for the full per-cell table (contacts, solidity, Fuerth fit ...).
import { $, api, app, download, esc, isStatic, needsServer, route } from './core.js';
import { f } from './fmt.js';
import { toCsv } from './tables_engine.js';
import { addCsv, addUpload, ensureWorkspace, removeRecording, setScale, ws } from './state.js';

route('data', async () => {
  await ensureWorkspace();
  app().innerHTML = `<h1>Load data</h1>
    <p class="lead">Open the output of a CellScope run: a recording folder holds <code>&lt;name&gt;.ome.tif</code>, its sidecar
      <code>&lt;name&gt;.ome.json</code> (<code>um_per_px</code>, <code>time_interval_min</code>, <code>channel_names</code>) and
      <code>pipeline_results/masks.npz</code> (key <code>labels</code>: a <code>(T, H, W)</code> integer stack, 0 = background, the same ID = the same
      tracked cell in every frame). Files are read in this browser tab and never uploaded${isStatic() ? '' : ' (unless you ask for the Python table below)'}.</p>
    <form class="panel" id="d-form">
      <h3>Add a recording</h3>
      <div class="row">
        <div><label for="d-masks">masks.npz (required)</label><input type="file" id="d-masks" accept=".npz" required></div>
        <div><label for="d-tif">Recording .ome.tif (optional, for the image)</label><input type="file" id="d-tif" accept=".tif,.tiff"></div>
        <div><label for="d-json">Sidecar .ome.json (optional)</label><input type="file" id="d-json" accept=".json"></div>
      </div>
      <div class="row">
        <div><label for="d-label">Name</label><input id="d-label" placeholder="from the file name"></div>
        <div><label for="d-cond">Condition</label><input id="d-cond" placeholder="e.g. WT" list="d-conds"><datalist id="d-conds">${[...new Set(ws.recordings.map(r => r.condition))].map(c => `<option value="${esc(c)}">`).join('')}</datalist></div>
        <div><label for="d-um">Pixel size (µm/px)</label><input id="d-um" type="number" step="any" min="0" placeholder="sidecar / OME value"></div>
        <div><label for="d-dt">Frame interval (min)</label><input id="d-dt" type="number" step="any" min="0" placeholder="sidecar value"></div>
      </div>
      <button type="submit">Add recording</button><span class="small mute" id="d-msg" role="status"></span>
      <p class="small mute">Without a pixel size the measurements stay in pixels and the cell state falls back to the
        circularity/solidity rule (here: "unknown", since solidity is not computed by default), as in the desktop app. The browser reader handles
        uncompressed or zlib TIFF stacks of one position; a raw multi-position Micro-Manager file may need the desktop app.</p>
    </form>
    <div class="panel"><h3>Add a CSV table</h3>
      <label for="d-csv">Per-cell CSV (exported by the desktop app's Export CSV, or CellScope's <code>per_cell.csv</code>)</label>
      <input type="file" id="d-csv" accept=".csv,text/csv"><span class="small mute" id="d-csvmsg" role="status"></span>
      <p class="small mute">Shown on the <a href="#/cells">Cells</a> page (table, filters, histogram, scatter).</p></div>
    <h2>Workspace</h2><div id="d-list"></div>`;
  $('#d-form').onsubmit = async e => {
    e.preventDefault();
    const msg = $('#d-msg');
    msg.textContent = ' reading…';
    try {
      const rec = await addUpload({ masks: $('#d-masks').files[0], tif: $('#d-tif').files[0], sidecar: $('#d-json').files[0],
        label: $('#d-label').value.trim(), condition: $('#d-cond').value.trim(), umPerPx: +$('#d-um').value || null, dtMin: +$('#d-dt').value || null });
      msg.innerHTML = ` added <a href="#/viewer/${encodeURIComponent(rec.label)}">${esc(rec.label)}</a> (${rec.masks.T} frames, ${rec.masks.W}×${rec.masks.H}).`;
      list();
    } catch (err) { msg.innerHTML = ` <span class="err">${esc(err.message)}</span>`; }
  };
  $('#d-csv').onchange = async e => {
    try { const t = await addCsv(e.target.files[0]); $('#d-csvmsg').innerHTML = ` loaded ${t.rows.length} rows × ${t.columns.length} columns. <a href="#/cells">Open in Cells</a>`; }
    catch (err) { $('#d-csvmsg').innerHTML = ` <span class="err">${esc(err.message)}</span>`; }
  };

  function list() {
    $('#d-list').innerHTML = `<div class="scroll"><table class="tbl"><thead><tr><th>recording</th><th>condition</th><th>frames</th><th>size</th><th>µm/px</th><th>min/frame</th><th>source</th><th></th></tr></thead><tbody>
      ${ws.recordings.map((r, i) => `<tr><td><a href="#/viewer/${encodeURIComponent(r.label)}">${esc(r.label)}</a></td>
        <td><label class="hide" for="d-c${i}">condition of ${esc(r.label)}</label><input id="d-c${i}" data-i="${i}" class="d-cond" value="${esc(r.condition)}"></td>
        <td>${r.masks.T}</td><td>${r.masks.W}×${r.masks.H}</td>
        <td><label class="hide" for="d-u${i}">µm/px of ${esc(r.label)}</label><input id="d-u${i}" data-i="${i}" class="d-um" type="number" step="any" value="${r.umPerPx ?? ''}"></td>
        <td><label class="hide" for="d-t${i}">min/frame of ${esc(r.label)}</label><input id="d-t${i}" data-i="${i}" class="d-dt" type="number" step="any" value="${r.dtMin ?? ''}"></td>
        <td>${r.source === 'demo' ? '<span class="badge syn">synthetic demo</span>' : `uploaded${r.scaleFrom ? ` · scale: ${esc(r.scaleFrom)}` : ''}`}</td>
        <td><button class="alt d-py" data-i="${i}">Python table</button><button class="alt d-rm" data-i="${i}" aria-label="Remove ${esc(r.label)}">Remove</button></td></tr>`).join('')}
      </tbody></table></div>
      ${ws.tables.length ? `<p class="small">CSV tables: ${ws.tables.map(t => `${esc(t.name)} (${t.rows.length} rows)`).join(', ')}</p>` : ''}
      <div id="d-py"></div>`;
    const R = el => ws.recordings[+el.dataset.i];
    $('#d-list').querySelectorAll('.d-cond').forEach(el => { el.onchange = () => { R(el).condition = el.value.trim() || 'uploaded'; }; });
    $('#d-list').querySelectorAll('.d-um, .d-dt').forEach(el => { el.onchange = () => {
      const r = R(el), row = el.closest('tr');
      setScale(r, +row.querySelector('.d-um').value || null, +row.querySelector('.d-dt').value || null);
    }; });
    $('#d-list').querySelectorAll('.d-rm').forEach(el => { el.onclick = () => { removeRecording(R(el).label); list(); }; });
    $('#d-list').querySelectorAll('.d-py').forEach(el => { el.onclick = () => pythonTable(R(el)); });
  }

  async function pythonTable(rec) {
    const out = $('#d-py');
    if (isStatic()) { out.innerHTML = needsServer('The full Python per-cell table'); return; }
    out.innerHTML = '<p class="mute">Running exporters.per_cell_table in Python…</p>';
    try {
      const fd = new FormData();
      const blob = rec.masksFile || new Blob([await masksNpz(rec)]);
      fd.append('file', blob, `${rec.label}_masks.npz`);
      fd.append('um_per_px', rec.umPerPx || 0); fd.append('dt_min', rec.dtMin || 0);
      const r = await api('/analyze', { body: fd });
      out.innerHTML = `<p>Python per-cell table for <b>${esc(rec.label)}</b>: ${r.per_cell.length} cells × ${r.columns.length} columns
        (mean area ${f(r.per_cell[0]?.mean_area_um2 ?? r.per_cell[0]?.mean_area_px)} for the first cell). <button id="d-pydl">Download CSV</button></p>`;
      $('#d-pydl').onclick = () => download(`${rec.label}_per_cell_python.csv`, toCsv(r.per_cell, r.columns), 'text/csv');
    } catch (err) { out.innerHTML = `<p class="err">${esc(err.message)}</p>`; }
  }
  list();
});

// Re-pack the labels as an uncompressed .npz (one int32 'labels.npy' entry) for the Python API.
async function masksNpz(rec) {
  const { T, H, W, labels } = rec.masks;
  let header = `{'descr': '<i4', 'fortran_order': False, 'shape': (${T}, ${H}, ${W}), }`;
  const pad = 64 - ((10 + header.length + 1) % 64);
  header += ' '.repeat(pad % 64) + '\n';
  const npy = new Uint8Array(10 + header.length + labels.byteLength);
  npy.set([0x93, 78, 85, 77, 80, 89, 1, 0, header.length & 255, header.length >> 8]);
  npy.set(new TextEncoder().encode(header), 10);
  npy.set(new Uint8Array(labels.buffer, labels.byteOffset, labels.byteLength), 10 + header.length);
  return zipStore('labels.npy', npy);
}

function crc32(b) {
  let c, crc = 0xffffffff;
  for (let i = 0; i < b.length; i++) { c = (crc ^ b[i]) & 255; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; crc = (crc >>> 8) ^ c; }
  return (crc ^ 0xffffffff) >>> 0;
}
function zipStore(name, data) {
  const nm = new TextEncoder().encode(name), crc = crc32(data), n = data.length;
  const loc = new DataView(new ArrayBuffer(30)), cen = new DataView(new ArrayBuffer(46)), end = new DataView(new ArrayBuffer(22));
  [[0, 0x04034b50, 4], [4, 20, 2], [14, crc, 4], [18, n, 4], [22, n, 4], [26, nm.length, 2]].forEach(([o, v, s]) => (s === 4 ? loc.setUint32(o, v, true) : loc.setUint16(o, v, true)));
  [[0, 0x02014b50, 4], [4, 20, 2], [6, 20, 2], [16, crc, 4], [20, n, 4], [24, n, 4], [28, nm.length, 2], [42, 0, 4]].forEach(([o, v, s]) => (s === 4 ? cen.setUint32(o, v, true) : cen.setUint16(o, v, true)));
  const cdOff = 30 + nm.length + n;
  [[0, 0x06054b50, 4], [8, 1, 2], [10, 1, 2], [12, 46 + nm.length, 4], [16, cdOff, 4]].forEach(([o, v, s]) => (s === 4 ? end.setUint32(o, v, true) : end.setUint16(o, v, true)));
  return new Blob([loc, nm, data, cen, nm, end]);
}
