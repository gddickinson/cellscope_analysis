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
- **scripts/plot_multivariate.py** — the explain-and-illustrate set:
  `mv_story_panel.png` (6-panel), `mv_shape_score.png` (combined roundness
  score via `combined_score_fig`), `mv_feature_correlation.png` (which
  features are redundant / what to combine), `mv_feature_heatmap.png`,
  `mv_top_pair.png`. → `analysis_out/` (gitignored).

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

### maskviewer/gui/  — PyQt5 + pyqtgraph
- **image_view.py** — `ImageCanvas`: base grayscale `ImageItem` + label
  overlay `ImageItem` in one locked-aspect viewbox. `make_label_lut`
  (stable per-ID colours), `label_boundaries` (outline mode), `set_base`,
  `set_overlay`, emits `cellHovered(int)`.
- **controls.py** — `ControlPanel`: recording / channel combos, frame
  slider+spinbox, show-masks + outline checkboxes, opacity slider. Emits
  `recordingChanged / channelChanged / frameChanged / overlayChanged`.
- **viewer_window.py** — `ViewerWindow(QMainWindow)`: owns the data, wires
  controls↔canvas, caches per-channel contrast levels, status bar
  (frame/time/scale/cell-count/hover), ←/→ frame stepping.

### maskviewer/analysis/  — pure-function stats (grow analysis HERE)
- **label_stats.py** — `n_cells_per_frame`, `cell_ids`, `cell_areas_px`,
  `track_lengths`, `centroids`, `summary(labels, um_per_px)`. No GUI/IO deps.
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
- **dynamics.py** — `transition_rate`, `dwell_median`, `contact_response`,
  `rounding_on_contact` over the per-cell time series → arm tests. `run()`.
- **interactions.py** — `density_slope_test` (treatment×crowding) +
  `clean_subset_test` (stable/non-dividing/in-view cells). `run()`.

## tests/
- **test_io.py** — smoke tests (discover / load / summary) against the
  synthetic sample; regenerates it if missing. Needs `pytest`.

## Config / data
- **config.example.json** — committed template for `config.json` (gitignored,
  machine-specific, points at real CellScope results).
- **sample_data/** — committed *synthetic* recording+mask (only data in the repo).
- **data/** — local, **gitignored** symlinks into a CellScope tree (made by
  `scripts/link_data.py`); never pushed.
