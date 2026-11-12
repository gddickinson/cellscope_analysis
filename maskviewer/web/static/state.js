// The workspace: the recordings open in the browser (the synthetic demo, or the user's own masks.npz + optional
// .ome.tif / .ome.json), their analysis (computed in a Web Worker by the JS ports), and CSV tables the user loaded.
// Nothing leaves the browser: files are read locally.
import { api } from './core.js';
import { readMasks } from './npz.js';
import { openTiff } from './tiff.js';
import { analyseStack, recordingCurves, parseCsv } from './tables_engine.js';
import { setDocs } from './fmt.js';

export const ws = { recordings: [], tables: [], current: null, demo: false, listeners: new Set() };
const changed = () => ws.listeners.forEach(fn => { try { fn(); } catch (e) { console.warn(e); } });

let docsP = null;
export const loadDocs = () => (docsP ||= api('/metrics').then(setDocs).catch(() => setDocs({})));

async function fetchBuf(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} fetching ${url}`);
  return r.arrayBuffer();
}

let demoP = null;
// Load the synthetic demo set (masks now; the image stacks on first view).
export function loadDemo() {
  return (demoP ||= (async () => {
    const d = await api('/demo');
    for (const r of d.recordings) {
      const masks = await readMasks(await fetchBuf(r.masks));
      add({ label: r.label, condition: r.condition, note: r.condition_note, source: 'demo', masks,
        tifUrl: r.tif, umPerPx: r.um_per_px, dtMin: r.time_interval_min, channelNames: r.channel_names });
    }
    ws.demo = true;
  })());
}

export async function ensureWorkspace() {
  await loadDocs();
  if (!ws.recordings.length) await loadDemo();
  if (!ws.current && ws.recordings.length) ws.current = ws.recordings[0].label;
}

function uniqueLabel(base) {
  let l = base, k = 2;
  while (ws.recordings.some(r => r.label === l)) l = `${base}_${k++}`;
  return l;
}

function add(rec) {
  rec.label = uniqueLabel(rec.label);
  rec.analysis = null; rec.tiff = null;
  ws.recordings.push(rec);
  changed();
  return rec;
}

// Add the user's files: {masks: File, tif?: File, sidecar?: File, label, condition, umPerPx, dtMin}
export async function addUpload({ masks, tif, sidecar, label, condition, umPerPx, dtMin }) {
  const m = await readMasks(await masks.arrayBuffer());
  let meta = {};
  if (sidecar) meta = JSON.parse(await sidecar.text());
  let tiff = null;
  if (tif) {
    tiff = await openTiff(tif);
    if (tiff.T !== m.T || tiff.H !== m.H || tiff.W !== m.W) throw new Error(`image ${tiff.T}x${tiff.H}x${tiff.W} (T x H x W) does not match the masks ${m.T}x${m.H}x${m.W}`);
    meta = { ...tiff.meta, ...meta };
  }
  const rec = add({ label: label || masks.name.replace(/\.npz$/, ''), condition: condition || 'uploaded', source: 'upload', masks: m,
    umPerPx: umPerPx || meta.um_per_px || null, dtMin: dtMin || meta.time_interval_min || null,
    channelNames: meta.channel_names || (tiff ? Array.from({ length: tiff.C }, (_, i) => `ch${i}`) : []),
    scaleFrom: umPerPx ? 'entered' : meta.um_per_px ? (sidecar ? 'sidecar' : 'OME metadata') : 'none (pixels)' });
  rec.tiff = tiff; rec.masksFile = masks;
  ws.current = rec.label;
  return rec;
}

export function removeRecording(label) {
  ws.recordings = ws.recordings.filter(r => r.label !== label);
  if (ws.current === label) ws.current = ws.recordings[0]?.label || null;
  changed();
}

export async function addCsv(file) {
  const t = parseCsv(await file.text());
  ws.tables.push({ name: file.name, ...t });
  changed();
  return t;
}

export const getRec = label => ws.recordings.find(r => r.label === label) || null;
export const current = () => getRec(ws.current) || ws.recordings[0] || null;
export const conditions = () => [...new Set(ws.recordings.map(r => r.condition))].sort();

export async function tiffOf(rec) {
  if (!rec.tiff && rec.tifUrl) rec.tiff = await openTiff(await fetchBuf(rec.tifUrl));
  return rec.tiff;
}

// Analyse a recording in a Web Worker (inline fallback); cached on the record.
let worker = null, seq = 0;
const pending = new Map();
function getWorker() {
  if (worker === null) {
    try {
      worker = new Worker(new URL('./analysis_worker.js', import.meta.url), { type: 'module' });
      worker.onmessage = e => {
        const p = pending.get(e.data.id);
        if (!p) return;
        if ('progress' in e.data) { p.onProgress?.(e.data.progress); return; }
        pending.delete(e.data.id);
        e.data.error ? p.reject(new Error(e.data.error)) : p.resolve(e.data.result);
      };
      worker.onerror = () => { worker = false; };
    } catch { worker = false; }
  }
  return worker;
}

export function analyse(rec, onProgress) {
  if (rec.analysis) return Promise.resolve(rec.analysis);
  if (rec.analysing) return rec.analysing;
  const opt = { umPerPx: rec.umPerPx || null, dtMin: rec.dtMin || null };
  const w = getWorker();
  rec.analysing = (w ? new Promise((resolve, reject) => {
    const id = ++seq;
    pending.set(id, { resolve, reject, onProgress });
    w.postMessage({ id, labels: rec.masks.labels, T: rec.masks.T, H: rec.masks.H, W: rec.masks.W, ...opt });
  }) : Promise.resolve().then(() => {
    const res = analyseStack(rec.masks, opt);
    res.curves = recordingCurves(res.cents, opt);
    return res;
  })).then(res => { rec.analysis = res; rec.analysing = null; return res; },
    err => { rec.analysing = null; throw err; });
  return rec.analysing;
}

export async function analyseAll(onProgress) {
  let done = 0;
  for (const r of ws.recordings) { await analyse(r); onProgress?.(++done / ws.recordings.length); }
}

// Per-cell rows of every recording, tagged with recording + condition.
export const allPerCell = () => ws.recordings.filter(r => r.analysis)
  .flatMap(r => r.analysis.perCell.map(c => ({ ...c, recording: r.label, condition: r.condition })));

// Re-analyse after a scale change.
export function setScale(rec, umPerPx, dtMin) {
  rec.umPerPx = umPerPx || null; rec.dtMin = dtMin || null; rec.analysis = null; rec.scaleFrom = 'entered';
  changed();
}
