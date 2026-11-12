// About (#/about): what the project is, what the web version does and leaves out, how to run both apps, credits.
import { app, route } from './core.js';

route('about', () => {
  app().innerHTML = `<h1>About</h1>
  <p class="lead">cellscope_analysis is the analysis bench for <a href="https://github.com/gddickinson/cellscope">CellScope</a> detection results:
    CellScope produces and edits the segmentation/tracking masks; this project views and analyses them. It was built for a PIEZO1
    keratinocyte-migration study, and works on any CellScope recording.</p>
  <h2>What runs where</h2>
  <div class="two">
    <div class="panel"><h3>In your browser (this site)</h3><ul>
      <li>Readers for <code>masks.npz</code> (NumPy zip, stored or deflated, ZIP64) and <code>.ome.tif</code> stacks (uncompressed or zlib, 8/16-bit), plus the <code>.ome.json</code> sidecar and CSV tables.</li>
      <li>JS ports of <code>cell_metrics</code> (moment shape, Benkrid–Crookes perimeter, circularity, convexity, solidity), <code>state</code>, <code>neighbors</code>,
        <code>motion</code> (MSD + fit, direction and velocity autocorrelation, d/D, turning, run-and-tumble, jump steps), <code>exporters.per_cell_table</code>
        and the comparison statistics of <code>compare</code> (aggregate, ensemble curves, Mann-Whitney U, Cohen's d, Bonferroni, BH-FDR).</li>
      <li>Each port is checked against the Python code (node test on a committed fixture, and the <a href="#/validate">JS vs Python check</a> page).</li></ul></div>
    <div class="panel"><h3>Only in the desktop app (or the local Python API)</h3><ul>
      <li>Cell–cell contacts, Fürth persistence-time fit, state-segmented metrics, edge dynamics and kymographs, edge ↔ fluorescence,
        shape modes (VAMPIRE), membrane metrics, lineage/divisions, multivariate PERMANOVA, channel alignment and FOV,
        projects/designs and mask export.</li>
      <li>The local web app's <a href="#/data">Load data</a> page can send a recording to the Python API for the full per-cell table.</li></ul></div>
  </div>
  <h2>Demo data</h2>
  <p>The demo recordings are <b>synthetic</b>: simulated cells (wobbling outlines, some rounding up for a few frames) moving by persistent
    random walks, written in the CellScope layout by the repo's own writer (<code>maskviewer/web/demo_data.py</code> →
    <code>maskviewer/io/writer.py</code>, fixed seeds). The two "conditions" are two turning-noise settings, not treatments. No real
    microscopy data is published here.</p>
  <h2>Run it</h2>
  <h3>Desktop app (PyQt5)</h3>
  <pre>git clone https://github.com/gddickinson/cellscope_analysis.git
cd cellscope_analysis
conda env create -f environment.yml && conda activate cellscope_analysis
python main_viewer.py</pre>
  <h3>Web app (local)</h3>
  <pre>pip install -r requirements-web.txt
python run_web.py          # http://127.0.0.1:8213</pre>
  <p class="small mute">The static site is built by <code>scripts/build_static.py</code> and published to GitHub Pages.</p>
  <h2>Credits</h2>
  <p>George D. Dickinson, University of California, Irvine. MIT licence. Direction autocorrelation, MSD, directionality ratio and velocity
    autocorrelation follow DiPer (Gorelik &amp; Gautreau, Nat Protoc 2014) and are matched to the lab's <code>diper_clone</code> in the Python tests.
    Shape descriptors follow scikit-image <code>regionprops</code>.</p>`;
});
