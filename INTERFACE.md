# INTERFACE.md — cellscope_analysis navigation map

Read this before opening source files. Update it when modules change.

## Docs
- **docs/DATA.md** — what's in `data/`, every per-recording file, and how the
  masks were produced (CellScope detection → review → cleaning). Read this for
  data provenance.
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

## tests/
- **test_io.py** — smoke tests (discover / load / summary) against the
  synthetic sample; regenerates it if missing. Needs `pytest`.

## Config / data
- **config.example.json** — committed template for `config.json` (gitignored,
  machine-specific, points at real CellScope results).
- **sample_data/** — committed *synthetic* recording+mask (only data in the repo).
- **data/** — local, **gitignored** symlinks into a CellScope tree (made by
  `scripts/link_data.py`); never pushed.
