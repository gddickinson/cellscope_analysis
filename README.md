# cellscope_analysis

A **viewer + analysis workbench** for [CellScope](https://github.com/gddickinson/cellscope)
detection results — microscopy recordings (`.ome.tif`) with their
segmentation/tracking masks (`masks.npz`). CellScope *produces and edits* the
masks; this app is the **bench for analysing them**: view recordings with mask
overlays, inspect individual tracked cells, quantify shape / motility / membrane
dynamics, compare all cells in a recording, and export everything as CSV.

CPU-only (no GPU/torch). PyQt5 + pyqtgraph GUI; a pure, GUI-free `maskviewer/analysis`
package does the maths. Built for a **PIEZO1** keratinocyte-migration study
(see `docs/DATA.md`), but general to any CellScope recording.

![overview — masks coloured by a metric with a units colour bar](docs/screenshots/overview.png)

## Highlights

- **Dockable workbench** — every panel detaches/resizes; layout persists. The
  time bar sits below the view (play/pause, fps, loop).
- **Full image controls** — histogram + draggable levels, brightness/contrast,
  gamma, colormap (LUT), invert, auto; per channel; **composite** multi-channel
  blend (DIC grey + SiR-actin Cy5 magenta).
- **Colour cells by any metric** with a **units colour bar** (area, circularity,
  speed, nearest-neighbour, **contact fraction / count / class**, shape mode,
  track length, …); per-frame state colouring + a **mask source** mode (which
  channel detected each cell — DIC / Cy5 / both, from the detection fusion).
- **Cell–cell contact** — *where cells physically touch* (shared mask boundary),
  distinct from centroid proximity. Per frame each cell gets a **contact fraction**
  (share of its membrane engaged), interface length, contact count and a class —
  **free / point / extensive**. A **Cell contacts** overlay draws the touching
  interfaces (blue point / red extensive); over a track it measures **contact
  episodes** (formation/breakage frequency + duration); and an **Export CSV ▸
  cell-pair contacts** table records **which cells touch, when, and the degree**.
  Available as colour-by, per-cell plots, and **cross-treatment comparison metrics**.
- **Per-cell inspection** — click a cell → metrics + plot of *any* per-frame
  characteristic (shape, perimeter, circularity, convexity, state, speed,
  displacement, turning, IoU, nearest-neighbour, per-channel intensity / membrane
  metrics) + MSD (log/linear, α/D + Fürth persistence-time) + direction
  autocorrelation. **Zoom to Cell** (`Z`) frames the view on the selected cell —
  handy in a large sparse field of view.
- **Membrane dynamics** — protrusion/retraction, **boundary radius** and
  **edge-curvature** **kymographs** (+ matching per-frame edge maps coloured by edge
  velocity / radius / curvature / intensity), with event detection. With a
  **fluorescence channel** (tagged **PIEZO1**, **SiR-actin**, or any signal),
  correlate **edge movement ↔ fluorescence intensity** — at each edge point a
  rectangle reaches into the cell (configurable **positioning** — straight inward, or
  flip/search to recover concave edges) and its mean intensity is plotted against the
  local protrusion/retraction (scatter coloured by movement class, regression line,
  **Pearson r / R² / p**, plus protrude-vs-retract means and a t-test/Mann–Whitney). A
  faithful reproduction of the lab's `cell_edge_analysis` pipeline, adapted to closed
  tracked cells. Available per cell and as a **cross-treatment comparison metric**.
- **Pre-analysis: channel alignment & FOV** — DIC↔fluorescence channels are often
  offset by a small shift and recordings can carry black borders, both of which bias
  mask-relative sampling. **Analysis ▸ Channel Alignment & FOV** aligns a channel to a
  reference (**auto** gradient phase-correlation or manual dy/dx) and defines the
  field of view (**auto** border-trim or a manual rectangle), with a live grey/magenta
  overlay. Corrections are **non-destructive** (stored on the project, applied to both
  display and analysis); recordings with **1, 2 or any number of channels** are
  supported.
- **Shape modes** — VAMPIRE-style clustering (mode shapes, fractions, entropy,
  eigenshapes).
- **Population** — all cells at once: time series, mean ± SEM/SD, histogram,
  scatter, **flower plot**, lineage tree + division timeline; with filtering.
- **Projects** — load any dataset (any treatments / recording counts) via
  **File ▸ Open Project Folder** (auto-derives the experimental *design* — arms,
  controls, vehicle, colours), save/reopen it as a small **project file**, and
  switch between **Recent Projects** without restarting. Recordings are analysed
  independently, so a project may mix **different image sizes and lengths** —
  e.g. **single-cell crops** that vary in shape and span only the frames where the
  cell is present. **Config ▸ Settings…** (`Ctrl+,`) is one tabbed window for all
  analysis settings — **cell-plot metrics** (which per-frame metrics are computed),
  **comparison analysis** (toggle the heavier families — contacts / state-segmented
  / solidity — the comparison computes), and **pixel size & time scale** (µm/px +
  min/frame overrides for when a file's metadata is missing or wrong).
- **Comparison window** — a dedicated space (**Analysis ▸ Comparison window**,
  `Ctrl+Shift+C`) for cross-recording / treatment analysis (**recording =
  experimental unit**): tabbed **Distributions** (strip / box+Bonferroni /
  superplot) · **Ensemble MSD** (mean±SEM or median+CI) · **Scatter** (X-vs-Y +
  Spearman) · **Direction autocorrelation** (DiPer-style directional-persistence
  decay curves per condition — Gorelik & Gautreau 2014), all with **units on the
  axes**. A **Filters** row (min frames, min
  track-quality, min cells/recording, cell-state) refines the cells/recordings
  used; the right panel is tabbed — **Stats** (per-contrast p / Bonferroni /
  Cohen's d / covariate-adjusted OLS + per-arm KW + vehicle) · **Histogram**
  (per-cell distribution by group) · **Data** (per-recording + per-group tables,
  unit-tagged). The Stats tab's **Ranked report…** lists *every* group-vs-group
  pair for the current metric **ordered by the likelihood of a significant
  difference** (Mann–Whitney U + Cohen's d + Bonferroni; CSV-exportable) — beyond
  the design's control-vs-test contrasts. A **multivariate phenotype test**
  (Results ▾) reports per-arm **PERMANOVA p + leave-one-recording-out AUC** over all
  metrics — catching separation single metrics miss. It offers **whole-track** metrics and
  **state-segmented** ones
  (`mean_speed_spread`, `persistence_spread`, …) that reproduce the original
  CellScope state-aware analysis. A **Help** button + per-metric tooltips explain
  every metric, and every graph is **stylable** — a **Style…** button (or
  **shift-right-click a plot**) sets fonts, marker/line sizes, fill opacity, grid,
  log axes, histogram bins, bars-vs-points, **trendlines**, **scatter fit lines**
  (linear / polynomial / power / exp / log; all-data / per-group / both; ±SE band),
  **background colour**, a
  **legend**, **which groups are shown**, ensemble-MSD **τ-bin / max display lags /
  linear axis / point markers** (plus a compute-time **MSD lag count** in the
  toolbar), and a **filter annotation** that labels graphs + tables when
  filtering is active (persisted; also via main-window **Config ▸ Comparison plot
  options**). **Results ▾** saves / loads the computed comparison results
  (reload without recompute) or exports CSVs. Background compute + per-project
  cache; click a point → load that recording in the viewer.
- **Groups & Comparisons editor** (Comparison window ▸ **Groups…**) — assign
  recordings to **groups**, **include/exclude** any recording, define which groups
  form each **comparison** and which is the **control**, and set the vehicle pair.
  Changes apply **instantly** (a remap of the computed table — no recompute) and
  save with the project.
- **Filters** (Comparison window ▸ **Filters…**) — restrict the cells/recordings
  compared: min frames tracked, track-quality, min cells/recording, cell state,
  **nearest-neighbour crowding** (NN distance + neighbour count, min/max), and
  **distance from the image edge**.
- **Sortable per-cell table**, **CSV export** (per-frame / per-cell / tracks /
  **cell-pair contacts**, for Origin/Prism), **save any plot** (PNG/SVG), and a
  **Help ▸ Metrics Reference** documenting every metric + tooltips throughout.

| Cell inspection | Population (flower) | Shape modes |
|---|---|---|
| ![cell info](docs/screenshots/cell_info.png) | ![population](docs/screenshots/population.png) | ![shape modes](docs/screenshots/shape_modes.png) |

*Edge movement ↔ SiR-actin (Cy5) on a real WT-control cell — the edge-movement vs
per-sector intensity scatter (coloured by movement class) with regression line and
r/R²/p, the sampling rectangles, and the boundary coloured by per-sector intensity:*

| Edge movement ↔ intensity | Sampling rectangles (coloured by intensity) | Edge this frame: intensity |
|---|---|---|
| ![edge movement vs Cy5 actin — scatter coloured by movement class with regression + r/R²/p](docs/screenshots/edge_piezo.png) | ![per-sector sampling rectangles on the cell boundary, centres coloured by actin intensity](docs/screenshots/edge_sampling_rectangles.png) | ![the cell boundary this frame coloured by per-sector Cy5 intensity](docs/screenshots/edge_this_frame_intensity.png) |

![channel alignment & FOV pre-analysis (real WT control) — align the actin (Cy5) channel to DIC and define the field of view inside the black border; non-destructive](docs/screenshots/prep_align_fov.png)

![divisions overlay — parent→daughter links inferred from the masks (cell 8 → cell 11), drawn as an open circle (parent) joined to a diamond (daughter) on a real WT cell](docs/screenshots/division_links.png)

![cell–cell contact — two real WT cells coloured by contact class (red = extensive) with the shared-membrane interface drawn where they touch](docs/screenshots/contacts.png)

![the unified Config ▸ Settings window — the Comparison-analysis tab toggles which heavier families (contacts / state-segmented / solidity) the comparison computes; sibling tabs hold the cell-plot metrics and the pixel/time scale](docs/screenshots/settings.png)

![the Comparison window — a metric across conditions (recording = unit), arm-aware box plots + filters + per-contrast stats table](docs/screenshots/comparison.png)

![the Stats-tab Ranked report — every group pair for the current metric, ranked by the likelihood of a significant difference (Mann–Whitney U + Cohen's d + Bonferroni); synthetic data](docs/screenshots/ranked_report.png)

![the Comparison window Histogram tab — per-cell distribution by group, units on the axis](docs/screenshots/comparison_histogram.png)

![the Comparison window Direction-autocorrelation tab — DiPer directional-persistence decay curves per condition (recording = unit)](docs/screenshots/comparison_autocorr.png)

![the per-graph plot-style options (Style… / shift-right-click)](docs/screenshots/comparison_style.png)

![the cell / recording filters (Filters…)](docs/screenshots/comparison_filters.png)

![multivariate phenotype test — PERMANOVA + leave-one-recording-out AUC per arm](docs/screenshots/comparison_multivariate.png)

![the Groups & Comparisons editor — assign recordings to groups, include/exclude, pick controls + vehicle](docs/screenshots/groups_editor.png)

*(The single-recording / per-cell panels — overview, cell inspection, population,
shape modes, edge dynamics, alignment, divisions, **cell contacts**, **settings** —
use a **WT-control** recording from the study (baseline only, no treatment-comparison
data). The cross-condition Comparison-window screenshots — including the **ranked
report** — use synthetic data.)*

## Environment

```bash
conda env create -f environment.yml      # python, numpy, scipy, pandas, sklearn,
conda activate cellscope_analysis        # tifffile, pyqtgraph, PyQt5, matplotlib, pytest
```

## Quick start

```bash
python scripts/make_sample_data.py        # (optional) write the synthetic sample
python main_viewer.py                      # discovers from config.json, else the sample
python main_viewer.py --data-root /path/to/results/by_condition
python main_viewer.py --recording R.ome.tif --masks R/pipeline_results/masks.npz
```

In the GUI: pick a recording + channel, scrub frames (slider or **←/→**, Space =
play), toggle masks/overlays, set **Colour by** a metric, and click a cell to
inspect it. Heavier analyses (Population, Shape Modes, Cell Table) have a
**Compute** button; these run **off the GUI thread** with a **progress bar + ETA
in the bottom status bar** (the Comparison window shows the same), so the window
stays responsive and you can see how long a pass will take.

## Self-drive (headless remote control)

For automated testing / agent workflows, set `MASKVIEWER_REMOTE=<port>` to expose
a localhost HTTP API that drives the GUI on its own thread:

```bash
MASKVIEWER_REMOTE=8765 python main_viewer.py
curl 'http://127.0.0.1:8765/state'
curl 'http://127.0.0.1:8765/set?recording=0&frame=5&color_by=area'
curl 'http://127.0.0.1:8765/cmd?action=compute_population'
curl 'http://127.0.0.1:8765/screenshot?path=/tmp/v.png&what=window'
```

GUI changes can also be verified headless with `QT_QPA_PLATFORM=offscreen` (see
`SESSION_LOG.md`). File ▸ **Save View Image / Save Window Screenshot** grab PNGs.

## Pointing at your data

Real data is **not** stored in this repo. The quickest way in is **File ▸ Open
Project Folder** — point it at a folder of recording folders and it loads them as
a project, auto-deriving the experimental design (arms / controls / vehicle /
colours) from the condition names. **Save Project As** writes a small JSON you can
reopen (or pick from **Recent Projects**); **Open Project File** loads it back.

For the default launch set, copy the config template and edit:

```bash
cp config.example.json config.json     # gitignored
# "data_roots": [".../cellscope/ic295_analysis/by_condition"]
```

Each root is scanned for recording folders (`*.ome.tif` + `pipeline_results/masks.npz`);
the immediate sub-folder name is used as the **condition**. The bundled synthetic
`sample_data/` is always available as a fallback.

## Data formats

| | format |
|---|---|
| Recording | `*.ome.tif`, `(T, C, H, W)` uint16 + `*.ome.json` (`um_per_px`, `time_interval_min`, `channel_names`) |
| Masks | `masks.npz`, key `labels`, `(T, H, W)` int32 — `0`=bg, positive IDs track-consistent |

The **mask label stack is the single analysis input** — every metric (shape, motion,
edge, state, **lineage / divisions**) is computed from it *in this project*. Pre-cleaning
pipeline artifacts (e.g. `divisions.json`) are not read, so IDs/edits made before the
masks were finalised never leak into a result.

**What the data is + how masks were made** — see [`docs/DATA.md`](docs/DATA.md).

## Analysis package

Pure, GUI-free, testable functions in `maskviewer/analysis/` — morphometry
(`cell_metrics`), motion (`motion`), state (`state`), nearest-neighbour
(`neighbors`), edge dynamics (`edge_dynamics`), edge-movement↔fluorescence
(`edge_intensity`), shape modes (`shape_modes`), membrane quality (`membrane`),
channel alignment (`registration`) + field-of-view (`fov`), population
(`population`), lineage (`lineage`), CSV export (`exporters`), and metric docs
(`metric_docs`). See **INTERFACE.md** for the full map.

## Tests

```bash
python -m pytest -q       # in the cellscope_analysis env
```

## License

MIT (see LICENSE).
