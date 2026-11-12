// Node test: the JS readers and analysis ports reproduce the repo's Python code on the committed fixture
// (tests/fixtures/web_engine, written by scripts/make_web_fixture.py). Run: node engine.test.mjs
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { readMasks } from './npz.js';
import { openTiff } from './tiff.js';
import { perFrameRecords, centroidHistory } from './morph_engine.js';
import * as mo from './motion_engine.js';
import { perCellTable, recordingCurves, parseCsv, toCsv } from './tables_engine.js';
import { mannWhitney, cohensD, benjaminiHochberg, ensembleByCondition } from './stats_engine.js';

const here = p => fileURLToPath(new URL(p, import.meta.url));
const buf = p => { const b = readFileSync(here(p)); return b.buffer.slice(b.byteOffset, b.byteOffset + b.length); };
const FIX = '../../../tests/fixtures/web_engine/';
const exp = JSON.parse(readFileSync(here(FIX + 'expected.json'), 'utf8'));
let checks = 0;

function close(a, b, what, rtol = 1e-9, atol = 1e-9) {
  checks++;
  if (b === null || b === undefined) { assert.ok(a === null || a === undefined || Number.isNaN(a), `${what}: expected NaN, got ${a}`); return; }
  if (typeof b === 'boolean' || typeof b === 'string') { assert.equal(a, b, what); return; }
  assert.ok(Number.isFinite(a), `${what}: got ${a}, expected ${b}`);
  assert.ok(Math.abs(a - b) <= atol + rtol * Math.abs(b), `${what}: ${a} vs ${b}`);
}
const closeArr = (a, b, what) => { assert.equal(a.length, b.length, `${what} length`); b.forEach((v, i) => close(a[i], v, `${what}[${i}]`)); };
function closeRows(js, py, what, skip = []) {
  assert.equal(js.length, py.length, `${what}: row count`);
  py.forEach((r, i) => { for (const k of Object.keys(r)) if (!skip.includes(k)) { assert.ok(k in js[i] || r[k] === null, `${what}: JS lacks column ${k}`); close(js[i][k], r[k], `${what} row ${i} ${k}`); } });
}

// masks.npz reader
const m = await readMasks(buf(FIX + 'masks.npz'));
assert.deepEqual([m.T, m.H, m.W], [12, 96, 96]);
const { um_per_px: um, dt_min: dt } = exp;

// per-frame region properties (+ solidity), all columns
const pf = perFrameRecords(m, { umPerPx: um, dtMin: dt, withSolidity: true });
closeRows(pf, exp.per_frame, 'per_frame');

// per-cell table: every column the JS port computes (contacts are Python-only and not in the fixture rows' JS set)
const PY_ONLY = /contact|furth|persistence_time/;
const pfPlain = perFrameRecords(m, { umPerPx: um, dtMin: dt });
const cents = centroidHistory(pfPlain, m.T);
const pc = perCellTable(m, pfPlain, cents, { umPerPx: um, dtMin: dt });
closeRows(pc, exp.per_cell, 'per_cell', Object.keys(exp.per_cell[0]).filter(k => PY_ONLY.test(k)));
const pfPx = perFrameRecords(m, {});
const pcPx = perCellTable(m, pfPx, centroidHistory(pfPx, m.T), {});
closeRows(pcPx, exp.per_cell_px, 'per_cell_px', Object.keys(exp.per_cell_px[0]).filter(k => PY_ONLY.test(k)));

// per-cell motion
for (const [cid, c] of Object.entries(exp.cells)) {
  const cen = cents[cid], sc = mo.scaleTrack(cen, um);
  const r = mo.msd(sc, dt);
  closeArr(r.tau, c.msd_tau, `msd tau ${cid}`); closeArr(r.msd, c.msd, `msd ${cid}`);
  const f = mo.fitMsd(r.tau, r.msd);
  close(f.D, c.fit.D, `fit D ${cid}`); close(f.alpha, c.fit.alpha, `fit alpha ${cid}`); close(f.r2, c.fit.r2, `fit r2 ${cid}`);
  closeArr(mo.directionAutocorrelation(cen), c.autocorr, `autocorr ${cid}`);
  closeArr(mo.velocityAutocorrelation(cen), c.velcorr, `velcorr ${cid}`);
  closeArr(mo.directionalityRatio(sc, dt).ratio, c.dir_ratio, `dir_ratio ${cid}`);
  closeArr(mo.turningAngles(sc), c.turning, `turning ${cid}`);
  closeArr(mo.instantaneousSpeed(sc, dt), c.speed, `speed ${cid}`);
}

// per-recording ensemble curves (compare.build_comparison)
const curves = recordingCurves(cents, { umPerPx: um, dtMin: dt });
for (const [k, col] of [['msd', 'msd'], ['autocorr', 'autocorr'], ['dir_ratio', 'dir_ratio'], ['velcorr', 'velcorr']]) {
  closeArr(curves[k].map(r => r.tau), exp.curves[k].map(r => r.tau), `${k} tau`);
  closeArr(curves[k].map(r => r.value), exp.curves[k].map(r => r[col]), `${k} value`);
}

// statistics
for (const [i, c] of exp.mannwhitney.entries()) {
  const r = mannWhitney(c.x, c.y);
  close(r.U, c.U, `MWU U case ${i}`); close(r.p, c.p, `MWU p case ${i} (${r.method})`, 1e-7, 1e-12);
  close(cohensD(c.x, c.y), c.d, `cohen d case ${i}`);
}
closeArr(benjaminiHochberg(exp.bh.p.map(v => v ?? NaN)), exp.bh.q, 'BH q');
const ens = ensembleByCondition(exp.ensemble.long.map(r => ({ condition: r.condition, tau: r.tau, value: r.msd })));
for (const [cond, [tau, centre, lo, hi]] of Object.entries(exp.ensemble.out)) {
  closeArr(ens[cond].tau, tau, `ens tau ${cond}`); closeArr(ens[cond].centre, centre, `ens centre ${cond}`);
  closeArr(ens[cond].lo, lo, `ens lo ${cond}`); closeArr(ens[cond].hi, hi, `ens hi ${cond}`);
}

// CSV round trip
const csv = toCsv(pc);
const back = parseCsv(csv);
assert.equal(back.rows.length, pc.length);
close(back.rows[0].mean_area_um2, pc[0].mean_area_um2, 'csv round trip', 1e-12);

// TIFF reader on the committed synthetic sample recording (8 frames x 2 channels)
const tif = await openTiff(buf('../../../sample_data/Pos_demo/Pos_demo.ome.tif'));
assert.deepEqual([tif.T, tif.C, tif.H, tif.W, tif.bits], [8, 2, 192, 192, 16]);
const plane = await tif.plane(3, 1);
assert.equal(plane.reduce((a, b) => a + b, 0), 53988413);   // tifffile.imread(...)[3, 1].sum()

console.log(`engine.test.mjs: ${checks} numeric checks ok`);
