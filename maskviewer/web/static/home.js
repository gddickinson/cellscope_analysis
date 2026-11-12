// Home: hero, real counts from the demo set, and cards to the pages.
import { api, app, esc, isStatic, route } from './core.js';

route('home', async () => {
  const hash = location.hash, info = await api('/info');
  if (location.hash !== hash) return;
  app().innerHTML = `
  <section class="hero">
    <p class="kicker">CellScope results · tracked cells · shape and motility</p>
    <h1 class="glow">CellScope Analysis</h1>
    <p class="lead">A viewer and analysis workbench for <a href="https://github.com/gddickinson/cellscope">CellScope</a> detection results.
      Open a segmentation/tracking label stack (<code>masks.npz</code>) with its recording (<code>.ome.tif</code>), inspect each tracked
      cell, measure shape and motility per cell and per frame, filter and plot the population, and compare recordings by condition
      with the recording as the experimental unit.</p>
    <a class="btn" href="#/viewer">Open the viewer</a><a class="btn alt" href="#/data">Load your own masks</a><a class="btn alt" href="#/compare">Compare conditions</a>
  </section>
  <div class="tiles">
    <div class="tile"><b>${info.n_recordings}</b><span>demo recordings (synthetic)</span></div>
    <div class="tile"><b>${info.n_cells}</b><span>tracked cells in them</span></div>
    <div class="tile"><b>${info.n_frames}</b><span>frames in total</span></div>
    <div class="tile"><b>${info.conditions.length}</b><span>simulated conditions</span></div>
    <div class="tile"><b>${info.n_metrics}</b><span>per-cell columns from the Python export</span></div>
  </div>
  <div class="callout"><b>Demo data are synthetic.</b> ${esc(info.demo_note)}
    ${isStatic() ? ' Your own files are read and analysed in this browser tab; nothing is uploaded.' : ''}</div>
  <h2>Pages</h2>
  <div class="grid">
    <a class="card" href="#/viewer"><b>Viewer</b><span>Recording with mask overlay (fill or outline), colour by cell ID, state or any metric, track trails, timeline. Click a cell for its per-frame plots, MSD and direction autocorrelation.</span></a>
    <a class="card" href="#/cells"><b>Cells</b><span>Per-cell table (track, shape, motion, run-and-tumble, track quality), filters, histogram and scatter, and CSV export in the desktop app's column layout.</span></a>
    <a class="card" href="#/population"><b>Population</b><span>All cells of a recording: flower plot, mean ± SEM time course of any per-frame metric, and the per-recording DiPer curves.</span></a>
    <a class="card" href="#/compare"><b>Compare</b><span>Recordings grouped by condition: strip plots of per-recording means over cells, ensemble MSD / direction autocorrelation / d/D / velocity autocorrelation, Mann-Whitney U and Cohen's d.</span></a>
    <a class="card" href="#/data"><b>Load data</b><span>Your own <code>masks.npz</code> (+ optional <code>.ome.tif</code> and <code>.ome.json</code>), or a CSV exported by the desktop app or CellScope.</span></a>
    <a class="card" href="#/validate"><b>JS vs Python check</b><span>The browser analysis recomputed on the demo and compared with the repo's Python per-cell table, column by column.</span></a>
  </div>`;
});
