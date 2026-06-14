# INTERFACE.md — cellscope_analysis navigation map

Read this before opening source files. Update it when modules change.

## Docs
- **docs/DATA.md** — what's in `data/`, every per-recording file, and how the
  masks were produced (CellScope detection → review → cleaning). Read this for
  data provenance.
- **docs/FINDINGS_followup.md** — results of the multivariate/dynamics/
  interaction investigation: the KO multivariate phenotype (the win), the
  informative nulls, and evidence-weighted next steps.
- **CLAUDE.md** — agent handoff (formats, how to run, conventions, seeds).

## Entry points
- **main_viewer.py** — CLI launcher. Resolves recordings (from `config.json`
  `data_roots`, `--data-root`, or an explicit `--recording/--masks`),
  discovers them, wraps them in a **Project** (`project.from_entries`, with the
  data-root folder name as the project name), and opens `ViewerWindow`. Qt is
  imported lazily so `--help` needs no display.
- **scripts/make_sample_data.py** — writes the synthetic `sample_data/Pos_demo/`
  (recording `.ome.tif` + `.ome.json` + `pipeline_results/masks.npz`). Safe,
  fake data so the app runs out of the box.
- **scripts/link_data.py** — populates the gitignored `data/` folder with
  symlinks into a CellScope tree (`by_condition`, flat `recordings/`,
  `results/`, `gt/`). Convenience browser + viewer `data_root`. Idempotent.
- **scripts/smoke_compare_window.py** — headless (QT offscreen) smoke for the
  Comparison window + Project wiring: drives every tab / dist-kind / OLS / stats
  table on fake multi-arm + single-arm data, checks the editable control combo,
  exercises the **filters** (frames / quality / cells-per-rec / state / crowding /
  edge via the Filters… dialog), the right **Stats / Histogram / Data** tabs +
  units, the **bars view + plot-style dialog (incl. trendline) + shift-right-click**,
  the **Groups & Comparisons editor** (exclude / regroup / add-comparison / control
  / vehicle / reset), and verifies `ViewerWindow.open_compare_window` /
  `set_project`. `--shot=PATH` (also writes `_msd` / `_histogram` / `_style` /
  `_filters` variants) / `--editshot=PATH` (re)write the screenshots.
- **scripts/smoke_progress.py** — headless smoke for the status-bar progress bars:
  unit-checks `StatusProgress` + `TaskRunner`, then drives the main viewer's
  Population / Cell-table / Shape computes through the off-thread runner (asserting
  progress ticks + applied results) and the Comparison window's threaded compute,
  plus the busy-guard.
- **scripts/run_followup.py** — runs the multivariate / dynamics /
  interactions investigation and prints arm-structured results.
- **scripts/plot_followup.py** — writes the basic multivariate figures
  (genetic-arm PCA, KO fingerprint) to `analysis_out/` (gitignored).
- **scripts/plot_metric_arms.py** — arm-structured control-vs-treatment
  comparison of any recording-level metric (`--metric`, default
  `persistence_spread`): box+strip per arm with within-arm Bonferroni stars
  (`<metric>_arms.png`) + a Cohen's-d-vs-control forest (`<metric>_effect.png`).
- **scripts/plot_multivariate.py** — the explain-and-illustrate set:
  `mv_story_panel.png` (6-panel), `mv_shape_score.png` (combined roundness
  score via `combined_score_fig`), `mv_feature_correlation.png` (which
  features are redundant / what to combine), `mv_fingerprint_grid.png` (all 4
  treatment-vs-control fingerprints, shared scale + PERMANOVA/AUC — why KO is
  the only significant one), `mv_roundness_vs_persistence.png` (are the two KO
  axes linked? between-condition yes / within-condition no → distinct,
  non-redundant), `mv_feature_heatmap.png`, `mv_phenotype_2d.png`.
  → `analysis_out/` (gitignored).

## maskviewer/ (package)
- **config.py** — `load_config(path)` → dict with `data_roots` (always
  appends the bundled `sample_data/` as a fallback). `PROJECT_ROOT`,
  `SAMPLE_DIR`, `CONFIG_PATH` constants.
- **project.py** — `Project` (name, data_roots, entries, design, **`excluded`**
  recording labels + **`overrides`** label→group; `.conditions` (effective,
  override-aware), `.all_groups`, `.n_recordings`, `group_of`, `included_entries`,
  **`regroup(df)`** = drop-excluded + apply-overrides remap of a per-cell/MSD
  frame so grouping changes need no recompute) + `Design` (`arms`
  {arm:{control,conditions}}, `vehicle`, `colors`; `condition_order`, `color`).
  `auto_design(conditions)` derives the experiment structure (recognises the
  IC295 genetic/drug arms + WT–DMSO vehicle; otherwise one arm with a heuristic
  control); `ensure_colors(design, groups)` assigns palette colours to new
  groups. `from_entries`, `from_data_roots` (discover + auto-design),
  `load_project`/`save_project` (small JSON, incl. excluded/overrides). Decouples
  the app from the hard-coded IC295 design so any dataset (any treatments /
  counts / groupings) loads + compares correctly. GUI-free.

### maskviewer/io/  — load data (GUI-free)
- **recording.py** — `load_recording(tif)` → `Recording` (`data` as
  `(T,C,H,W)`, `channel_names`, `um_per_px`, `time_interval_min`, `.frame(t,c)`).
  Reads the `.ome.json` sidecar; coerces 2-D/3-D inputs to `(T,C,H,W)`.
- **masks.py** — `load_masks(npz)` → `Masks` (`labels` `(T,H,W)`,
  `.frame(t)`, `.max_label`, `.cell_ids()`, `.n_cells_per_frame()`).
- **dataset.py** — `discover(roots)` → sorted `[Entry]`; an `Entry`
  (`label`, `condition`, `recording_path`, `mask_path`) loads its recording
  / masks lazily. A folder qualifies if it has a `*.ome.tif` + (ideally)
  `pipeline_results/masks.npz`.

### maskviewer/gui/  — PyQt5 + pyqtgraph (dockable workbench)
- **image_view.py** — `ImageCanvas`: base grayscale `ImageItem` (user LUT +
  display levels) + label overlay `ImageItem` + an `Overlays` layer, in one
  locked-aspect viewbox. `make_label_lut` (stable per-ID colours),
  `scalar_label_lut` (colour-by-feature), `label_boundaries` (outline mode),
  `set_base(img, levels, lut)`, `set_base_layers([...])` (additive composite of
  several channels), `set_overlay(...)`, `set_colorbar(legend)` (units colour bar
  for colour-by, via a `ColorBarItem`), emits `cellHovered(int)` +
  `cellClicked(int)`, `zoom`/`autorange`.
- **colorby.py** — `overlay_lut(win, lab)` → `(label-LUT, legend)` for the
  current colour-by metric (legend = lo/hi/cmap/units for the colour bar).
- **overlays.py** — `Overlays`: scale bar, frame/time text, cell-ID labels,
  track trails, selected-cell highlight; corner items re-anchor on pan/zoom.
- **luts.py** — `build_lut(colormap, gamma, invert)` → RGBA LUT, `PRESETS`,
  and `DisplayState` (the per-channel levels/colormap/gamma/invert record).
  No Qt import (testable headless).
- **panels/** — each a signal-only `QWidget` dock:
  - **timeline.py** `TimelinePanel` — frame slider + play/pause/fps/loop +
    time readout (bottom bar). Emits `frameChanged`.
  - **display_panel.py** `DisplayPanel` — recording/channel pickers, composite
    toggle + per-channel visibility, mask show/outline/opacity, colour-by (id /
    state / area / perimeter / circularity / eccentricity / aspect-ratio /
    solidity / extent / nearest-neighbour / neighbour-count / mean-speed /
    track-length / shape-mode), overlay toggles.
  - **image_adjust.py** `ImageAdjustPanel` — histogram + draggable levels,
    brightness/contrast sliders, gamma, colormap, invert, auto/reset. Emits
    `displayChanged`; `state()`/`set_state()` for per-channel persistence.
  - **cell_info.py** `CellInfoPanel` — selected-cell summary + a combo to plot
    any *enabled* per-frame characteristic (shape, perimeter, circularity, state,
    speed, displacement, turning, IoU, area-change, nearest-neighbour, intensity,
    membrane contrast) over time + MSD (log-log **or linear**) with α/D fit. Owns
    the enabled-metric set (QSettings-persisted); `set_metric_enabled` recomputes
    immediately.
  - **edge_panel.py** `EdgePanel` — velocity / radius **kymograph** (angle×time,
    blue=retraction/red=protrusion) **and a per-frame edge map** (the cell's
    boundary in the current frame coloured by per-sector velocity or radius) +
    summary + kymograph CSV export, for the selected cell.
  - **shape_panel.py** `ShapeModesPanel` — VAMPIRE shape modes: mode mean-shapes,
    mode-fraction bars, heterogeneity entropy (lazy compute button). Compute runs
    off-thread (`AsyncComputeMixin`) → status-bar progress + ETA.
  - **population_panel.py** `PopulationPanel` — all-cells plots for the recording:
    time series / mean ± SEM-or-SD error band / histogram / flower plot / scatter
    (X vs Y, click→select) / lineage tree / division timeline, with filters
    (min track length, state, exclude edge); off-thread compute (`AsyncComputeMixin`)
    → status-bar progress + ETA, cached.
  - **cell_table.py** `CellTablePanel` — sortable per-cell metric table (+
    `parent` / `daughters` columns from divisions.json); row → select cell;
    CSV export. Off-thread compute (`AsyncComputeMixin`) → status-bar progress + ETA.
  (cross-recording comparison is no longer a dock — it is its own window, see
  **compare_window.py** below.)
- **compare_window.py** — `CompareWindow(QMainWindow)`: the dedicated comparison
  space (Analysis ▸ Comparison window), opened on the loaded **Project**.
  Background compute (`_Worker` thread) + per-project disk cache; toolbar
  (Compute/recompute · **Groups…** (opens `DesignEditor`) · Metric · Y ·
  **Control** (editable for single-arm designs) · MSD stat · OLS · Export) + a
  **Filters…** button (opens the `FilterMixin` dialog: frames / track-quality /
  cells-per-recording / state / nearest-neighbour crowding / distance-from-edge).
  Left tabbed plots — **Distributions** (strip / box+Bonferroni / bars /
  superplot) · **Ensemble MSD** · **Scatter** (all axis-labelled with units). The
  right panel is tabbed: **Stats** (sortable per-contrast p / Bonferroni / Cohen d
  / OLS β,p + omnibus KW + vehicle — via `StatsTablesMixin`) · **Histogram**
  (per-cell distribution by group) · **Data** (per-recording + per-group tables,
  unit-tagged). Uses the project's `Design`; click a point → load that recording
  (`recordingPicked`). `set_project` re-targets it. Threaded compute reports into a
  bottom-bar **`StatusProgress`** (per-recording progress + ETA). Both whole-track
  **and** state-segmented (`…_spread` / `…_rounded`) metrics are offered; metric
  combos carry per-column tooltips (`metric_docs.comparison_tooltip`); a **Help**
  button opens the Metrics & methods reference; a **Style…** button (or
  shift-right-click a plot) opens the `PlotStyleDialog`; tabs/controls tooltipped.
- **compare_tables.py** — `StatsTablesMixin`: fills the right-panel **Stats** +
  **Data** tables from the per-recording table + Design (`_update_stats`,
  `_fill_data`, `_set_table`); + `show_metrics_help(parent)` (the Metrics &
  methods reference dialog). Split out to keep `compare_window` small.
- **compare_filters.py** — `FilterMixin`: builds the cell/recording filter widgets,
  lays them out in a non-modal **Filters…** dialog, and applies them in `_filtered`
  (min frames · track-quality · min cells/recording · state · NN distance min/max ·
  neighbour count min/max · distance-from-image-edge). Session-only (+ Reset).
- **compare_plots.py** — design-aware pyqtgraph drawing for `CompareWindow`
  (GUI-state-free): `strip` (mean ± SEM, clickable), `box` (+ Bonferroni stars
  via `arm_tests`), `bars` (group mean ± SEM), `superplot` (cells + per-recording
  means), `ensemble_msd` (mean±SEM / median+CI bands; band-bound curves are added
  to the plot so they inherit its log mode + clamped > 0 — fixes misaligned
  log-log bands/lines), `scatter` (X-vs-Y + Spearman, clickable), `histogram`
  (per-cell distribution by group). A **`trendline`** (`_trend`) option draws a
  scatter least-squares line and connects per-group centres on the categorical
  plots. Colours + order from the `Design`; axes labelled with units via
  `metric_docs.axis_label`. Every function takes a `PlotStyle` (fonts /
  marker+line size / fill opacity / grid / log axes / histogram bins / trendline…)
  applied via the shared `_axes` helper.
- **plot_style.py** — `PlotStyle` (dataclass of render options incl. `trendline`,
  QSettings-persisted) + `PlotStyleDialog` (non-modal live editor) +
  `PlotStyleMixin` (opens the editor from a toolbar button **or shift-right-click
  on any plot**, saves + replots).
- **design_editor.py** — `DesignEditor(QDialog)`: the **Groups & Comparisons**
  editor opened from the Comparison window (toolbar ▸ Groups…). A recordings
  table (include checkbox + editable **group** combo + cell counts, with bulk
  include/exclude/set-group) over a comparisons editor (per-comparison member-group
  checkboxes + control combo + rename/remove, an Add-comparison button, and a
  vehicle/batch pair) + Auto-detect / Reset. Edits the `Project`'s
  `excluded`/`overrides` + `Design` in place and emits `designChanged`; the
  window remaps + replots with **no recompute**.
- **menus.py** — `build_menubar(win)`: File (Open Recording / **Open Project
  Folder / Open Project File / Save Project As / Recent Projects** / Export CSV /
  screenshots) / View / Image / Analysis (**Comparison window…** `Ctrl+Shift+C`
  + Export CSV) / **Config** (Cell-plot-metrics checkable submenu, rebuilt per
  recording) / Window / Help (incl. **Metrics Reference…** → `metric_docs.as_html`).
  Tooltips throughout.
- **export_dialog.py** — `CSVExportDialog`: pick tables + folder/prefix; runs on
  a worker `QThread` with a progress bar + Cancel; solidity / edge-dynamics opts.
- **plot_export.py** — `save_plot(plot, parent)`: PNG/SVG export for any panel plot.
- **status_progress.py** — `StatusProgress(QWidget)`: a compact status-bar progress
  widget (label + bar + elapsed/**ETA**, `fmt_secs`); `start` / `update(done,
  total)` / `finish` / `fail`. ETA = elapsed × remaining/done. Embedded in both
  windows' bottom bars.
- **task_runner.py** — `TaskRunner(QObject)`: runs `fn(progress_cb)` on a worker
  `QThread`, re-emitting `progress` and calling `on_done` / `on_error` on the GUI
  thread (one task at a time; busy → refuses). `AsyncComputeMixin._dispatch` lets a
  panel run its heavy compute through an injected `run_async` (the window's
  `run_task`), falling back to synchronous compute when none is set (tests/headless).
- **window_actions.py** — `WindowActionsMixin`: File/Window/Help action handlers
  (incl. **project** open-folder / open-file / save-as / recent-projects +
  `set_project` to adopt a different dataset, and `open_compare_window`), the
  lazy+cached heavy-compute providers (`_population_table` / `_shape_modes_model`,
  `progress_cb`-aware), **`run_task`** (off-thread compute → status-bar bar/ETA),
  + the remote-control handlers (`remote_state/set/cmd/screenshot`); keeps
  `viewer_window` small.
- **remote.py** — `RemoteControl`: optional localhost HTTP self-drive
  (`MASKVIEWER_REMOTE=<port>`); marshals commands to the GUI thread; for headless
  agent driving + screenshots.
- **viewer_window.py** — `ViewerWindow(QMainWindow)`: accepts a **Project** (or a
  bare entries list, auto-wrapped); owns the data, builds the docks (Display +
  Cell-Info + Edge-Dynamics + Shape-Modes + Population + Cell-Table tabbed +
  Image-Adjust right; Timeline bottom; each dock wrapped in a scroll area so the
  window fits any screen), wires panels↔canvas, split base/overlay rendering
  (single or additive **composite**), colour-by any calculated metric + units
  **colour bar** (`colorby.overlay_lut`), lazy caches (centroid history / track
  lengths / mean speeds / shape-mode model) shared as providers, click-to-select →
  Cell-Info + Edge dock, opens the standalone **CompareWindow** (lazy, kept in
  sync via `set_project`), `show_metrics_help`, layout save/restore (QSettings) +
  Reset Layout, **status bar with a `StatusProgress` bar+ETA** (heavy panel
  computes run off-thread via `run_task` + `TaskRunner`), ←/→/Space shortcuts.

### maskviewer/analysis/  — pure-function stats (grow analysis HERE)
- **label_stats.py** — `n_cells_per_frame`, `cell_ids`, `cell_areas_px`,
  `track_lengths`, `centroids`, `summary(labels, um_per_px)`. No GUI/IO deps.
- **cell_metrics.py** — morphometry (no skimage; perimeter via a Crofton
  estimate matching skimage): `regionprops_frame` (area, centroid, bbox, axes,
  eccentricity, aspect ratio, orientation, extent, edge flag, state, optional
  solidity / perimeter+circularity), `per_frame_records` (+ nearest-neighbour
  columns, `progress_cb`), `centroid_history`, `cell_series`, and
  `cell_frame_table` (per-frame series for ONE cell — shape, perimeter,
  circularity, **convexity**, **rel_area**, state, speed, displacement, turning,
  consecutive IoU, area-change, nearest-neighbour, and per-channel intensity /
  membrane-contrast / **boundary-gradient** / **membrane-score**). `metrics=`
  selects which series to compute. `available_frame_metrics` / `metric_label` /
  `BASE_FRAME_METRICS` drive the Config ▸ Cell-plot-metrics menu.
- **motion.py** — centroid-track motion: `instantaneous_speed`,
  `displacement_metrics` (net/path/straightness/speed), `direction_autocorrelation`
  + `persistence` (lag-1, speed-unbiased), `msd` + `fit_msd` (D, α exponent),
  `fit_furth` (Fürth/PRW D + persistence-time), `turning_angles`, `motion_summary`.
- **membrane.py** — boundary/membrane quality from mask + image channel:
  `boundary_confidence` (gradient along contour), `intensity_contrast`,
  `texture_contrast`, `membrane_score` (composite). PIEZO1-relevant.
- **state.py** — `classify_state` → rounded/spread/edge/unknown per cell-frame
  (CellScope IC295 rule: area ≤ 960 µm² AND ecc ≤ 0.85 → rounded), `STATE_CODE`,
  `STATE_COLOR`.
- **neighbors.py** — `frame_nn`: per-cell nearest-neighbour distance + count of
  neighbours within a radius (`DEFAULT_RADIUS_UM`), centroid-to-centroid.
- **edge_dynamics.py** — membrane protrusion/retraction (no cv2):
  `edge_velocity_kymograph` (radial edge velocity, 72 sectors about the
  mid-centroid; +protrusion/−retraction), `radius_kymograph`, `edge_summary`
  (protrusion/retraction/net/ruffling), `edge_summary_for_cell`.
- **shape_modes.py** — VAMPIRE-style population shape clustering (sklearn):
  `fit_shape_modes` (aligned radial contour signatures → PCA + K-means → mode
  per cell-frame + mode mean-shapes + Shannon-entropy heterogeneity),
  `cell_mode_series`, `cell_heterogeneity`, `mode_contour`; the model also returns
  **eigenshapes** (PCA components) + per-PC explained variance + normalised entropy.
  `fit_shape_modes` takes `progress_cb` (per-frame, drives the GUI progress bar).
- **population.py** — all-cells analysis for one recording: `population_table`
  (per-(cell,frame) shape + nearest-neighbour + state + per-frame `speed`,
  `progress_cb`-aware), `metric_columns`, `flower_tracks` (origin-centred trajectories).
- **metric_docs.py** — `doc` / `tooltip` / `as_html`: what each metric indicates
  + how it's calculated (powers Help ▸ Metrics reference and the GUI tooltips);
  plus `column_units` / `column_label` / `axis_label` — derive display units +
  a human name for an aggregated comparison column (e.g. `mean_area_um2` →
  "mean area (µm²)", `mean_speed_spread` → "mean speed [spread]"), used for plot
  axes + table headers; and `comparison_doc` / `comparison_tooltip` — resolve any
  aggregated / per-state column to its (what, how) doc + a tooltip. `as_html`
  includes a **Cross-recording comparison** section (recording = unit, whole-track
  vs state-segmented, filters, stats).
- **compare.py** — cross-recording comparison (recording = unit): `build_comparison`
  (→ per-cell table over many recordings + condition, AND per-recording ensemble
  MSD), `aggregate`, `by_condition`, `order_conditions`, `metric_columns`,
  `ensemble_by_condition` (mean±SEM / median+bootstrap-CI MSD curves),
  `ols_adjusted` (per-arm covariate-adjusted treatment effect),
  `per_condition_summary` (per-group n / mean / SEM / median over recordings —
  the Data tab). Per-arm KW / Bonferroni reuse `feature_tables.arm_tests`.
  `build_comparison` also merges in the **state-segmented** per-cell metrics
  (`state_metrics`) so the GUI can reproduce the original analysis.
- **state_metrics.py** — `per_cell_state_metrics`: per-cell metrics computed
  **separately over rounded vs spread frames** (`mean_speed_{s}`,
  `persistence_{s}`, `straightness_{s}`, `mean_area_um2_{s}`, …), reproducing the
  original CellScope state-aware analysis — edge frames excluded, per-step speed
  capped at 15 µm/min, persistence/straightness over contiguous same-state
  segments (≥5 frames). Mirrors the original `core/motility_state.py` +
  `core/state_analysis.py` (validated to match `compare/per_recording.csv` to 3 dp).
- **exporters.py** — tidy CSV tables for Origin/Prism: `per_frame_table`
  (region props incl. perimeter/circularity/state + nearest-neighbour),
  `per_cell_table` (track + shape + motion + nearest-neighbour aggregates +
  Fürth D/persistence-time + density-stratified speed + area-stability +
  track-quality + **min/mean distance from the image border**, optional
  `with_edge` protrusion/retraction columns, `progress_cb`),
  `track_table` (trajectories), `export_all` (single shared per-frame pass +
  `progress_cb`).
  Needs pandas.
- **feature_tables.py** — data layer for the follow-up analyses: loads the
  CellScope IC295 artifacts via `data/` (`recordings()`, `cells()`,
  `tracks()`) + the experimental design (`ARMS`, `VEHICLE`) +
  `arm_tests()` (per-arm KW + within-arm Bonferroni + vehicle MWU).
  Needs scipy/pandas.
- **multivariate.py** — recording-level `permanova`, leave-one-recording-out
  `loro_auc` / `loro_detail` (held-out scores + permutation null), `loadings`
  (Cohen's d fingerprint), `univariate_p`, and `add_shape_score` (collapses
  the collinear shape cluster `SHAPE_FEATURES` into one `shape_roundness`
  PC1; `FEATURES_COMBINED` is the de-duplicated set). `run()`. **Found the KO
  phenotype** (one roundness axis, KO vs WT p=0.0006) the univariate tests
  missed (needs sklearn).
- **edges.py** — `edge_flags()` recomputes a per-frame edge-truncation flag
  per cell from the masks (a cell is edge in frame t if its label touches the
  border), cached to `analysis_out/_edge_flags.pkl`. Lets centroid-based
  metrics skip partially-out-of-view frames.
- **dynamics.py** — `transition_rate`, `dwell_median`, `contact_response`,
  `rounding_on_contact` over the per-cell time series → arm tests. `run()`
  attaches `edges.edge_flags` so centroid-based metrics **skip edge frames**
  (state-based ones already exclude edge via the `unknown` state).
- **interactions.py** — `density_slope_test` (treatment×crowding) +
  `clean_subset_test` (stable/non-dividing/in-view cells). `run()`.

## tests/
- **test_io.py** — smoke tests (discover / load / summary) against the
  synthetic sample; regenerates it if missing. Needs `pytest`.
- **test_analysis.py** — cell_metrics / motion / exporters (known-answer
  synthetic arrays + the sample): shape morphometry, persistence vs
  straightness, CSV table shapes + writing.
- **test_project.py** — Project/Design model (GUI-free): auto-design (IC295 +
  generic single-arm), `regroup` exclude/override, effective conditions +
  `all_groups`, `ensure_colors`, save/load roundtrip of excluded/overrides.
- **test_compare_extras.py** — `metric_docs` units / labels / per-state suffix /
  `comparison_doc` + `compare.per_condition_summary` (units + per-group summary).
- **test_state_metrics.py** — `state_metrics`: segmentation helper, persistence /
  straightness on synthetic straight tracks, end-to-end per-cell state metrics on
  a moving-square stack, and the speed cap.

## Config / data
- **config.example.json** — committed template for `config.json` (gitignored,
  machine-specific, points at real CellScope results).
- **sample_data/** — committed *synthetic* recording+mask (only data in the repo).
- **data/** — local, **gitignored** symlinks into a CellScope tree (made by
  `scripts/link_data.py`); never pushed.
