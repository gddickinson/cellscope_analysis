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
  discovers them, and opens `ViewerWindow`. Qt is imported lazily so
  `--help` needs no display.
- **scripts/make_sample_data.py** — writes the synthetic `sample_data/Pos_demo/`
  (recording `.ome.tif` + `.ome.json` + `pipeline_results/masks.npz`). Safe,
  fake data so the app runs out of the box.
- **scripts/link_data.py** — populates the gitignored `data/` folder with
  symlinks into a CellScope tree (`by_condition`, flat `recordings/`,
  `results/`, `gt/`). Convenience browser + viewer `data_root`. Idempotent.
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
  several channels), `set_overlay(...)`, emits `cellHovered(int)` +
  `cellClicked(int)`, `zoom`/`autorange`.
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
    mode-fraction bars, heterogeneity entropy (lazy compute button).
- **menus.py** — `build_menubar(win)`: File/View/Image/Analysis/**Config**
  (Cell-plot-metrics checkable submenu, rebuilt per recording)/Window/Help.
- **export_dialog.py** — `CSVExportDialog`: pick tables + folder/prefix; runs on
  a worker `QThread` with a progress bar + Cancel; solidity / edge-dynamics opts.
- **viewer_window.py** — `ViewerWindow(QMainWindow)`: owns the data, builds the
  docks (Display + Cell-Info + Edge-Dynamics + Shape-Modes tabbed + Image-Adjust
  right; Timeline bottom), wires panels↔canvas, split base/overlay rendering
  (single or additive **composite** of visible channels), colour-by any
  calculated metric (`_overlay_lut` builds the per-cell value→LUT), lazy caches
  (centroid history / track lengths / mean speeds / shape-mode model) shared as
  providers, click-to-select → Cell-Info + Edge dock, layout save/restore
  (QSettings) + Reset Layout, status bar, ←/→/Space shortcuts.

### maskviewer/analysis/  — pure-function stats (grow analysis HERE)
- **label_stats.py** — `n_cells_per_frame`, `cell_ids`, `cell_areas_px`,
  `track_lengths`, `centroids`, `summary(labels, um_per_px)`. No GUI/IO deps.
- **cell_metrics.py** — morphometry (no skimage; perimeter via a Crofton
  estimate matching skimage): `regionprops_frame` (area, centroid, bbox, axes,
  eccentricity, aspect ratio, orientation, extent, edge flag, state, optional
  solidity / perimeter+circularity), `per_frame_records` (+ nearest-neighbour
  columns, `progress_cb`), `centroid_history`, `cell_series`, and
  `cell_frame_table` (per-frame series for ONE cell — shape, perimeter,
  circularity, state, speed, displacement, turning, consecutive IoU, area-change,
  nearest-neighbour, per-channel intensity + membrane contrast). `metrics=`
  selects which series to compute. `available_frame_metrics` / `metric_label` /
  `BASE_FRAME_METRICS` drive the Config ▸ Cell-plot-metrics menu.
- **motion.py** — centroid-track motion: `instantaneous_speed`,
  `displacement_metrics` (net/path/straightness/speed), `direction_autocorrelation`
  + `persistence` (lag-1, speed-unbiased), `msd` + `fit_msd` (D, α exponent),
  `turning_angles`, `motion_summary`.
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
  `cell_mode_series`, `cell_heterogeneity`, `mode_contour`.
- **exporters.py** — tidy CSV tables for Origin/Prism: `per_frame_table`
  (region props incl. perimeter/circularity/state + nearest-neighbour),
  `per_cell_table` (track + shape + motion + nearest-neighbour aggregates,
  optional `with_edge` protrusion/retraction columns), `track_table`
  (trajectories), `export_all` (single shared per-frame pass + `progress_cb`).
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

## Config / data
- **config.example.json** — committed template for `config.json` (gitignored,
  machine-specific, points at real CellScope results).
- **sample_data/** — committed *synthetic* recording+mask (only data in the repo).
- **data/** — local, **gitignored** symlinks into a CellScope tree (made by
  `scripts/link_data.py`); never pushed.
