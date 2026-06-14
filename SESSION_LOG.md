# cellscope_analysis — Session Log

Chronological log of substantive changes. Append an entry for any non-trivial
change. Most recent first.

---

## 2026-06-13 — Colour bar, metrics reference + tooltips, Population tab

- **Units colour bar** for the main display: a `ColorBarItem` on the canvas shows
  the value range + units of the current colour-by metric (hidden for
  categorical id/state/shape-mode); Display ▸ "Colour bar" toggle. `colorby`
  now returns `(lut, legend)`; the bar's colormap is built from matplotlib
  (pyqtgraph's `colormap.get` crashes on non-builtin names).
- **Metrics reference + tooltips**: `analysis/metric_docs.py` is one source of
  what-each-metric-indicates + how-it's-calculated. Help ▸ **Metrics Reference…**
  opens an HTML dialog; tooltips added to the Config metric menu, the cell-plot
  and colour-by combos (per item), and the main controls (timeline, image
  adjust, display, edge).
- **Edge "this frame" crop**: the per-frame edge map now auto-crops to the
  cell's max radius and centres on it (stable view as you scrub).
- **Population tab** (`analysis/population.py` + `panels/population_panel.py`):
  plot any metric across ALL cells of the recording — every-cell time series,
  **mean ± SEM/SD** error band (with optional individual curves), **histogram**,
  and a **flower plot** (origin-centred trajectories). Filters: min track
  length, cell state, exclude edge. Lazy compute + cache (one regionprops pass +
  per-frame speed). Inspired by CellScope's flower/comparison plots.

Verified headless + screenshots (flower, mean±error). `pytest` 23 passed (added
population + colour-bar/docs coverage). All files < 500 lines (colour-by logic
split into `gui/colorby.py`). Next big item: cross-recording / treatment
comparison (superplots across conditions).

---

## 2026-06-13 — VAMPIRE shape modes + edge maps + colour-by-metric + linear MSD

- **VAMPIRE shape modes** (`analysis/shape_modes.py`, sklearn): each cell-frame
  boundary → aligned, scale-normalised radial signature (reusing the edge
  sampler) → PCA + K-means into recurrent **shape modes**; per cell-frame mode,
  mode mean-shapes, mode fractions, Shannon-entropy heterogeneity. New **Shape
  Modes dock** (mode shapes + fraction bars + entropy, lazy compute) and a
  per-cell `shape_mode` series in the cell plot. (~7.5 s fit on a real 2048²
  recording → 674 contours / 5 modes; lazy + cached.) This was the last
  un-ported CellScope per-frame analysis.
- **Per-frame edge map** in the Edge dock: besides the velocity/radius
  kymographs, a view drawing the selected cell's boundary in the **current
  frame**, each boundary point coloured by per-sector edge velocity (RdBu) or
  radius — a spatial "where is it protruding/retracting now" view. Window feeds
  the current frame to the dock on scrub + selection.
- **Colour the main display by calculated metrics**: colour-by now offers area,
  perimeter, circularity, eccentricity, aspect ratio, solidity, extent,
  nearest-neighbour distance/count, mean speed, track length and shape mode
  (per-frame metrics recomputed each frame via `regionprops_frame`; per-cell ones
  lazily cached). `_overlay_lut` builds a per-cell value→colour LUT.
- **Linear MSD** plot option alongside the log-log MSD (same α/D fit overlay).

Verified headless: shape dock + shape_mode plot, all colour-by modes build LUTs,
edge per-frame map (526 boundary points coloured), linear+log MSD. `pytest` 21
passed. All files < 500 lines.

---

## 2026-06-13 — Configurable cell-plot metrics + nearest-neighbour + full CellScope per-frame set

- **Config menu** (`Config ▸ Cell plot metrics`): a checkable item per available
  per-frame metric; toggling recomputes the selected cell and updates the plot
  combo **immediately**. The panel owns the enabled set (QSettings-persisted);
  `cell_frame_table(metrics=…)` computes only the selected series, so expensive
  ones (solidity, perimeter, intensity, membrane contrast, nearest-neighbour)
  are skipped when off. Menu rebuilt per recording (intensity/membrane keys
  depend on channels).
- **Nearest-neighbour** (`analysis/neighbors.py`): per-cell NN distance + count
  within a radius (centroid-to-centroid). Added to the cell plot, the per-frame
  CSV (`nn_dist_*`, `n_neighbors`) and per-cell aggregates. The window provides
  the cached centroid history to the panel as a lazy neighbour provider.
- **Completed the CellScope per-frame metric set** so all are plottable:
  added **perimeter** (Crofton estimate matching skimage) + **circularity**
  (in `regionprops_frame`/exports too), **consecutive IoU**, **relative
  area-change**, and **membrane contrast** (inside-vs-outside ring intensity per
  channel — a boundary/membrane-quality proxy). With the existing area, ecc,
  aspect ratio, solidity, axes, orientation, extent, state, speed, displacement,
  turning, MSD and per-channel intensity, the only CellScope analysis not yet
  ported is **VAMPIRE shape-mode** classification (a population PCA+K-means model
  — its own recording-level feature; flagged for next).

Verified headless: 23 configurable metrics, immediate toggle on/off, NN +
membrane + circularity plots, composite + edge unaffected. `pytest` 21 passed
(added NN / perimeter-circularity / metric-gating tests). All files < 500 lines.

---

## 2026-06-13 — Membrane dynamics, composite, threaded export, rich cell plots

Second workbench pass (options 2–4 + richer cell info), informed by a deep read
of CellScope's analysis code (radial edge kymograph; the rounded/spread state
rule — replicated so values stay comparable to docs/FINDINGS_followup).

- **Edge / membrane dynamics** (`analysis/edge_dynamics.py`, no cv2): radial
  edge-velocity kymograph — boundary sampled into 72 angular sectors about the
  **mid-centroid** (removes whole-cell translation), median radius/sector,
  velocity = Δr·µm/dt (+protrusion/−retraction), angular Savitzky-Golay +
  temporal Gaussian smoothing; `edge_summary` (protrusion/retraction/net/
  ruffling). New **Edge Dynamics dock** (`panels/edge_panel.py`) shows the
  kymograph (angle×time, RdBu) / radius map + summary + CSV export for the
  selected cell. Verified on a real cell: clear protrusion/retraction waves.
- **Composite multi-channel view**: `ImageCanvas.set_base_layers` blends
  channels additively (DIC grey + SiR-actin Cy5 magenta); `DisplayPanel` gains a
  Composite toggle + per-channel visibility; window assigns sensible default
  LUTs per channel (Cy5→magenta, DIC→grey, …) and orders grey channels at the
  bottom.
- **Threaded CSV export**: export now runs on a worker `QThread` with a progress
  bar + Cancel (UI stays responsive). `export_all` shares ONE per-frame
  regionprops pass between the per_frame + per_cell tables; optional
  edge-dynamics columns in per_cell.
- **Per-frame state + richer cell info**: `analysis/state.py` classifies each
  cell-frame rounded/spread/edge/unknown (CellScope IC295 rule, area+ecc);
  `regionprops_frame` now carries `edge`+`state`; new colour-by **Cell state**.
  `cell_metrics.cell_frame_table` returns ALL per-frame series for one cell
  (shape, state, speed, displacement, turning angle, per-channel intensity); the
  Cell-Info panel plots any of them + an **MSD log-log view with α/D fit**
  (`motion.fit_msd`, `motion.turning_angles`).

Verified headless (`QT_QPA_PLATFORM=offscreen`): 5 docks, composite blend, state
colour-by, 16-metric cell plot combo, edge kymograph, edge-included export, all
OK. `pytest` 18 passed (added edge/state/cell_frame_table/MSD-fit tests). Every
file < 500 lines. Next: cross-recording comparison/superplot dock; VAMPIRE-style
shape modes; per-protrusion event detection.

---

## 2026-06-13 — Viewer UX overhaul → dockable workbench + CSV export

Reworked the GUI from a fixed splitter into a **dockable workbench** and added
the analysis-export foundation. Motivated by: this app is now the analysis
bench (CellScope does mask *creation*); research confirmed the science is
**PIEZO1** (YODA1 = agonist; GOF/KO = PIEZO1 variants; OT = Otenabant, a CB1
antagonist — user-confirmed), pointing the metric set at shape + motion.

**GUI (PyQt5 + pyqtgraph), all panels detachable/resizable QDockWidgets:**
- **Timeline moved below the view** (full-width bottom dock) with play/pause,
  fps, loop, frame/time readout (`panels/timeline.py`).
- **Image controls** (`panels/image_adjust.py`): histogram + draggable min/max
  levels, brightness/contrast sliders (synced to the levels), gamma, colormap
  LUT (grey/red/green/blue/magenta/cyan + matplotlib maps), invert, Auto
  (1–99 pct) + Reset — **per-channel** (cached as `luts.DisplayState`).
- **Display panel** (`panels/display_panel.py`): recording/channel, mask
  show/outline/opacity, **colour-by** (Cell ID / per-frame area / track
  length), overlay toggles.
- **Overlays** (`overlays.py`): scale bar, frame/time text, cell-ID labels,
  track trails, selected-cell highlight (corner items re-anchor on pan/zoom).
- **Cell-info panel** (`panels/cell_info.py`): click a cell → metrics + an
  area/speed-over-time plot with a current-frame marker.
- **Menus** (`menus.py`): File/View/Image/Analysis/Window/Help (Window lists
  dock toggles + Reset Layout); QSettings layout persistence.
- `ImageCanvas` extended for user LUT+levels, `cellClicked`, colour-by LUTs,
  zoom; replaced the old `ControlPanel` (controls.py removed).

**Analysis + CSV export (pure, GUI-free, skimage-free):**
- `analysis/cell_metrics.py` — moment-based morphometry matching skimage
  (eccentricity/axes via central moments + 1/12; convex-hull solidity).
- `analysis/motion.py` — speed, net/path/straightness, **direction
  autocorrelation** (`persistence`, the speed-unbiased measure — straightness
  is reported but flagged speed-biased per Gorelik & Gautreau 2014), MSD.
- `analysis/exporters.py` — `per_frame_table` (region props = "masks as CSV"),
  `per_cell_table` (track+shape+motion), `track_table` (trajectories),
  `export_all`; tidy, unit-tagged headers for Origin. GUI dialog =
  `gui/export_dialog.py` (Ctrl+E). On a real 2048²×97 recording: load 4.4s,
  per-cell+tracks export ~12s (synchronous, wait-cursor — thread it later if
  dense fields feel slow).

Verified headless (`QT_QPA_PLATFORM=offscreen`): 4 docks, timeline at bottom,
scrub/channel/auto/gamma/colormap/colour-by/overlays/select/reset all OK.
`pytest` 12 passed (added `tests/test_analysis.py`). Next: comparison/superplot
dock across recordings, edge-velocity/retraction (kymographs), composite
multi-channel, MSD/turning-angle plots — see CLAUDE.md roadmap.

---

## 2026-06-13 — Edge-truncated cells: verified + dynamics now skip them

Checked whether edge cells (masks cut by the border → unreliable shape +
inward-biased centroid) contaminate the analysis. Shape/state is already
edge-clean (CellScope voids edge frames to `unknown`; 85% of cells never
touch the edge, frac_in_view median=1.0). **The KO shape finding is robust**:
identical p-values with/without an extra frac_in_view≥0.8 cell filter
(eccentricity p=0.0047; shape_roundness p=0.0006). Recorded in
`docs/FINDINGS_followup.md`.

New `maskviewer/analysis/edges.py` recomputes a per-frame edge flag per cell
from the masks (label touching the border), cached to
`analysis_out/_edge_flags.pkl`; `dynamics.run()` attaches it so centroid-
based metrics (contact step-speed, onsets) **skip edge frames**. State-based
metrics already excluded edge. Remaining track caveat is FOV censoring (cells
leaving frame), not edge masking. All analysis_out plots regenerated.

---

## 2026-06-13 — Evaluated persistence+straightness; kept separate; full scan

Checked whether persistence + straightness should be combined like the shape
cluster: they are only **weakly correlated (r=0.25)** (local angular vs global
net/path directedness), so combining would discard ~38% real variance —
**kept separate** (per decision). A full pairwise correlation scan
(`correlation_fig` → `mv_feature_correlation.png`) confirms the **shape
cluster was the only strongly-collinear group**; `frac_rounded` is moderately
correlated with shape (r≈0.6) but is a distinct construct (state-time vs
morphology) so also kept separate; nothing else clusters (|r|<0.5).
Generalised the combiner to `_pc1_score` (shape still the only score);
removed the directionality machinery. Documented in
`docs/FINDINGS_followup.md`.

---

## 2026-06-13 — Collinearity check + combined roundness score

Flagged that the shape fingerprint features are collinear (circularity↔
solidity r=0.92, circularity↔eccentricity r=−0.68) — can't be read as
independent evidence. Verified the KO result is NOT an artefact: holds with
one shape feature (eccentricity alone p=0.003, AUC=0.81), a curated 6-feature
set (AUC=0.86), and PCA-decorrelated PCs (p=0.004). Collapsed the four shape
metrics into one `shape_roundness` score (PC1, 62% of their variance) — which
is the *strongest* single discriminator: **KO vs WT p=0.0006** (Bonferroni-
safe). So the phenotype is one interpretable axis (KO/GOF spread cells
rounder + more compact), not 12. Added `add_shape_score`/`FEATURES_COMBINED`
to `multivariate.py`; new figure `mv_shape_score.png`; story panel A/F + the
fingerprint now use the combined score. Documented in
`docs/FINDINGS_followup.md`.

---

## 2026-06-13 — Follow-up treatment-effect investigation

Added `maskviewer/analysis/{feature_tables,multivariate,dynamics,
interactions}.py` + `scripts/{run_followup,plot_followup}.py` to test the
strategies recommended last session, on the CellScope IC295 results (read via
`data/`; recording = unit). Added scipy/scikit-learn/pandas to the env.

**Bore fruit:** multivariate (PERMANOVA + leave-one-recording-out logistic)
recovers a **KO-vs-WT phenotype invisible to univariate tests** — PERMANOVA
p=0.004 (Bonferroni-safe, replicates an independent run), LORO-AUC=0.80
(perm p=0.022); fingerprint = KO spread cells rounder/more compact
(↓eccentricity d=−1.8, ↑circularity, ↑solidity) + less persistent. GOF n.s.;
**drug arm null by every method**.

**Informative nulls:** dynamics (transition/dwell/contact) found no treatment
effect AND contact analysis is event-starved at this density (only 2–5
recordings have enough contact onsets); clean-cell subsetting *lost* the KO
signal (over-filtering); treatment×density n.s. The **WT-vs-DMSO vehicle/batch
effect is large** (multivariate AUC=0.83; rounded-dwell p=0.010) — as strong
as the genetic effect.

Findings in `docs/FINDINGS_followup.md`; figures in `analysis_out/`
(gitignored). Recommendations forward: adopt multivariate as primary;
drug arm needs power (dose-response, ~25/cond, batch control); image
denser/larger fields for contact; don't over-filter; design out batch
(co-culture).

---

## 2026-06-13 — docs/DATA.md (data + mask provenance)

Wrote `docs/DATA.md` explaining the IC295 dataset (6 conditions / 2 arms +
vehicle, 0.6523 µm/px, 10-min, 97 frames), the `data/` folder layout, every
per-recording file (incl. the `masks_{original,reviewed,precleanup}.npz`
audit trail, `per_cell.csv`, `recording_summary.json`, `divisions.json`,
`RUN_METADATA.json`), and how masks were produced — verified from a real
`RUN_METADATA.json` (`pipeline = unified_detection.detect_recording (auto)`):
cpsam auto-route (cpsam_dic vs raw) → DeepSea union → Hungarian tracking +
division → 4-phase gap-fill → Cy5 persistence_guard → manual review →
clean. Flagged the `RUN_METADATA` `um_per_px:1.0` placeholder (trust the
`.ome.json`). Linked from README / CLAUDE.md / INTERFACE.md.

---

## 2026-06-13 — Local data/ symlink folder (gitignored)

Added `scripts/link_data.py` + a gitignored **`data/`** folder of symlinks
into the CellScope tree: `by_condition` (whole tree), flat `recordings/`
(48 `<cond>__<label>` links), `results/{compare,compare_pooled}`, and
`gt/{ic295_gt_full,legacy_gt}`. `config.json` now points the viewer at
`data/by_condition` (project references its own folder). Verified discovery
+ load of a real 2048² recording through the symlink. `data/` is gitignored
(public repo — symlinks point at private local data); recreate with
`python scripts/link_data.py`. Also tightened `.gitignore` so the sample
re-include (`!sample_data/**/*.tif|*.npz`) no longer un-ignores `.DS_Store`.

---

## 2026-06-13 — Dedicated CPU-only conda env

Confirmed the viewer needs **no GPU** (no torch/cellpose/CUDA/MPS — it only
views pre-computed masks). Added `environment.yml` and created a dedicated
**`cellscope_analysis`** env (conda-forge: python 3.11, numpy, tifffile,
pyqtgraph 0.14, pyqt 5.15, matplotlib, pytest). Verified in the new env:
`torch present? False`, `pytest` 3/3 pass, headless GUI smoke OK. Docs
(README, CLAUDE.md, requirements.txt) updated to prefer this env;
`cellpose4` still works as a fallback.

---

## 2026-06-13 — Project bootstrap (viewer + analysis scaffold)

Split a dedicated analysis project out of `cellscope` to keep detection-result
review/analysis simple and expandable. Initial scope: **view recordings with
their mask overlays in a GUI**, with a GUI-free analysis package to grow.

- **Stack**: PyQt5 + pyqtgraph (already in CellScope's `cellpose4` env; no new
  deps). napari was considered but isn't installed and is heavier.
- **IO** (`maskviewer/io/`): `load_recording` (`.ome.tif` `(T,C,H,W)` +
  `.ome.json` sidecar), `load_masks` (`masks.npz` → `labels (T,H,W)`),
  `discover` (walks `data_roots` for recording folders).
- **GUI** (`maskviewer/gui/`): `ImageCanvas` (base channel + LUT-coloured
  label overlay, outline mode, hover→cell ID), `ControlPanel`, `ViewerWindow`
  (channel/frame/opacity, ←/→ stepping, status bar). Verified headless with
  `QT_QPA_PLATFORM=offscreen`: loads, scrubs, channel switch, outline, hover.
- **analysis** (`maskviewer/analysis/label_stats.py`): per-frame counts,
  areas, track lengths, centroids, `summary` — the expansion seed.
- **Data policy**: PUBLIC repo → **no real data committed**. Real recordings
  referenced via gitignored `config.json` (`data_roots`); committed
  `sample_data/Pos_demo/` is **synthetic** (`scripts/make_sample_data.py`).
  Verified discovery finds the synthetic sample AND the 48 real IC295
  recordings via a local `config.json`.
- Docs: README, CLAUDE.md (handoff + data formats + expansion seeds),
  INTERFACE.md (navigation map), MIT LICENSE.

Headless smoke (the agent's GUI test without a screen):
```bash
QT_QPA_PLATFORM=offscreen conda run -n cellpose4 python - <<'PY'
from PyQt5 import QtWidgets; import sys
from maskviewer.config import load_config
from maskviewer.io import discover
from maskviewer.gui import ViewerWindow
app=QtWidgets.QApplication(sys.argv)
w=ViewerWindow(discover(load_config()['data_roots']))
w.controls.frame.setValue(3); print(w.status.currentMessage())
PY
```

Next ideas (see CLAUDE.md): CSV export + plots from `analysis/`, a per-cell
info panel, an HTTP remote-control hook for headless agent testing.
