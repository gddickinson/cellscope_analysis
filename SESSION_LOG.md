# cellscope_analysis — Session Log

Chronological log of substantive changes. Append an entry for any non-trivial
change. Most recent first.

---

## 2026-06-14 — Comparison: crowding/edge filters, trendlines, MSD-plot fix

Three Comparison-window improvements.

- **More filters** (`gui/compare_filters.py`, new `FilterMixin`): the filters moved
  from the cramped toolbar row into a non-modal **Filters…** dialog and gained
  spatial/crowding ones — **distance from the image edge** (new per-cell
  `min/mean_border_dist_um` in `exporters.per_cell_table`), **nearest-neighbour
  distance** (min/max, on `mean_nn_dist`), and **neighbour count** (min/max, on
  `mean_n_neighbors`) — alongside frames / track-quality / min-cells / state.
  Session-only (+ Reset). Filter `_filtered()` moved into the mixin.
- **Trendlines** in the plot-style options (`PlotStyle.trendline`): on the scatter
  a least-squares line; on the categorical plots (strip / box / bars / superplot) a
  dashed line connecting the per-group centres across conditions (a trend across an
  ordered series). Replaces the scatter-only `scatter_fit`.
- **Ensemble-MSD plot fix**: the CI band's bound curves are now added to the plot
  (so they inherit its log mode) and clamped > 0 — previously a bare
  `FillBetweenItem` over loose curves rendered the band/lines misaligned on the
  log-log axes (and `mean−SEM ≤ 0` broke the log).

Tests: `pytest` **44 passed** (new edge-distance test). The compare smoke drives
the Filters… dialog + new filters, trendlines on every dist kind, and writes
`comparison_{msd,filters}.png`. Both GUI smokes green; all files < 500 lines
(`_filtered` + filter widgets live in `compare_filters.py`).

---

## 2026-06-14 — Per-graph plot-style options (Comparison window)

Every Comparison-window graph is now customisable.

- **`gui/plot_style.py`** (new): `PlotStyle` (dataclass of render options —
  font size, marker/line size, fill opacity, grid, log X/Y, scatter fit line,
  histogram bins/density/bars, show-points — QSettings-persisted), a non-modal
  **`PlotStyleDialog`** live editor, and **`PlotStyleMixin`** that opens it from a
  toolbar **Style…** button *or* **shift-right-click on any plot** (your suggested
  UX) and replots live.
- `compare_plots` functions all take the `PlotStyle` and apply it via a shared
  `_axes` helper (fonts/grid/log/ticks); added a **`bars`** view (group mean ± SEM)
  → the Distributions tab gains a **Bars (mean ± SEM)** option (bars-vs-points).
- `compare_window`: holds the style (`PlotStyle.from_settings`), adds the Style…
  button, installs the shift-right-click event filter on all four plots, and threads
  the style into every draw call. `_show_help` moved to `compare_tables.show_metrics_help`
  to keep the file < 500 lines.

Tests: `pytest` **43 passed**; the compare smoke now drives the bars view, the
style dialog (font/bins/bars/grid/fit), and the shift-right-click filter, and
writes `docs/screenshots/comparison_style.png`. Both GUI smokes green; all files
< 500 lines.

---

## 2026-06-14 — Match the original analysis (state-segmented metrics) + full metric docs

Investigated why the Comparison window's numbers differed from the original
`cellscope` project. Diagnosis (with matching controls — `n_cells` and
`frac_spread` were identical, proving same masks/tracking/state rule): the
original computes every motility/shape metric **per state** (rounded vs spread),
edge-excluded, speed-capped and segment-gated, while our GUI was computing one
**whole-track** value per cell. (The follow-up/FINDINGS analysis already matched,
because `feature_tables` reads the original CSVs directly.)

- **`analysis/state_metrics.py`** (new) — `per_cell_state_metrics`: per-cell
  `mean_speed_{s}` / `persistence_{s}` / `straightness_{s}` / `mean_area_um2_{s}` /
  shape means over rounded vs spread frames, mirroring the original
  `core/motility_state.py` + `core/state_analysis.py` (edge frames excluded;
  per-step speed at the step's start frame, edge steps dropped, capped at
  15 µm/min; persistence/straightness over contiguous ≥5-frame segments).
  **Validated to reproduce `compare/per_recording.csv` to 3 decimals** (Pos60/61/62
  spread+rounded speed, persistence, straightness, area, eccentricity).
- `compare.build_comparison` now merges these alongside the whole-track columns
  (single shared per-frame pass), so the Comparison window offers both.
- **Documentation pass** ("document all methods + help + tooltips"):
  `metric_docs` gained `column_units`/`column_label` state-suffix awareness,
  `comparison_doc` / `comparison_tooltip` (resolve any aggregated/per-state column
  to its what+how), new entries (frac_rounded/spread, n_cells, frames_tracked),
  and a **Cross-recording comparison** section in `as_html`. The Comparison window
  got a **Help** button (Metrics & methods reference), per-column metric tooltips,
  and tab/control tooltips; the main viewer's Help ▸ Metrics Reference picks up the
  new section automatically.

Tests: `pytest` **43 passed** (new `tests/test_state_metrics.py` + extended
`test_compare_extras.py`). Both GUI smokes green. All files < 500 lines.

---

## 2026-06-14 — Comparison: more filters, axis units, Histogram + Data tabs

Extended the Comparison window per the request — more filtering, units on graphs,
and histogram + tabular tabs alongside the per-contrast stats.

- **Filters** (new second toolbar row): min frames tracked, **min track-quality**,
  **min cells/recording** (drop low-N recordings — recording = unit), and a
  **cell-state** filter (all / mostly spread / mostly rounded via frac_spread/
  frac_rounded ≥ 0.5). Cell-level filters apply before aggregation; min-cells drops
  recordings (and their cells) consistently across plots, stats, histogram, data
  and the MSD curves.
- **Units on graphs**: `metric_docs.column_units` / `column_label` / `axis_label`
  turn an aggregated column into "mean area (µm²)" etc.; used on every distribution
  / scatter axis, the histogram axis, and the Data-tab headers.
- **Right panel is now tabbed** (`StatsTablesMixin` split into `gui/compare_tables.py`):
  **Stats** (the existing per-contrast table + omnibus/vehicle) · **Histogram**
  (`compare_plots.histogram` — per-cell distribution by group, shared bins, legend)
  · **Data** (per-recording table + per-group summary `compare.per_condition_summary`,
  unit-tagged; exportable, +`comparison_per_group_summary.csv`).

Tests: `pytest` **37 passed** (new `tests/test_compare_extras.py` — units/labels +
per-group summary). `scripts/smoke_compare_window.py` now drives the filters + the
three right tabs + units and writes `docs/screenshots/comparison{,_histogram}.png`.
All files < 500 lines (stats/data table code moved to `compare_tables.py`).

---

## 2026-06-14 — Status-bar progress bars + ETA (off-thread compute)

Long compute (the per-frame regionprops / contour passes) now reports into a
**bottom-bar progress widget with elapsed + ETA** in both the main viewer and the
Comparison window, so the user can see how long a pass will take — and the GUI
stays responsive because the work runs on a worker thread.

- **`gui/status_progress.py`** — `StatusProgress(QWidget)`: label + bar +
  elapsed/ETA (`start` / `update(done,total)` / `finish` / `fail`); ETA =
  elapsed × remaining/done. Embedded via `statusBar().addPermanentWidget`.
- **`gui/task_runner.py`** — `TaskRunner(QObject)`: runs `fn(progress_cb)` on a
  `QThread`, marshalling `progress` + `on_done`/`on_error` back to the GUI thread
  (one task at a time). `AsyncComputeMixin` lets a panel run its compute through an
  injected `run_async`, with a synchronous fallback for tests/headless.
- **Main viewer**: Population / Shape-modes / Cell-table `_compute` split into
  `_work(progress_cb)` (off-thread) + `_apply(result)` (GUI); the window injects
  `run_task` (status-bar bar/ETA, busy-guard) into the panels. The
  `_population_table` / `_shape_modes_model` providers + `run_task` moved to
  `WindowActionsMixin` (keeps `viewer_window.py` < 500). Synchronous callers
  (colour-by) still get a wait cursor.
- **Comparison window**: moved its progress from the toolbar to the bottom bar
  (`StatusProgress`, per-recording progress + ETA); fail/cancel handled.
- **Analysis**: `population_table`, `exporters.per_cell_table`, and
  `shape_modes.fit_shape_modes` gained a `progress_cb` (per-frame), forwarded to
  the existing `per_frame_table` pass / contour loop.

Tests: `pytest` **34 passed**. New `scripts/smoke_progress.py` (offscreen)
unit-checks `StatusProgress` + `TaskRunner` and drives the real threaded compute
in both windows (progress ticks + applied results + busy-guard);
`smoke_compare_window.py` still green. All files < 500 lines.

---

## 2026-06-14 — Groups & Comparisons editor (configure grouping live)

Closed the gap that grouping was implicit (folder name → condition → `auto_design`)
with no way to reconfigure it. New **Groups & Comparisons editor** (Comparison
window toolbar ▸ **Groups…**, `gui/design_editor.py`):

- **Recordings table** — include/exclude each recording (checkbox), reassign its
  **group** (editable combo, free-text new groups allowed), per-recording cell
  counts; bulk include / exclude / set-group on the selected rows.
- **Comparisons editor** — one card per comparison: rename, choose member groups
  (colour-coded checkboxes), pick the **control**; add / remove comparisons; set
  the **vehicle/batch** pair. Auto-detect-from-names + Reset-all.
- Edits the `Project`'s `excluded` / `overrides` + `Design` **in place** and emits
  `designChanged`; the window remaps + replots with **no recompute** — grouping
  is a remap of the already-computed per-cell/MSD table (`Project.regroup`), so
  changes are instant. Include/exclude + group overrides **persist** in the
  project JSON.
- Model: `Project` gained `excluded` (labels) + `overrides` (label→group),
  override-aware `.conditions` / `.all_groups` / `.n_recordings` / `group_of` /
  `included_entries` / `regroup`; `project.ensure_colors` assigns palette colours
  to new groups. The Comparison window's `_filtered()` / ensemble MSD now go
  through `regroup`; toolbar gained the **Groups…** button.

Tests: `pytest` **34 passed** (new `tests/test_project.py` — auto-design, regroup,
effective groups, ensure_colors, save/load roundtrip). `scripts/smoke_compare_window.py`
now also drives the editor (exclude / regroup / add-comparison / control / vehicle
/ reset) and writes `docs/screenshots/groups_editor.png` (`--editshot=`). All
files < 500 lines.

---

## 2026-06-14 — Comparison window + Projects (load any dataset)

Promoted the cross-recording comparison from a cramped dock into its own
**standalone window** (Analysis ▸ Comparison window, `Ctrl+Shift+C`) and added a
**Project** concept so the app is no longer hard-wired to the single IC295
dataset.

- **`maskviewer/project.py`** (new): `Project` (name / data_roots / entries /
  `Design`) + `Design` (arms {control, conditions}, vehicle, colours).
  `auto_design()` derives the experiment from the condition names — recognises
  the IC295 genetic (WT/GOF/KO) + drug (DMSO/Y1/OT) arms and the WT–DMSO vehicle,
  otherwise builds one arm with a heuristic control. `from_entries` /
  `from_data_roots` / `load_project` / `save_project` (small JSON). GUI-free.
- **Generalised the stats** to a design: `feature_tables.arm_tests(by_cond,
  arms, vehicle)` and `compare.{effect_sizes,ols_adjusted}(…, arms)` now take an
  arbitrary arm spec (default to IC295 when called bare — back-compatible).
- **`gui/compare_window.py`** (new): `CompareWindow(QMainWindow)` — toolbar
  (Compute/recompute · Metric · Y · Control · MSD stat · Frames · OLS · Export);
  tabbed plots **Distributions** (strip / box+Bonferroni / superplot) · **Ensemble
  MSD** · **Scatter**, beside a sortable per-contrast stats table (p / Bonferroni /
  Cohen's d / OLS β,p) + omnibus KW + vehicle. Threaded compute + per-project disk
  cache; click a point → load that recording. `set_project` re-targets it.
- **`gui/compare_plots.py`** (new): design-aware pyqtgraph drawing (colours +
  condition order from the `Design`); deleted `panels/compare_panel.py`.
- **Project loading UX**: File ▸ Open Project Folder / Open Project File / Save
  Project As / **Recent Projects** (QSettings); `ViewerWindow.set_project` swaps
  the dataset live and propagates to the comparison window. `main_viewer.py` now
  builds a `Project`. `ViewerWindow` accepts a Project *or* a bare entries list
  (back-compat for the tests/smokes).
- File-size hygiene: moved `set_project` / `_rebuild_recent_menu` /
  `open_compare_window` into `WindowActionsMixin` to keep `viewer_window.py` < 500.
- **Tests**: `pytest` 28 passed; new `scripts/smoke_compare_window.py` drives
  every tab / dist-kind / OLS / stats table on fake multi-arm + single-arm data,
  checks the editable control combo, and verifies the ViewerWindow wiring
  (offscreen). Regenerated `docs/screenshots/comparison.png` (`--shot=`).

---

## 2026-06-13 — Cell-table division indicators

The Cell-Table dock now shows **parent** + **daughters** columns (label IDs) from
the recording's divisions.json — a cell with a `parent` is a child, a cell with
`daughters` is a parent (`lineage.relatives`). Columns appear only when the
recording has division events; the window passes `divisions` to
`cell_table.set_recording`. Verified on a real recording (5 divisions wired
through) + an isolated panel test. `pytest` 28 passed.

---

## 2026-06-13 — Comparison-audit gaps (ensemble MSD, state, OLS, box plots)

A background agent audited CellScope's cross-recording/comparison code; added the
high-value mask-computable gaps to the Compare dock:
- **Ensemble MSD by condition** (`compare.build_comparison` now also returns a
  per-recording ensemble MSD; `ensemble_by_condition` → mean±SEM or
  median+bootstrap-CI) — the headline migration figure. (Reuses centroids via a
  new `per_cell_table(centroids=)` param so it's not an extra pass.)
- **Per-state composition**: `frac_rounded` / `frac_spread` per cell → comparable
  metrics (the IC295 phenotype lives in state).
- **Covariate-adjusted OLS** (`compare.ols_adjusted`): per-arm treatment effect
  after frac_spread + density — disentangles migration from the state/crowding
  confounds (central to a mechanosensor claim). Dependency-free (lstsq + t-tests),
  surfaced via a dock checkbox.
- **Box plots** by condition with within-arm Bonferroni significance stars; a
  **metric-vs-metric scatter by condition** with Spearman.
Deferred (documented, lower value / dependency-gated): cell-level LMM
(statsmodels), van Elteren stratified test + CEM matching + residual
normalization, violin plots, ANOVA/Welch/Shapiro options, per-condition flower
grid / histograms, pooled cell-level stats toggle.

`pytest` 28 passed (warning-free); headless smoke verified all five plot kinds +
OLS + median MSD; screenshot refreshed. All files < 500 lines.

---

## 2026-06-13 — Cross-recording comparison dock

The big next phase: compare a metric across recordings grouped by condition,
**recording = experimental unit**.
- `analysis/compare.py`: `build_comparison` (per-cell metrics over every
  recording via each Entry's masks + `exporters.per_cell_table`, tagged with
  recording + condition), `aggregate` (→ per-recording means), `by_condition`,
  `order_conditions` (arm order), `metric_columns`.
- **Compare dock** (`panels/compare_panel.py`): background compute (QThread +
  progress + cancel) with a disk cache; pick a metric → "Recording means" (strip
  + mean±SEM per condition) or "Superplot" (per-cell cloud coloured by recording
  behind the per-recording means); stats = omnibus KW + per-arm Kruskal-Wallis +
  within-arm Bonferroni vs control + WT-vs-DMSO vehicle (reusing
  `feature_tables.arm_tests`); min-frames filter; click a point → load that
  recording; CSV export of the per-cell + per-recording tables.
- Wired into the window (new tabbed dock; `set_entries` on load / open-folder;
  `recordingPicked` → select recording). README illustrated with
  `docs/screenshots/comparison.png`.

`pytest` 28 passed (added a compare test on synthetic multi-condition fakes);
headless smoke verified both plot kinds + arm stats + click-to-load. All files
< 500 lines. Follow-up: a comparison-analysis audit of CellScope is queued.

---

## 2026-06-13 — Fix: window too large / not resizable

The stacked right docks (tabbed group + Image-Adjust) forced a ~1188 px minimum
window height, so on smaller screens the window opened oversized with its resize
edges off-screen. Fixes: (1) each dock's panel is wrapped in a resizable
`QScrollArea` so a tall panel scrolls instead of inflating the window
(minimumSizeHint 499×1188 → 289×443); (2) `setMinimumSize(720, 480)`;
(3) initial size capped to the available screen; (4) `_fit_to_screen()` clamps a
restored/oversized geometry and re-centres it on-screen at startup. Verified the
window now shrinks to 720×480 and stays on-screen; panels reachable; tests pass.

---

## 2026-06-13 — Self-drive remote, screengrab, illustrated README

- **Self-drive remote** (`gui/remote.py`, `MASKVIEWER_REMOTE=<port>`): a
  localhost HTTP server (off by default) that drives the GUI for headless/agent
  workflows — `/state`, `/set` (recording/frame/channel/colour-by/selected),
  `/cmd` (compute_population/shape/table, raise dock, overlay…), `/screenshot`.
  Commands marshal to the GUI thread via a queue drained by a QTimer.
  `remote_*` handlers live on `WindowActionsMixin`. Verified end-to-end (HTTP →
  GUI thread → grab → PNG).
- **Screengrab**: File ▸ Save View Image (canvas) / Save Window Screenshot.
- **Illustrated README**: drove the GUI headless on the synthetic sample and
  captured `docs/screenshots/{overview,cell_info,population,shape_modes,
  edge_dynamics}.png`; rewrote README around the workbench + embedded them +
  documented the remote hook. (Synthetic sample only — public-repo data policy.)
- Docs: INTERFACE (remote/plot_export/window_actions/cell_table), CLAUDE
  (run + Done + roadmap) updated.

`pytest` 27 passed; default (no-remote) build unaffected; all files < 500 lines.

---

## 2026-06-13 — Single-recording push (part 2): CellScope analysis-audit gaps

A background agent audited every CellScope analysis file; implemented the
mask/image-computable per-recording gaps it found:
- **convexity** (hull-perim/perim — perimeter-based ruffling) + **rel_area**
  (area / cell's 90th-pct, scale-free footprint collapse) — per-frame metrics.
- **membrane.py**: `boundary_confidence` (gradient along contour),
  `intensity_contrast`, `texture_contrast`, `membrane_score` — per-channel in the
  cell plot (boundary_grad_/membrane_score_ + existing intensity/membrane_contrast).
- **Fürth/PRW MSD fit** (`motion.fit_furth` → D + persistence-time P) — shown in
  the Cell-Info MSD title + per_cell export.
- **per_cell QC + contact**: density-stratified speed (isolated vs crowded) +
  frac_isolated, area-stability (CV / max-min / large-jumps), composite
  **track_quality** score.
- **VAMPIRE eigenshapes** (PCA components ± mean) + per-PC variance + normalised
  entropy, drawn in the Shape-Modes dock.
All surface automatically in the configurable cell-plot / colour-by / Config menu
(30 metrics now). Consciously deferred (documented): per-state segment
MSD/straightness suite, Sarle bimodality, shape min/max, small-τ MSD option —
low marginal value or CellScope-specific. `pytest` 27 passed; all files < 500.

---

## 2026-06-13 — Single-recording push (part 1): lineage, correlation/autocorr, edge events, cell table, save-plots, click-select, fixed scale, layout

Eight requested single-recording / UX items:
- **Cell division & lineage** (A1): load `divisions.json` (io/divisions.py),
  `analysis/lineage.py` (track spans, lineage rows, division counts, relatives);
  Population gains **Lineage tree** + **Division timeline** plots; Cell-Info
  shows parent/daughter; a **Divisions** overlay marks dividing cells.
- **Correlation & autocorrelation** (A2): Population **Scatter (X vs Y)**
  (per-cell, click a point → select); Cell-Info **Direction-autocorrelation**
  curve.
- **Per-protrusion edge events** (A3): `edge_dynamics.edge_events` (sustained
  protrusion/retraction runs → counts, rates, durations, strengths) shown in the
  edge panel + per_cell `with_edge` export.
- **Sortable per-cell table** (A4): new Cell-Table dock (sortable, row→select,
  CSV export).
- **Save plots** (U1): PNG/SVG buttons on cell-info, edge, shape, population
  (gui/plot_export.py).
- **Click-to-select linking** (U2): `ViewerWindow.select_cell` centralises
  selection; table rows + scatter points select the cell everywhere.
- **Fixed colour scale** (U3): Display toggle; `colorby` uses a cached global
  metric range (scalar_label_lut gained vmin/vmax).
- **Layout presets & polish** (U4): Window ▸ Show All Panels / Save Current
  Layout; sensible default dock width. Menu-action methods split into
  `gui/window_actions.py` (file-size).

`pytest` 23 passed; headless smoke covered every item; lineage verified on a
real recording (5 divisions). All files < 500 lines. Part 2 (next): the
CellScope analysis audit gaps.

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
