// Viewer (#/viewer[/<recording>]): image + mask overlay, colour by cell ID / state / any metric with a colour bar,
// trails, IDs, scale bar and time; timeline with play; click a cell to inspect it (cellpanel.js).
import { $, app, esc, onLeave, route } from './core.js';
import { autoLevels, draw, labelAt } from './render.js';
import { cellPanel } from './cellpanel.js';
import { STATE_RGB, cellRgb, f, label, ramp, rampCss } from './fmt.js';
import { analyse, current, ensureWorkspace, getRec, tiffOf, ws } from './state.js';

const view = { mode: 'fill', opacity: 0.45, colourBy: 'id', trails: true, ids: true, scale: true, time: true, channel: null,
  selected: null, metric: null, fps: 4 };

const FRAME_COLS = rec => (rec.umPerPx ? ['area_um2', 'perimeter_um'] : ['area_px', 'perimeter_px'])
  .concat(['circularity', 'convexity', 'eccentricity', 'aspect_ratio', 'extent', rec.umPerPx ? 'nn_dist_um' : 'nn_dist_px', 'n_neighbors']);
const CELL_COLS = rec => [`mean_speed_${rec.umPerPx ? 'um' : 'px'}_per_${rec.dtMin ? 'min' : 'frame'}`, 'persistence_dir_autocorr',
  'straightness', 'frames_tracked', 'frac_rounded', 'track_quality'];

route('viewer', async args => {
  await ensureWorkspace();
  if (args[0] && getRec(args[0])) ws.current = args[0];
  const rec = current();
  if (!rec) { app().innerHTML = '<h1>Viewer</h1><p>No recordings loaded. <a href="#/data">Load data</a>.</p>'; return; }
  app().innerHTML = `<h1>Viewer</h1>
    <div class="row small-ctl">
      <div><label for="v-rec">Recording</label><select id="v-rec">${ws.recordings.map(r => `<option value="${esc(r.label)}"${r === rec ? ' selected' : ''}>${esc(r.label)} · ${esc(r.condition)}${r.source === 'demo' ? ' (synthetic)' : ''}</option>`).join('')}</select></div>
      <div><label for="v-ch">Image</label><select id="v-ch"></select></div>
      <div><label for="v-col">Colour cells by</label><select id="v-col"></select></div>
      <div><label for="v-mode">Masks</label><select id="v-mode"><option value="fill">fill</option><option value="outline">outline</option><option value="off">hidden</option></select></div>
    </div>
    <div class="progress" id="v-prog"><div></div></div>
    <div class="viewer">
      <div>
        <div class="stage"><canvas id="v-canvas" aria-label="Recording frame with cell masks; click a cell to inspect it"></canvas></div>
        <div class="timeline"><button id="v-play" class="alt" aria-label="Play or pause">Play</button>
          <label class="hide" for="v-t">Frame</label><input type="range" id="v-t" min="0" max="${rec.masks.T - 1}" value="0">
          <span class="mono small" id="v-tl"></span></div>
        <div id="v-cbar"></div>
        <div class="row small-ctl">
          <label class="check"><input type="checkbox" id="v-trails"> track trails</label>
          <label class="check"><input type="checkbox" id="v-ids"> cell IDs</label>
          <label class="check"><input type="checkbox" id="v-scale"> scale bar</label>
          <label class="check"><input type="checkbox" id="v-time"> time</label>
          <div><label for="v-op">Mask opacity <b id="v-opv"></b></label><input type="range" id="v-op" min="0.1" max="1" step="0.05"></div>
        </div>
        <p class="small mute" id="v-meta"></p>
      </div>
      <aside class="panel" id="v-cell"><p class="mute">Click a cell in the image to inspect it.</p></aside>
    </div>`;
  let t = 0, playing = null, tif = null, levels = {};
  const canvas = $('#v-canvas'), prog = $('#v-prog > div');
  const meta = $('#v-meta');
  meta.innerHTML = `${rec.masks.T} frames · ${rec.masks.W}×${rec.masks.H} px · ${rec.umPerPx ? `${rec.umPerPx} µm/px` : 'no pixel size (pixel units)'} · ${rec.dtMin ? `${rec.dtMin} min/frame` : 'no frame interval'}${rec.source === 'demo' ? ' · <span class="badge syn">synthetic demo</span>' : ''}${rec.note ? ` · ${esc(rec.note)}` : ''}`;
  $('#v-rec').onchange = e => { location.hash = '#/viewer/' + encodeURIComponent(e.target.value); };
  for (const [id, key] of [['v-trails', 'trails'], ['v-ids', 'ids'], ['v-scale', 'scale'], ['v-time', 'time']]) {
    $('#' + id).checked = view[key]; $('#' + id).onchange = e => { view[key] = e.target.checked; paint(); };
  }
  $('#v-mode').value = view.mode; $('#v-mode').onchange = e => { view.mode = e.target.value; paint(); };
  $('#v-op').value = view.opacity; $('#v-opv').textContent = view.opacity;
  $('#v-op').oninput = e => { view.opacity = +e.target.value; $('#v-opv').textContent = view.opacity; paint(); };

  const a = await analyse(rec, p => { prog.style.width = `${Math.round(p * 100)}%`; });
  if (!canvas.isConnected) return;                  // page left while computing
  $('#v-prog').classList.add('hide');
  const byFrame = Array.from({ length: rec.masks.T }, () => ({}));
  a.perFrame.forEach(r => { byFrame[r.frame][r.cell_id] = r; });
  const byCell = Object.fromEntries(a.perCell.map(r => [r.cell_id, r]));
  const opts = [['id', 'cell ID'], ['state', 'state (rounded / spread / edge)'],
    ...FRAME_COLS(rec).map(c => [`f:${c}`, label(c) + ' (this frame)']), ...CELL_COLS(rec).map(c => [`c:${c}`, label(c) + ' (per cell)'])];
  if (!opts.some(o => o[0] === view.colourBy)) view.colourBy = 'id';
  $('#v-col').innerHTML = opts.map(([v, l]) => `<option value="${v}"${v === view.colourBy ? ' selected' : ''}>${esc(l)}</option>`).join('');
  $('#v-col').onchange = e => { view.colourBy = e.target.value; paint(); };

  try { tif = await tiffOf(rec); } catch (e) { tif = null; meta.innerHTML += ` · <span class="err">image not readable: ${esc(e.message)}</span>`; }
  if (!canvas.isConnected) return;
  const names = rec.channelNames.length ? rec.channelNames : tif ? Array.from({ length: tif.C }, (_, i) => `ch${i}`) : [];
  const chOpts = tif ? [...(tif.C > 1 ? [['composite', 'composite (DIC grey + fluorescence magenta)']] : []), ...names.map((n, i) => [String(i), n])] : [['none', 'no image (masks only)']];
  if (!chOpts.some(o => o[0] === view.channel)) {                 // default: the DIC channel, else the first
    const dic = names.findIndex(n => /dic|bright|phase/i.test(n));
    view.channel = tif && dic >= 0 ? String(dic) : tif ? '0' : 'none';
  }
  $('#v-ch').innerHTML = chOpts.map(([v, l]) => `<option value="${v}"${v === view.channel ? ' selected' : ''}>${esc(l)}</option>`).join('');
  $('#v-ch').onchange = e => { view.channel = e.target.value; paint(); };

  const range = key => {
    const vals = key.startsWith('f:') ? a.perFrame.map(r => r[key.slice(2)]) : a.perCell.map(r => r[key.slice(2)]);
    const v = vals.filter(Number.isFinite);
    return v.length ? [Math.min(...v), Math.max(...v)] : [0, 1];
  };
  const k = Math.max(1, Math.min(6, Math.floor(720 / rec.masks.W)));

  async function layersFor(tt) {
    if (!tif) return [];
    const L = async (c, rgb) => {
      const plane = await tif.plane(tt, c);
      levels[c] ||= autoLevels(plane);                 // levels fixed from the first frame shown
      return { plane, lo: levels[c][0], hi: levels[c][1], rgb };
    };
    if (view.channel === 'composite') {
      const dic = names.findIndex(n => /dic|bright|phase/i.test(n)), di = dic >= 0 ? dic : tif.C - 1;
      const fl = [...Array(tif.C).keys()].filter(c => c !== di);
      return [await L(di, [200, 200, 200]), ...(await Promise.all(fl.slice(0, 2).map((c, i) => L(c, i ? [80, 255, 120] : [255, 60, 255]))))];
    }
    return [await L(+view.channel, [255, 255, 255])];
  }

  let token = 0;
  async function paint() {
    const my = ++token, layers = await layersFor(t);
    if (my !== token) return;
    const cb = view.colourBy, [lo, hi] = cb.includes(':') ? range(cb) : [0, 1];
    const colourOf = id => {
      if (cb === 'id') return cellRgb(id);
      if (cb === 'state') return STATE_RGB[byFrame[t][id]?.state || 'unknown'];
      const v = cb.startsWith('f:') ? byFrame[t][id]?.[cb.slice(2)] : byCell[id]?.[cb.slice(2)];
      return ramp((v - lo) / ((hi - lo) || 1));
    };
    const ids = view.ids ? Object.fromEntries(Object.values(byFrame[t]).map(r => [r.cell_id, [r.centroid_y, r.centroid_x]])) : null;
    draw(canvas, { m: rec.masks, t, k, layers, colourOf, showMasks: view.mode !== 'off', mode: view.mode, opacity: view.opacity,
      selected: view.selected, trails: view.trails ? a.cents : null, trailLen: 1000, trailColour: id => `rgb(${cellRgb(id).join(',')})`,
      ids, umPerPx: rec.umPerPx, dtMin: rec.dtMin, showScale: view.scale, showTime: view.time });
    $('#v-tl').textContent = `frame ${t + 1}/${rec.masks.T} · ${Object.keys(byFrame[t]).length} cells`;
    $('#v-cbar').innerHTML = cb.includes(':') ? `<div class="cbar" style="background:${rampCss(8)}"></div><div class="cbar-l"><span>${f(lo)}</span><span>${esc($('#v-col').selectedOptions[0].textContent)}</span><span>${f(hi)}</span></div>`
      : cb === 'state' ? `<div class="legend">${Object.entries(STATE_RGB).map(([s, c]) => `<span class="cls" style="--c:rgb(${c.join(',')})">${s}</span>`).join('')}</div>` : '';
  }
  const setT = v => { t = Math.max(0, Math.min(rec.masks.T - 1, v)); $('#v-t').value = t; paint(); };
  $('#v-t').oninput = e => setT(+e.target.value);
  const stop = () => { clearInterval(playing); playing = null; $('#v-play').textContent = 'Play'; };
  $('#v-play').onclick = () => {
    if (playing) return stop();
    $('#v-play').textContent = 'Pause';
    playing = setInterval(() => setT(t + 1 >= rec.masks.T ? 0 : t + 1), 1000 / view.fps);
  };
  onLeave(stop);
  const onKey = e => { if (e.target.tagName === 'INPUT' && e.target.type !== 'range') return; if (e.key === 'ArrowRight') setT(t + 1); if (e.key === 'ArrowLeft') setT(t - 1); };
  document.addEventListener('keydown', onKey);
  onLeave(() => { stop(); document.removeEventListener('keydown', onKey); });
  const showCell = () => cellPanel($('#v-cell'), rec, view.selected, { metric: view.metric, onMetric: m => { view.metric = m; showCell(); } });
  canvas.onclick = ev => {
    const l = labelAt(canvas, ev, rec.masks, t, k);
    if (!l) return;
    view.selected = l; paint(); showCell();
  };
  if (view.selected && byCell[view.selected]) showCell(); else view.selected = null;
  paint();
});
