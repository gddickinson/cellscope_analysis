// Static-site data layer: answers api() calls from the JSON exported by scripts/build_static.py. All analysis of
// masks runs in the browser (JS ports); the full Python per-cell table for an upload needs the local app.
const files = new Map();
async function file(rel) {
  if (!files.has(rel)) files.set(rel, fetch('api/' + rel + '.json').then(r => { if (!r.ok) throw new Error(`${r.status} ${rel}`); return r.json(); }));
  return files.get(rel);
}

export const NEEDS_SERVER = 'needs the full app running locally (Python server): see the README, "Web interface"';

export async function staticApi(path, body) {
  const clean = path.split('?')[0].replace(/^\/+/, '');
  if (clean === 'analyze') throw new Error('The full Python per-cell table ' + NEEDS_SERVER + '. Everything else on this site runs in your browser.');
  return file(clean);
}
