# cellscope_analysis — Session Log

Chronological log of substantive changes. Append an entry for any non-trivial
change. Most recent first.

---

## 2026-06-18 — Portable project files (data_roots relative to the project file)

**Request / why.** Reviewed whether a cellscope_analysis project save affects the
original cellscope project (it doesn't — we write one JSON, read everything else;
cellscope uses `*.cellscope` per-recording files, never scans for generic `*.json`,
and `ic293_analysis/*` is gitignored there so our file is invisible to its git). The
one portability gap: saved `data_roots` were **absolute**, so a project broke when
the data moved / a share mounted at a different path on another machine.

**Fix (`project.py`).**
- `save_project` stores each data root **relative to the project file's directory**
  (`_relpath_to`) — a project written into the data folder gets `"data_roots": ["."]`.
  Falls back to absolute when no relative path exists (different Windows drive).
- `load_project` resolves stored roots against the file's dir (`_resolve_root`);
  **absolute/legacy roots load as-is**, and in-memory roots are always absolute. So a
  re-save converts legacy absolute → relative automatically.
- Converted the live `…/ic293_analysis/ic293.json` to the portable form
  (`data_roots: ["."]`, exclusion preserved) by load+save; verified it reloads,
  resolves to the absolute path, includes 77, excludes `Pos36_div-GOF`.

**Tests.** `tests/test_portable_project.py` (4): saved-relative-to-file, **move the
whole tree → still discovers the recording**, legacy-absolute backward compat,
re-save relativises a legacy absolute file. Full suite **191 passed**.

---

## 2026-06-18 — Wire include/exclude to the Comparison Groups editor + Save Project

**Request.** Wire the new Include/Exclude dialog together with the Comparison
window's Groups editor (they edit the same `Project.excluded`); make the
include/exclude choices saveable to the loaded project file (e.g. `ic293.json`).

**Two-way sync.**
- `CompareWindow` gains `inclusionChanged = pyqtSignal(object)`, emitted from
  `_on_design_changed` (which already fires on every Groups-editor include/group
  edit). The main viewer connects it (in `open_compare_window`) to
  `inclusion.apply_inclusion(self, exc, notify_compare=False)` — so excluding in the
  Groups editor **removes the recording from the main session dropdown** too.
- The reverse: `apply_inclusion(..., notify_compare=True)` (the default, used by the
  File-menu dialog) refreshes the open Groups editor's table (`set_data`) + replots
  (`_on_design_changed`). The `notify_compare` flag prevents an echo loop (the
  Groups-editor-originated path passes False).

**Save.**
- `window_actions.save_project_as(path=None)` now takes an optional path: with one it
  saves straight there (no prompt), else it prompts. New **File ▸ Save Project**
  (Ctrl+S) calls it with `project.path` → writes the loaded file (e.g. `ic293.json`);
  **Save Project As…** still prompts. `Project.excluded` was already serialized by
  `save_project`, so exclusions persist.

**Sizes.** Kept under 500: trimmed the `_on_design_changed` refactor (compare_window
499); the reverse-sync lives in `inclusion.py`; Save Project is wired via a menu
lambda (window_actions 499).

**Tested.** `tests/test_inclusion.py` +3 (Groups-editor→session, main→Groups-editor,
save-to-path round-trips `excluded`). GUI test-driven on the real `ic293.json`:
exclude in Groups editor → session 77→76; re-include from the main side → Groups
checkbox re-ticks; Save Project → temp file reload shows `excluded=[Pos36_div-GOF]`;
**user's `ic293.json` left untouched**. Full suite **187 passed**.

---

## 2026-06-18 — Include / Exclude Recordings dialog (session-aware)

**Request.** A menu item acting on the loaded project: two lists (included /
excluded) with the ability to move recordings between them; changing status
loads/removes the recording from the session.

**Changes.**
- New `gui/inclusion.py`: `IncludeExcludeDialog` (dual-list transfer widget — arrows,
  double-click, multi-select; OK disabled when nothing included) + free functions
  `manage_inclusion(win)` (opens it from the menu) and `apply_inclusion(win, excluded)`.
- The **session** (recording dropdown) is now the **included** subset: `ViewerWindow`
  `__init__` + `set_project` set `self.entries = project.included_entries()`, and
  `_add_recording_entry` appends to `project.entries` (canonical) then rebuilds the
  session. So loading a project with a pre-set `excluded` (e.g. `ic293.json`'s
  `Pos36_div-GOF`) hides it from the dropdown on open.
- `apply_inclusion` sets `Project.excluded`, rebuilds the dropdown, **keeps the current
  recording without reloading** if still included, else **hands off to the first
  included** recording (loads it). Same `excluded` set the Comparison window's Groups
  editor uses — saved with the project, non-destructive.
- Menu: File ▸ **Include / Exclude Recordings…** (`menus.py` → `inclusion.manage_inclusion`).
- Kept `gui/inclusion.py` separate (free functions, not window methods) so
  `viewer_window.py` (499) and `window_actions.py` (493) stay under 500 lines.

**Test-drive (offscreen, real IC293 `ic293.json`).** Load → dropdown 77, div-cell
hidden but present in `project.entries`; menu action present; dialog partitions 77/1;
re-include → 78 + the div recording loads pixels+masks; exclude the on-screen
recording → 77 and the session hands off to an included recording. Plus
`tests/test_inclusion.py` (6): dialog partition/move, OK-gating, preset-excluded
hidden on load, keep-current, load-on-exclude-current, re-include. Full suite **184
passed**.

---

## 2026-06-18 — Drag-and-drop opening (folders / project .json / recordings)

**Request.** Drag folders and/or files onto the GUI window to open them.

**Changes.**
- `viewer_window.py`: `self.setAcceptDrops(True)` (offset by compacting the adjacent
  `resize(...)` so the file stays at 499 lines).
- `window_actions.py` (`WindowActionsMixin`, already a ViewerWindow base — so no new
  import/base in viewer_window): `dragEnterEvent` / `dragMoveEvent` / `dropEvent` →
  `open_paths(paths)`, which dispatches by kind: a project **`.json`** → load it
  (`_open_project_path`), **folder(s)** → open as a project via
  `projmod.from_data_roots` (recordings discovered under them; the new `_`/`.` prune
  keeps `_cache/` out), recording **`.ome.tif`/`.tif`** files → appended to the list
  (`_add_recording_entry` + `_sibling_masks` auto-detects `pipeline_results/masks.npz`).
  Empty/unknown drops warn instead of crashing. Refactored `open_recording_dialog` /
  `open_project_file` to share `_sibling_masks` / `_add_recording_entry` /
  `_open_project_path`. Drops on any non-drop-accepting child (canvas, docks)
  propagate to the window, so the whole window is a drop target.
- Status-bar feedback on each drop (n recordings / folders / "ignored others").

**Tests.** `tests/test_drag_drop.py` (5) — folder→project, recording-file→entry,
.json→project, empty-folder→warn (no crash), and dragEnter accept/ignore gating
(via a tiny fake event — constructing a real `QDragEnterEvent` segfaults under the
offscreen platform). Windows isolate `_settings` to a temp ini so `_remember_project`
never touches the real prefs. Full suite **178 passed**; real QSettings verified
untouched.

---

## 2026-06-18 — Fix: discovery loaded `_cache/` as a bogus "_cache" recording

**Report.** Opening the *whole* results folder (`…/ic293_analysis`) instead of its
`by_condition/` subtree loaded an extra recording called **`_cache`**.

**Cause.** A CellScope results root keeps its machinery in underscore-prefixed
siblings of `by_condition/` — chiefly **`_cache/`**, a flat dump of every converted
`*.ome.tif` (with *no* per-recording `pipeline_results/masks.npz`). `discover()`
walked into `_cache/`, found `*.ome.tif`s, and registered the folder itself as one
Entry labelled `_cache`.

**Fix.** `io/dataset.py::discover` now prunes any directory whose name starts with
`_` or `.` from the `os.walk` (so `_cache`, `_runs`, `_source_metadata`, hidden
dirs are never walked or mistaken for a recording). The selected root itself is
always scanned, so explicitly pointing at such a folder still works. Verified on
the real IC293 tree: discovering `…/ic293_analysis` now yields the **same 78**
recordings as `…/by_condition` (all 6 conditions, all with masks), no `_cache`.

**Test.** `tests/test_io.py::test_discover_skips_internal_underscore_folders` builds
a root with a real `by_condition/WT/Pos0-WT` recording beside `_cache/` (3 maskless
tifs), `_runs/`, and a hidden `.thumbs/`, and asserts only `Pos0-WT` is found. Full
suite **173 passed**.

---

## 2026-06-18 — Startup settings: blank-slate default + demo/config-roots toggles

**Request.** Add a GUI option to control whether the demo loads at startup (default
off), and make it possible to start from a blank slate (no files auto-loaded — the
IC295 results were loading because `config.json` points at them *and* `load_config`
always appended the demo).

**Changes.**
- `config.py`: `load_config(path, include_sample=True)` — the demo append is now a
  flag (default True for analysis scripts). New pure `startup_roots(load_config_roots,
  load_demo, config_path=None)` → the roots to scan on launch (both off → `[]`, a
  blank slate). GUI-free, tested.
- `main_viewer.py`: refactored to `_resolve(args)` → `(entries, roots, name, explicit)`.
  Explicit data CLI args (`--recording`/`--data-root`/`--config`) win as before; with
  **no** data args it reads QSettings `startup/load_config_roots` + `startup/load_demo`
  (**both default off**) via `startup_roots`. App is created before resolving so the
  toggles can be read. A no-args launch with both off opens an **empty window** (no
  longer exits with "No recordings"); an *explicit* CLI request that finds nothing still
  errors (exit 2).
- `config_window.py`: new **Startup** tab (first tab) with the two checkboxes (persist
  to QSettings; changes apply at next launch; tooltip shows the current config.json
  roots).
- Verified the empty `ViewerWindow` comes up clean (recording/masks None, empty
  recording combo) and is driven via File ▸ Open Project Folder / Recent Projects.

**To load a new dataset (e.g. IC293):** File ▸ Open Project Folder →
`…/cellscope/ic293_analysis/by_condition` (auto-design recognises the WT/GOF/KO +
DMSO/Y1/OT arms). Or tick **Load data from config.json** after pointing config.json
at it, or `python main_viewer.py --data-root …/ic293_analysis/by_condition`.

**Tests.** `tests/test_startup.py` (5) — the four toggle combinations + the
`include_sample` flag. Full suite **172 passed**. (A manual smoke briefly wrote
`startup/load_demo=True` to the real QSettings via `ConfigWindow`'s own settings store;
reset to default afterwards.)

---

## 2026-06-16 — Fix: edge precompute fired automatically (+ tests polluted QSettings)

**Report.** Edge-dynamics precompute seemed to run on switching to the Cell Info
tab, before pressing the button. **Two causes:**

1. **Tests polluted the real QSettings.** `tests/test_cell_info_precompute.py`
   constructed `CellInfoPanel` without isolating `_settings`, so
   `set_auto_precompute(True)` / `set_metric_enabled(...)` wrote the *developer's*
   `cellscope_analysis/viewer` settings — leaving **`cell_info/auto_precompute =
   True`**. With auto on, `set_context` (fired on load **and** on the first cell
   click, which auto-raises the Cell Info tab) ran the precompute.
2. **Auto-precompute also did the heavy edge pass.** Once auto fired, it chained
   the Edge-dynamics precompute — surprising + heavy.

**Fixes.**
- `precompute_all(chain=False)`: only the explicit **Precompute all cells** button
  (`clicked → precompute_all(chain=True)`) chains the edge precompute via
  `after_precompute`; **auto-precompute stays Cell-Info-only** (lightweight). Auto
  toggle tooltip updated to say so.
- **Tests isolate settings**: `_panel(tmp_path)` points `_settings` at a temp ini —
  verified the full suite leaves the real `cell_info/auto_precompute` /
  `cell_metrics_enabled` keys untouched. Reset both polluted keys to default on this
  machine.

Tests: `test_button_precompute_chains_edge` (button → chain) +
`test_auto_precompute_does_not_chain_edge` (auto → no chain). Full suite 167 passed;
ViewerWindow smoke confirms auto-off cell click does **not** all-cells-precompute,
while the button warms the edge cache.

## 2026-06-16 — Edge dynamics: per-cell cache + folded into "Precompute all cells"

Follow-up so the Edge tab is fast too (when it's the front tab, switching cells
previously still recomputed). `EdgePanel` now **caches** each cell's computed
state keyed by (cell_id, fluor channel) — `_compute_snapshot` builds a pure dict
(no self-mutation, no Qt → safe off-thread), `_ensure_computed` restores from the
cache or computes+caches, `_apply_snapshot` pushes it to the widgets. Revisiting a
cell (same fluor) is instant; the cache drops on recording change (`set_context`)
and survives deselect (`clear_cell` keeps it). A fluor change recomputes only the
fluorescence part (kymographs are fluor-independent) and re-caches.

**Folded into precompute.** `EdgePanel.precompute_all` (now an `AsyncComputeMixin`)
computes+caches every cell off-thread; the Cell-Info "Precompute all cells" pass
**chains** it via `cell_info.after_precompute` → `ViewerWindow._precompute_edge`
(sets the edge context + precomputes). So one button warms both caches; switching
cells on the Edge tab is then instant. Viewer wires `edge` into the `run_async`
panels. (`window_actions._precompute_edge` keeps `viewer_window` < 500.)

Tests: `tests/test_edge_panel_lazy.py` (+revisit cache hit, precompute caches every
cell, new recording clears cache), `tests/test_cell_info_precompute.py` (+after_precompute
chain hook). Full suite 166 passed; a headless ViewerWindow smoke confirms the
button warms both caches and the Edge switch is a cache hit.

## 2026-06-16 — Fix slow cell switching: edge dynamics now computes lazily

**Report.** After precomputing Cell Info, switching cells was *still* slow.
**Root cause (not Cell Info):** `select_cell` calls `edge.set_cell` on every
click, which eagerly computes the velocity/radius/curvature kymographs + the
fluorescence rectangle sampling — **even though the right-hand docks are tabbed,
so the Edge dock is hidden when the user is on the Cell Info tab** (and
`select_cell` even raises Cell Info to the front). Measured ~1.5 s/cell on a
1024²×30 synthetic (≈19× the ~80 ms Cell-Info cost); far worse on the real
2048²×97 data. The Cell-Info cache was working; the edge compute was the freeze.

**Fix (`gui/panels/edge_panel.py`).** The heavy per-cell compute is now **lazy**:
`set_cell` stores the request (`_pending`) and only computes when the dock is the
visible tab — visibility tracked via `showEvent`/`hideEvent` (which fire on tab
switches; `isVisible()` is unreliable under the offscreen platform). `showEvent`
computes the pending cell. So clicking cells while on the Cell Info tab no longer
pays for edge dynamics → instant (with the Cell-Info cache). `_on_fluor` and
`clear_cell` respect the same gating. To stay < 500 lines, the panel's view layer
(`_replot` + all `_draw_*` + `_export`) was split into
**`gui/panels/edge_render.py` `EdgeRenderMixin`** (mixed into `EdgePanel`); both
files are now ~270 lines.

**Tests.** `tests/test_edge_panel_lazy.py` — defers while hidden, computes on
show, re-defers after hide, `clear_cell` resets, and every render mode draws after
the split. Full suite 162 passed; a headless ViewerWindow smoke confirms
click-while-hidden defers and showing the Edge tab computes.

## 2026-06-16 — Cell Info: auto-precompute-on-load toggle (Config)

Follow-up to the precompute feature: a **Config ▸ Cell plot metrics** checkbox
"Auto-precompute all cells when a recording loads" (QSettings
`cell_info/auto_precompute`, **default off**). The panel owns the flag
(`set_auto_precompute`, read in `__init__`); `set_context` auto-runs
`precompute_all` when the recording genuinely changes and the toggle is on (so it
fires once per load, not per cell click). Enabling the toggle precomputes the
current recording immediately. Tests extended (`test_cell_info_precompute.py`):
auto-runs when enabled, doesn't when off (default), and the setter precomputes the
loaded recording. Full suite 157 passed; headless ConfigWindow smoke confirms the
checkbox (default off → toggling on precomputes).

## 2026-06-16 — Cell Info: precompute all cells (instant switching)

**Why.** Switching cells in the Cell Info dock recomputed that cell's whole
per-frame table from the full label stack each time (`cell_frame_table` scans
`labels[t]==cid` over every frame), so comparing cells by clicking between them
lagged.

**Change (`gui/panels/cell_info.py`).** `CellInfoPanel` now memoises each cell's
result (`_cache`, keyed by recording + enabled-metric set via `_cache_key`) — so
revisiting a cell is an instant lookup — and adds a **Precompute all cells**
button (`precompute_all`) that computes every cell up front **off the GUI thread**
(`AsyncComputeMixin` / the window's `run_task`, with the status-bar progress +
ETA) and shows a "✓ N cells cached" status. The cache self-invalidates when the
recording or the enabled metrics change; `clear_cell` (deselect) keeps it so a
misclick doesn't discard a precompute. New `set_context(labels, …)` primes the
panel from the loaded recording so precompute works before any cell is clicked
(wired in `viewer_window._load_entry`; `cell_info` added to the `run_async`
panels). Compacted two `viewer_window` lines to stay < 500.

**Tests.** `tests/test_cell_info_precompute.py` (offscreen) — precompute caches
all cells, a subsequent switch is a same-object cache hit, and the cache drops on
metric / recording change; plain `set_cell` memoises without precompute. Full
suite 154 passed; headless ViewerWindow smoke confirms the button end-to-end.

## 2026-06-16 — Load raw multi-position Micro-Manager OME-TIFFs directly

**Why.** Deploying the IC295 project to another machine: the masks are tiny
(~0.5 GB) but the recordings (~55 GB) already live on the pathaklab share — as
**raw multi-position Micro-Manager OME-TIFFs**. Each physical
`IC295__1_MMStack_<pos>.ome.tif` holds one stage position's pixels (291 pages =
97 T × 3 C), yet its embedded OME-XML describes the *whole* 72-position
acquisition, so `tifffile` reports a phantom `(72, 97, 3, 2048, 2048)` `RTCYX`
stack the loader rejected (ndim 5). The clean single-position `_cache` copies the
viewer used were made by `ic295_copy_from_lab.py` (byte copy + synthesized
`.ome.json`) → `recompress_recordings.py` (lossless re-compress that rewrites
single-position OME metadata).

**Change (`maskviewer/io/recording.py`).** `load_recording` now opens via
`TiffFile`, and when the series looks multi-position (`_looks_multiposition`: a
position/scene axis or >4 dims) calls `_read_single_position` — reads only the
file's *own* pages (one position; sibling files never opened) and reshapes via
the pure, tested `planes_to_tcyx(planes, C, T, Z, c_fast)`. Dimensions come from
the reliable series axes/shape (`C`/`T`/`Z`); the later of C/T in numpy axis order
is the faster-varying plane axis (MM is C-fast); MM `Summary.Channels` is the
channel fallback. Single-position files keep the existing fast path. Verified
**bit-identical** to the validated `_cache` copy for a real recording.

**Deploy (`scripts/deploy_ic295_masks.py`).** Builds a viewer-discoverable
`by_condition/<cond>/<label>/` tree at a destination: copies masks + provenance +
sidecars (~0.5 GB) and a **relative** symlink to each recording already on the
share (recordings not copied — read in place). Relative links → the tree resolves
on any machine that mounts the share. Writes a ready `config.json`. Read-only on
sources; idempotent + `--dry-run`.

**Tests.** `tests/test_multiposition.py` — the C-fast / T-fast reshape, T-inference,
the one-file-many-positions guard, and `_looks_multiposition` (pure; no real data).
Existing IO tests still pass (single-position path unchanged).

## 2026-06-16 — Docs + in-app help sync

Audited every doc / help surface against the recent features (state/shape params,
audit fixes, edge curvature, rectangle positioning, track-length metric, mask source).
CLAUDE.md + INTERFACE.md were already current (those PRs updated them). Gaps found +
fixed:

- **Help ▸ Metrics Reference + tooltips** (`metric_docs`): added `curvature` (edge
  summaries) and `track_length` doc entries — previously the `track_length_min` /
  curvature comparison/edge tooltips fell back to a bare label with no what/how. Now
  they render in the Metrics Reference dialog and as comparison-column tooltips.
- **README.md**: mask-source added to the colour-by list; curvature/radius kymographs
  + the rectangle-positioning option added to the membrane-dynamics section.
- **docs/DATA.md**: noted that `masks_precleanup.npz` / `masks_original.npz` carry the
  per-pixel `fusion_source_stack` (1=DIC, 2=Cy5, 3=both) now surfaced as the mask-source
  colour-by.

(FINDINGS_followup.md has no shape-mode/curvature content, so the shape-mode rotation
fix needs no caveat there.) `pytest` **145 passed**; Help/tooltip render smoke green;
all files < 500.

---

## 2026-06-16 — Colour masks by detection source (DIC / Cy5 / both)

Added a **Mask source** colour-by. The detection pipeline records a per-pixel
`fusion_source_stack` (uint8: 0 bg / 1 DIC-only / 2 Cy5-only / 3 both — the DIC↔Cy5
detection fusion). The final `masks.npz` drops it, so `io/masks.load_masks` now also
locates it in the loaded npz **or a sibling pre-cleaning artifact**
(`masks_precleanup.npz` / `masks_original.npz`) and exposes `Masks.source_stack()`
(lazy) + `Masks.cell_sources()` (`{cell_id: code}` by majority pixel vote over the track,
matching the pipeline's per-track `fusion_source`). `colorby` gained a categorical
**source** mode (red=DIC, yellow=Cy5, lime=both), added to the Display colour-by combo
with an explanatory tooltip. It's **display/QC only** — read from a pre-cleaning artifact
purely for provenance, never fed into analysis — and degrades gracefully (default
colouring) for single-channel / unfused recordings with no source data.

Verified on real IC295 data (a recording resolved to {both:6, DIC:3, Cy5:1}) and the
synthetic sample (no source → graceful fallback). `viewer_window` kept at 499 lines
(field folded in, lazy cache done inline in `colorby`). Tests +4
(`tests/test_mask_source.py`); `pytest` **145 passed**; all files < 500.

---

## 2026-06-16 — Edge curvature, rectangle positioning, track-length metric

Three user-requested viewer/analysis additions:

- **Edge curvature** (`edge_dynamics.curvature_kymograph`) — per-sector boundary
  curvature κ from the polar boundary `r(θ)` (`(r²+2r'²−r·r'')/(r²+r'²)^1.5`, circular
  finite differences), in 1/µm; +convex / −concave. Verified: a disk gives κ≈1/R, an
  ellipse spikes at the tips. Added to the **Edge Dynamics** dock as a *Curvature
  kymograph* + *Edge this frame: curvature* view (diverging colour, red convex / blue
  concave), a mean-κ + mean-|κ| line in the summary, and a CSV export tag.
- **Sampling-rectangle positioning** (from the original `cell_edge_analysis` step6) —
  `edge_intensity.rectangle_intensity` gained a `rotation` mode (`none` / `flip` /
  `search` over `RECT_SEARCH_ANGLES`): when the straight inward rectangle falls below
  `min_coverage` (concave edge / image border) it rotates to recover the best in-cell
  coverage (verified: on a crescent cell at coverage 0.8, valid sectors 57→61→65 for
  none→flip→search; no change on a convex cell). Exposed as a **categorical** analysis
  parameter (`ANALYSIS_CHOICES`, a combo) + a numeric search-angles spinbox.
- **Track length for plotting** — already existed for **colouring** (Display ▸ Colour
  by ▸ "Track length") and as a comparison metric (`frames_tracked`) + the cell-info
  summary; added `track_length_min` (track *duration*) to `per_cell_table` so both
  frames and minutes are selectable comparison metrics (auto-labeled "track length
  (frames|min)").

Infra: the Config window's option/parameter definitions moved to a new
`gui/analysis_params.py` (COMPARE_OPTIONS / ANALYSIS_PARAMS / **ANALYSIS_CHOICES** +
`compare_options` / `analysis_params` / `analysis_choices` / `apply_analysis_params` /
`analysis_params_tag`), re-exported from `compare_tables` for back-compat — keeps
`compare_tables` under 500 (now 355). The params tab renders numeric spinboxes **and**
categorical combos grouped by section. The rotation choice folds into the comparison
cache key. Tests +6 (`tests/test_edge_features.py`); `pytest` **141 passed**; GUI smoke
(all 10 edge views + the rotation combo) green; all files < 500.

---

## 2026-06-16 — Fix the remaining audit items (no longer just documented)

Turned every low-severity audit finding into an actual fix:

- **`motion.instantaneous_speed` + `cell_metrics` per-frame speed series** — per-step
  speed now divides by the **actual elapsed frames** (`Δframe·dt`) when a time scale is
  given, so a step bridging a tracking gap is no longer over-stated. Without `dt` the
  raw bridged length is still returned (what `jump_steps` keys on). Gapless tracks
  unchanged.
- **`contacts.contact_episodes`** — a tracking gap no longer **splits** one sustained
  contact into multiple "events" (it broke a run on any frame gap); only a present-but-
  free frame breaks a run. Stops inflating `n_contact_events`/`contact_event_rate`.
- **`contacts._boundary_mask`** — image-border pixels of a cell now count as boundary
  (previously a cell flush against the frame edge under-counted `boundary_px`, inflating
  its `contact_fraction`).
- **`cil.contact_locomotion`** — a contact `onset` now requires the cell to have been
  **present-but-free** the previous frame, so re-appearing after a tracking gap no
  longer counts as a new formation (`n_contact_onsets` was inflated).
- **`edge_dynamics`** — `mean_protrusion_velocity` / `mean_retraction_velocity` return
  **NaN** (not 0.0) when a cell has no protrusion/retraction events, so a never-
  protruding cell is excluded from (not dragging down) cross-recording means.
  `edge_velocity_kymograph(smooth=True)` no longer **fabricates** velocity in sectors
  that had no edge pixel in a frame (they're masked back to NaN), and the temporal
  smoothing is now a NaN-aware normalized convolution (`_nan_gaussian1d`) so a missing
  sector doesn't blank its whole time column.
- **`edge_intensity`** — `lagged_intensity_correlation` takes the present-frame indices
  so the lag counts **real frames**, not matrix rows (correct across gaps; falls back to
  rows when not given). `movement_intensity_pairs` fences a velmat/intmat length
  mismatch.
- **`multivariate`** — PERMANOVA returns `(nan, nan)` for degenerate group counts
  (< 2 groups, no within-df, or zero within-group dispersion) instead of dividing by
  zero; `loadings` now uses the **n-weighted pooled SD** (matches `compare.cohens_d`).
- **`stats_extra.bootstrap_ci`** — returns NaN bounds when > 50 % of resamples are
  degenerate (e.g. zero-variance groups), instead of taking percentiles of a tiny
  surviving subset.
- **`cell_metrics._region_shape`** — degenerate regions (< 3 px) return 0 axes /
  eccentricity (skimage's convention) rather than the +1/12-inflated values.
- **`interactions._cell_summ`** — guards a ragged legacy-cache length mismatch.

Tests +7 in `tests/test_audit_fixes.py` (speed-across-gap, border-boundary, edge_summary
NaN, PERMANOVA degenerate, loadings = cohens_d, bootstrap_ci degenerate, lagged frame-
path) + updated `test_contacts` for the corrected gap-handling. `pytest` **135 passed**;
GUI + analysis smoke green; all files < 500 (cell_metrics 499).

---

## 2026-06-16 — Deep-dive correctness audit: 6 calculation bugs fixed

Test-drove the whole GUI headless (all 17 colour-by modes, every cell-info plot
metric, MSD/autocorr, population, shape, edge+fluorescence, config, CSV, comparison
build — all green) and ran a 5-front correctness audit of the analysis math. The GUI
surface had **no runtime bugs**; the audit found and we fixed **6 calculation bugs**
(+ doc/consistency fixes):

1. **`motion.turning_angles` (HIGH)** — a paused cell (zero-length step) got
   `arctan2(0,0)=0` (phantom "due-east"), so a straight-but-paused track produced two
   fake ~90° turns and `run_and_tumble` reported it as **fully tumbling**. Now joints
   adjacent to a zero-length step return NaN (mirrors the guard
   `direction_autocorrelation` already had); `run_and_tumble` is NaN-aware.
2. **`shape_modes.contour_signature` (HIGH)** — the orientation-roll didn't actually
   remove rotation (inertia-orientation is mod-π and in a different angular frame than
   the binning), so VAMPIRE "shape modes" largely encoded **cell orientation, not
   shape** (a fixed shape rotating scattered across all modes). Replaced with a
   2nd-Fourier-harmonic alignment computed *in the binning frame* + a 180°-flip
   canonicalization. Rotation RMS of the signature: **0.43 → 0.017**; rotated copies of
   one shape now collapse together and round-vs-elongated separate regardless of angle.
3. **`compare.ranked_group_comparisons` (MED)** — guard `not (ptp(a)==0 and ptp(b)==0)`
   discarded a *valid, maximally-significant* comparison when both groups were
   internally constant but different (e.g. WT=[5,5,5] vs KO=[9,9,9] → p=0.047 in the
   main Stats table but NaN in the Ranked report). Now skips only the all-tied case
   (`ptp(pooled)==0`).
4. **`cell_metrics`→`state.classify_state` (MED)** — `circularity` was computed but
   never passed, so the no-scale fallback was dead code and scale-less recordings
   classified **every** cell `unknown`. Passed at both call sites (verified: a disk with
   no µm/px now classifies `rounded`).
5. **`contacts._aggregate` (LOW-MED)** — `contact_fraction`/`contact_length` counted
   boundary pixels of sub-`min_px` partners that `n_contacts`/class dropped. Now counts
   only pixels touching a surviving partner (a no-op when all partners survive).
6. **`motion.displacement_metrics` (MED)** — `mean_speed` divided total path by step
   *count*, inflating speed across tracking gaps. Now total path ÷ elapsed *time*
   (identical for gapless tracks; flows to colour-by + the comparison's mean_speed).

Plus: `mode_contour` display angle now matches the binning frame (cosmetic); the
perimeter is correctly labelled **skimage `regionprops` perimeter (Benkrid–Crookes,
nb=4), not Crofton** (comments + module docstring + INTERFACE.md + CLAUDE.md);
`_convexity`'s curvature-dependent bias is documented (relative ruffling index); and the
`ComputeWorker` option fallbacks now match the documented "all OFF" defaults.

Audit **verified correct** (no change): MSD / α-D fit (incl. the 4D factor) / Fürth /
direction autocorrelation; edge-dynamics velocity sign + units + polarity +
rear-retraction; **all** comparison statistics (recording = unit everywhere, BH-FDR
matches scipy + monotone + ≤Bonferroni, Cohen's d pooled SD, MWU/KW guards, PERMANOVA
pseudo-F with +1 permutation p, leave-one-recording-out AUC, CR1 cluster-robust SE,
state-segmented speed-cap/edge/segment gating); nearest-neighbour; CIL sign/windowing;
moment-based eccentricity/axes/orientation/extent; membrane metrics.

Low-severity items left as documented limitations (real call sites unaffected):
per-step `instantaneous_speed` gap bridging (needed by `jump_steps` QC), contact-episode
/ CIL-onset counting across tracking gaps, edge-cell boundary undercount, degenerate
sub-`MIN_AREA` region axes, `multivariate.loadings` unweighted pooled SD, `bootstrap_ci`
degenerate-resample drop, PERMANOVA div-by-zero on degenerate group counts.

Tests +6 (`tests/test_audit_fixes.py`): pause→no-phantom-turn, rotation-invariant shape
signature + shape-not-orientation clustering, ranked-report constant-but-different
groups, no-scale state fallback. `pytest` **128 passed**; all files < 500.

---

## 2026-06-16 — Expose ALL remaining code-level constants in the Analysis-parameters tab

Followed up by surfacing the constants previously left in code. The tab now groups
**17** parameters by section (scrollable):
- **Neighbours & contact**: + **min contact size (px)** (`contacts.MIN_CONTACT_PX`).
- **State classification**: + **min cell area (px)** (`state.MIN_AREA_PX` — also gates
  shape-mode contour extraction, so its change re-fits the shape model too).
- **Motion**: **run/tumble turn angle °** + **jump-step factor** (new module constants
  `motion.RUN_TUMBLE_TURN_DEG` / `JUMP_FACTOR`; `run_and_tumble` / `jump_steps` now
  sentinel-`None` and read them).
- **Edge dynamics**: **front/rear half-cone °** (`edge_dynamics.POLARITY_FRONT_DEG`, new),
  **kymograph time σ** (`TEMPORAL_SIGMA`) + **angular window** (`ANGULAR_SG_WINDOW`) — the
  last two were already read in-body, so they just needed wiring.
- **Edge↔fluorescence sampling**: **rectangle depth/width px** + **min in-cell coverage**
  (`edge_intensity.DEPTH_PX` / `WIDTH_PX` / `MIN_COVERAGE`; `rectangle_intensity` +
  wrappers sentinel-`None`).
- **Contact inhibition (CIL)**: **speed window (frames)** (`cil.DEFAULT_WINDOW`;
  `contact_locomotion` sentinel-`None`).

Same pattern throughout: `apply_analysis_params` mutates the module globals; leaves read
them at call time; `analysis_params_tag` folds all of them into the comparison cache key.
The params tab is now wrapped in a `QScrollArea`; `_set_param` re-fits the cached shape
model for `shape_n_modes` **and** `state_min_area_px`. Tests +1 (`test_extra_params_apply`
drives every new global + checks leaf flow for motion turn angle and state min-area).
`pytest` **122 passed**; headless ConfigWindow smoke (set via spinbox + reset) green; all
files < 500 (config_window 183, compare_tables 485).

Nothing tunable now stays hard-coded except genuinely structural constants (`N_SECTORS`
kymograph resolution, `N_PCS`) — changing those mid-session would invalidate the kymograph
geometry / PCA basis, so they remain code-level.

---

## 2026-06-16 — Expose the remaining analysis parameters (state thresholds + shape count)

Follow-up on the deferred options. The **state-classification thresholds** turned out
to be a clean win — `classify_state` reads `ROUNDED_AREA_UM2` / `ROUNDED_ECC` in its
body (not as bound defaults), so mutating the module globals propagates everywhere with
no analysis-code change. Added to the **Analysis parameters** tab (now grouped by
section): **Rounded max area (µm²)**, **Rounded max eccentricity**, and the **number of
shape modes** (`shape_modes.fit_shape_modes` made to read the live `N_MODES`). All set
via `apply_analysis_params`, folded into the comparison cache key (`analysis_params_tag`)
so a change recomputes, and flow to state / frac_rounded / state-segmented metrics +
the interactive state colouring + the VAMPIRE model (the params tab clears the cached
shape model + redraws). Verified: setting rounded-area=300 flips a 500-µm² cell from
rounded→spread live. Tests +1. `pytest` **121 passed**; smoke green; all files < 500.

(Left as documented module constants — low value to tune via UI: the state min-area
floor, edge-rectangle depth/width, kymograph smoothing, contact min-pixels, and the
per-function defaults already settable as args, e.g. run-tumble turn angle.)

---

## 2026-06-16 — Options panel: grouped metrics + Analysis-parameters tab

Second half of the options audit. **Cell-plot-metrics tab** is now **grouped by
category** (Shape & state / Motion & dynamics / Neighbours & contact / Fluorescence
per channel) with headers, instead of a flat 30-checkbox grid — much easier to scan.
New **Analysis parameters** tab (`compare_tables.ANALYSIS_PARAMS`) exposes the
previously-hardcoded tunables: **neighbour radius** (µm), **contact gap tolerance**
(px) and **extensive-contact threshold**. `apply_analysis_params` writes them onto the
analysis module globals (`neighbors.DEFAULT_RADIUS_UM`, `contacts.DEFAULT_GAP_PX`,
`EXTENSIVE_FRAC`), and the affected leaf functions (`frame_nn`, `frame_contacts` /
`frame_interfaces` + the contact wrappers, `cell_frame_table`'s nn) now read those
globals **at call time** (sentinel `None` defaults) — so a change applies uniformly to
the comparison (recompute; folded into the cache key via `analysis_params_tag`) *and*
the interactive overlay / colour-by / cell-info (the viewer clears its contact memo +
redraws). Applied at viewer startup so saved values take effect. Tests +1. `pytest`
**120 passed**; smoke green; all files < 500 (`compare_window` 498).

---

## 2026-06-16 — Comparison completeness: everything in the main GUI is now comparable

Audit found three main-GUI metric families that never reached the comparison. Closed:
- **Fluorescence intensity + membrane** (new `analysis/intensity_metrics.py`,
  `per_cell_fluor`): per-cell track-mean **intensity** + **membrane_score** /
  **boundary_grad** / **membrane_contrast** for *every channel* → compare SiR-actin /
  tagged-PIEZO1 levels + cortical enrichment across conditions. New
  **Fluorescence intensity + membrane** analysis toggle.
- **Shape-mode usage** (`shape_modes.per_cell_shape_summary`): per-cell
  `dominant_shape_mode` / `n_shape_modes` / `shape_mode_entropy` /
  `shape_mode_switch_rate` from the (disk-cached) VAMPIRE model. New **Shape-mode
  usage** toggle.
- **convexity** added to the per-cell aggregates (it was computed per-frame but never
  aggregated).
Both new families default OFF (gated like the others); `metric_docs` covers them
(intensity/membrane via the existing per-channel PREFIX docs). Tests +2. `pytest`
**119 passed**; all files < 500 (compare 489).

---

## 2026-06-16 — Minimal/fast defaults: heavy analysis is now opt-in

Set the GUI's analysis defaults to a fast **basic** state so a fresh session stays
responsive on large stacks; the advanced analyses are opt-in via Config ▸ Settings.
- **Cell-Info metrics** now default to a cheap subset (`cell_metrics.DEFAULT_PLOT_METRICS`:
  area, eccentricity, aspect ratio, extent, state, speed, displacement, turning) — all
  from the moment pass / centroid track. The costly ones (perimeter / circularity /
  convexity, solidity, per-channel intensity & membrane, nearest-neighbour, contacts,
  shape mode) are **off until enabled**, so a cell click no longer triggers convex
  hulls / per-channel sampling / a contact KD-tree per frame. `cell_info` switched from
  a persisted *disabled*-set to an *enabled*-set (`cell_metrics_enabled`), defaulting to
  the minimal set on first run (a one-time reset to fast).
- **Comparison-analysis toggles** now **all default OFF** (`COMPARE_OPTIONS`: contacts +
  state-segmented were on → off; solidity / edge / CIL already off). A basic comparison
  (shape + motion + NN + MSD + direction autocorrelation) computes fast; the user
  enables contacts / state-segmented / solidity / edge / CIL as needed.
- **Population** table defaults `with_solidity=False` + `with_contacts=False` (the
  per-cell-frame convex hull + KD-tree) so the population overview computes fast.

`pytest` **117 passed**; smoke green; all files < 500. Verified (isolated QSettings):
fresh defaults are all-minimal; opt-in toggles persist + recompute.

---

## 2026-06-15 — PR8: cell-level QC flags (exclude individual cells)

Final of the 8-part program. The project had recording-level include/exclude;
now individual cells can be QC-flagged out of the comparison. `Project.excluded_cells`
({label: set(cell_id)}) + `exclude_cell` / `is_cell_excluded`; `Project.regroup`
drops flagged cells alongside excluded recordings (a **display-time remap — no
recompute**, like the existing exclusions), and they persist in the project file.
Viewer **Analysis ▸ Toggle selected-cell exclusion** (`Ctrl+Shift+X`,
`toggle_cell_excluded`) flags the selected cell in/out with a status confirmation —
for removing obvious tracking errors / debris. Tests +2 (regroup drops the flagged
cell + toggle-off restores; save/load round-trip). `pytest` **117 passed**; smoke
green; all files < 500.

This completes the improvement program: PR1 edge polarity + lagged actin, PR2
run-and-tumble + track QC, PR3 stats power (FDR/CI/cluster-robust), PR4 contact-
inhibition (CIL), PR5 rose/density/forest plots, PR6 disk cache, PR7 headless
runner, PR8 cell-level QC.

---

## 2026-06-15 — PR7: headless analyze-project runner (figures + stats CSVs)

`scripts/analyze_project.py`: load a project (`--data-root`/`--name` or a `.cmp`
`--project`), run the full cross-recording Comparison, and write a paper-ready
folder — `per_cell.csv`, `per_recording.csv`, `multivariate.csv` (PERMANOVA + LORO-
AUC per arm), per arm-contrast `forest_<test>_vs_<control>.csv`, **box-plot PNGs**
for the most-differentiating metrics, an **effect-size forest PNG** per contrast,
and an ensemble direction-autocorrelation PNG — all GUI-free (offscreen Qt only for
rendering; figures via `widget.grab()` so axis labels render). Reproducible:
recording = unit throughout, same masks → same tables. `--limit` caps recordings
for a quick run. Verified on the synthetic sample (CSVs) + synthetic multi-condition
data (publication-quality forest/box PNGs). Test +1 (subprocess integration on the
sample). `pytest` **115 passed**; all files < 500.

---

## 2026-06-15 — PR6: performance — per-recording disk cache for heavy passes

New `analysis/cache.py`: a per-recording disk cache keyed by a fast **content
fingerprint** of the label stack (shape/dtype/nonzero + a strided byte sample) +
params, so it auto-invalidates when the masks or params change; stored under the
gitignored `analysis_out/cache/`, graceful on read/write failure. The **VAMPIRE
shape-mode model** now routes through it (`window_actions._shape_modes_model`): the
~15-30 s KMeans refit is skipped on re-open / revisit — measured **1665 ms → 2 ms**
on a cache hit (in-memory + disk). The viewer also memoises **per-frame contacts**
(`_frame_contacts` / `_frame_interfaces`, cleared on recording change) so colour-by-
contact + the contact overlay don't recompute when stepping back over frames. Tests
+2; smoke green; `viewer_window` factored to stay at 498. `pytest` **114 passed**.

---

## 2026-06-15 — PR5: plotting — rose + 2D phenotype density + effect-size forest

Three new visualizations that turn the data into figures.
- **Effect-size forest** (`gui/forest_plot.py` + `compare.forest_data`): Cohen's d ±
  95% bootstrap CI of *every* metric for a chosen contrast, sorted by |d|, red where
  MWU p<0.05 — the multivariate phenotype as one figure. CSV export. Stats-tab
  **Forest…** button.
- **2D phenotype map** (`gui/phenotype_map.py`): the per-**cell** cloud of two metrics
  (default roundness vs persistence) with a 1σ+2σ covariance ellipse per condition —
  the KO "rounder + less persistent" separation made visible. Stats-tab **Phenotype
  map…** button.
- **Rose plot** (`PopulationPanel` "Rose (net direction)"): polar histogram of per-cell
  net-migration directions + the mean-resultant-length R (directional bias).
All wired via the mixin so `compare_window` is untouched. Tests +1 (`forest_data`
ranks by |d|); smoke extended (forest/phenotype/ranked dialogs + population rose).
`pytest` **112 passed**; all files < 500.

---

## 2026-06-15 — PR4: contact-inhibition of locomotion (CIL)

New `analysis/cil.py` — the payoff of the contact tracking. `contact_locomotion`
combines the per-frame contact state + partners with centroid velocities → per-cell:
`speed_free` / `speed_contact` + `speed_ratio_contact` (contact ÷ free; <1 = slows on
contact, the CIL signature), `delta_speed_onset` (event-triggered speed change as a
contact forms), `velocity_alignment` (cosine with contacting neighbours' directions —
collective migration), `n_contact_onsets`. Wired into `build_comparison(with_cil=…)`
behind a new **Contact-inhibition (CIL)** analysis toggle (default off); metric_docs +
tooltips. Real Pos60-DMSO: cells 7 & 11 slow on contact (ratio 0.72 / 0.81), cell 10
co-migrates with its neighbour (alignment 0.69). Tests +2. `pytest` **111 passed**;
all files < 500.

---

## 2026-06-15 — PR3: stats power — FDR + bootstrap CI + cluster-robust cell-level test

New `analysis/stats_extra.py` (dependency-free, np+scipy — the project stays
statsmodels-free): `benjamini_hochberg` (FDR q-values, less conservative than
Bonferroni across many contrasts), `bootstrap_ci` (percentile CI of any statistic),
and `cluster_robust_p` (cell-level group effect with **recording-clustered** robust
SE, Liang-Zeger CR1 — a random-intercept-mixed-model stand-in that uses cell-level
data while keeping the recording the inference unit). The **Ranked report** now adds
**q (FDR)**, **Cohen's d ±95% bootstrap CI** and a **cell-level p** column (★★★ now
keys off q<0.05); `ranked_group_comparisons` gained `per_cell` + `with_ci`. On
synthetic data the cell-level cluster-robust p (0.0006) is sharper than the
recording-unit MWU, as expected. Tests +4. `pytest` **109 passed**; all files < 500.

---

## 2026-06-15 — PR2: run-and-tumble decomposition + ID-swap track QC

`motion.run_and_tumble`: split a track into directed **runs** and reorientation
**tumbles** (a step turning >60° from the previous is a tumble) → `n_runs`,
`mean_run_steps`/`mean_run_duration_min`, `tumble_rate_per_min`, `frac_tumble`,
`mean_tumble_angle_deg` — a persistence readout that resolves run length from turn
frequency (more sensitive than a single autocorrelation, useful for the underpowered
YODA1 arm). `motion.jump_steps`: displacement-outlier steps (>5× median) as a
track-continuity / ID-swap QC → `n_track_jumps`, `frac_track_jumps`, `max_step_um`.
Both wired into `per_cell_table` → the Comparison readouts; metric_docs + tooltips.
Tests +2. `pytest` **105 passed**; all files < 500.

---

## 2026-06-15 — PR1: front–rear edge polarity + lagged actin↔edge + edge in the comparison

First of an 8-part improvement program. **Edge polarity** (`edge_dynamics.edge_polarity`):
rotate each frame-pair's angular sectors into the cell's **migration-direction frame**
→ front / rear / side edge velocity, a `polarity_index` (front−rear), and
`rear_retraction_fraction` (spatial concentration of retraction at the rear — the
PIEZO1 GOF/YODA1 signature; more speed-independent than the magnitude). Folded into
`edge_summary_for_cell`. **Lagged correlation** (`edge_intensity.lagged_intensity_correlation`):
edge-velocity ↔ rectangle-intensity Pearson r vs frame lag → does the fluorescence
**lead or follow** the edge motion (peak lag/r exposed in `analyze_cell`'s summary).
**Surfaced in the comparison**: new **Edge dynamics** analysis toggle
(`build_comparison(with_edge=…)`) adds the per-cell edge summary + events + polarity
columns; the edge↔fluor block adds `edge_piezo_peak_lag`/`_r`. metric_docs + tooltips
for all. Tests +4. `pytest` **103 passed**; all files < 500.

---

## 2026-06-15 — GUI bug-hunt: fix headerless empty contact-pairs CSV

A headless test-drive (every colour-by mode incl. contacts, the contacts overlay,
cell-info contact plots, edge panel, Settings, the comparison + ranked report for
every metric, single-group + over-filtered, on a real multi-cell and a single-cell
recording) found **0 crashes / 0 anomalies** in the interactive surfaces. One real
bug surfaced in the export edge case: a recording with **no touching cells** (e.g. a
single-cell crop) made `contact_pairs_table` return a columnless empty DataFrame, so
`contact_pairs.csv` was a 1-byte headerless file that pandas/Origin can't read
(`EmptyDataError`). Fixed — `contact_pairs_table` now always carries the full column
header (dt-aware `mean_episode_min`/`_frames`), so an empty export round-trips. Test
+1 (`test_contact_pairs_table_empty_keeps_header`); `pytest` **100 passed**.

---

## 2026-06-15 — Docs / screenshots / help / tooltips refresh (contacts + config + ranked report)

Brought the user-facing surfaces up to date with the session's new features.
- **Screenshots** (`docs/screenshots/`): `contacts.png` (real WT Pos10 — two cells
  in extensive contact, coloured by class + the interface overlay), `settings.png`
  (the unified Config window, Comparison-analysis tab), `ranked_report.png`
  (synthetic). README gallery + Highlights updated (cell–cell contact bullet,
  colour-by + CSV + ranked-report mentions, Config ▸ Settings replaces the old
  scale-only item). Data policy note extended (WT-control for contacts/settings;
  synthetic for the ranked report).
- **Help ▸ Metrics Reference** (`metric_docs.as_html`): added a **Cell–cell contact**
  section + **Ranked report** / **what-gets-computed** paragraphs to the comparison
  help (the per-frame contact metrics already auto-listed).
- **Tooltips**: overlay checkboxes now carry tooltips (`_OV_TIPS`), incl. the new
  **Cell contacts** overlay; the comparison-analysis toggles, ranked-report button,
  colour-by contact modes already had them.
- **Shortcuts** dialog: added `Ctrl+,` (Settings) + `Ctrl+Shift+C` (Comparison).

GUI test-drive (offscreen): contacts overlay + colour-by, Settings (3 tabs), Metrics
Reference, Shortcuts all open clean. `pytest` **99 passed**; all files < 500.

---

## 2026-06-15 — Ranked group-comparison report (Comparison ▸ Stats)

The Stats tab showed only the design-driven contrasts (control-vs-test within
arms). New **Ranked report…** button lists **every** group-vs-group pair for the
current metric, ordered by the likelihood of a significant difference (smallest p
first). `compare.ranked_group_comparisons(per_rec, metric)` (pure) — recording =
unit, Mann-Whitney U (two-sided) + Cohen's d + Bonferroni over the tested pairs;
`gui/ranked_report.py::RankedReportDialog` renders a sortable table (p / Bonferroni
/ Cohen d / ★ stars) with CSV export. The button + opener live in
`StatsTablesMixin` (`_add_stats_buttons` / `_show_ranked_report`); `_update_stats`
caches the per-recording table for it. Moving the button creation into the mixin
**freed 2 lines** in `compare_window` (499 → 497).

Real data (DMSO/GOF/KO × 3 each, `frac_spread`): ranks **DMSO vs KO first**
(p=0.10, Cohen d=−2.14 — the strongest contrast), overlapping pairs last. Tests +2
(ordering + edge cases). `pytest` **99 passed**; smoke green; all files < 500.

---

## 2026-06-15 — Pairwise contact tracking (which cells touch, when, degree)

Answering "do you keep track of which cells touch, when, and the degree?" — the
per-frame/per-cell tables tracked *when* + *degree* but collapsed *which* partner.
New `contacts.contact_pairs(labels, scale, dt)` returns **one record per cell pair**
that ever touches: `cell_a` / `cell_b`, `first_frame` / `last_frame`,
`n_frames_in_contact`, `n_episodes`, `mean_episode_(min|frames)`, and the contact
**degree** (`mean_contact_fraction` / `max_contact_fraction`; per-frame pair degree =
the larger of the two cells' engaged-boundary fractions). Reuses the per-frame
`partners` dicts (no extra compute when `contacts_over_time` is passed).

Surfaced as a **Cell-pair contacts CSV** — `exporters.contact_pairs_table` +
`export_all(which=…contact_pairs…)` + a checkbox in the Export-CSV dialog (off the
GUI thread, so it stays responsive). Real Pos60-DMSO: the 8↔11 pair first touches at
**frame 68 — the division frame** (degree ≤0.20); 7↔8 spans frames 10–93.

(Deliberately not a synchronous Cell-Info line — the full per-recording pass would
freeze on selection; the threaded CSV + the live contact overlay cover it.)
Tests +3 (`contact_pairs` which/when/degree, separate partners + none, table +
`export_all`). `pytest` **97 passed**; all files < 500.

---

## 2026-06-15 — Unified Config window + comparison-analysis controls

Consolidated the scattered Config dialogs into one tabbed **Config ▸ Settings…**
(Ctrl+,) window (`gui/config_window.py`) with tabs: **Cell plot metrics**
(checkboxes bound to `cell_info` — same state as before), **Comparison analysis**
(NEW), and **Pixel size & time scale** (`scale_dialog` refactored to expose a
reusable `ScalePanel(QWidget)`). The old per-item Config menu (metrics submenu +
scale item) is replaced by the single Settings entry; Comparison-plot-options
stays (a live style editor, also linked from the new window).

**Comparison-analysis controls** (the requested "menu controls like cell plot
metrics, but for the comparison"): `compare_tables.COMPARE_OPTIONS` +
`compare_options()` define toggles for the optional/heavy analysis families —
**Cell–cell contacts**, **State-segmented metrics**, **Solidity** — persisted in
QSettings. `build_comparison` gained `with_contacts` / `with_state_segmented`
(joining `with_solidity`); `ComputeWorker` passes the toggles; `per_frame_table`
threads `with_contacts`. Disabling a family **skips its compute** (faster) and
drops its columns. The compute cache key folds the active options
(`…_lag30_ocoso.pkl`) so toggling triggers a recompute.

Verified: ConfigWindow builds its 3 tabs (43 metric checkboxes); on 3 real
recordings, full vs lean `build_comparison` = 14→0 contact cols and 14→0
state-segmented cols; cache key changes with the toggles. `pytest` **94 passed**
(+1 per_frame_table gate assertion); smoke green; `compare_window` held at 499,
all files < 500.

---

## 2026-06-15 — Contact overlay + contact-event dynamics (contacts follow-ups)

The two follow-ups noted in the contacts PR.
- **Contact overlay** (`overlays.py` + `display_panel` toggle "Cell contacts" +
  `viewer_window` render): draws the **shared-interface pixels** on the canvas,
  coloured by class (blue = point, red = extensive), via new
  `contacts.frame_interfaces` (refactored to share `_contact_pixels` / `_aggregate`
  with `frame_contacts`). Verified on Pos60 frame 68 — blue traces exactly where
  cell 11 meets cells 8 and 7.
- **Contact-event dynamics** (`contacts.contact_episodes` + `contact_summary` +
  `exporters.per_cell_table`): per-track in-contact episodes (a frame gap ends a
  run) → `n_contact_events`, `mean_contact_duration_min`, `contact_events_per_min`
  — contact formation/breakage frequency + duration, flowing into the per-cell CSV
  and the Comparison readouts. Real data: cell 11 has 3 episodes (mean 73 min,
  76% time-in-contact); isolated cells 0.
- `metric_docs` entries + a `_per_min`/`_per_frame` label/units fix so the rate
  columns render cleanly.

Tests +4 (`contact_episodes` runs/gaps, `frame_interfaces`, `contact_summary`
event dynamics, per-cell event columns). `pytest` **94 passed**; smoke green; all
files < 500 lines (`viewer_window` 481).

---

## 2026-06-15 — Cell–cell contact detection + classification (new analysis)

The analysis was missing any measure of when cells **physically touch** (only
centroid-proximity `neighbors.py` existed). New `analysis/contacts.py` measures
the actual shared-membrane interface and classifies it.

**Method** (masks-only, pure/GUI-free): per frame, two cells are in contact where
a boundary pixel of one lies within `DEFAULT_GAP_PX` (1.5 px) of a boundary pixel
of the other — found via a KD-tree over all boundary pixels (calibrated on real
masks: touching cells sit edge-to-edge, boundary pixels 1.0 px apart). Per cell:
`contact_fraction` (boundary engaged with any other cell), `n_contacts`,
`contact_length` (interface µm), `max_contact_fraction`, and a **class** —
`free` / `point` / `extensive` — split on `EXTENSIVE_FRAC` (0.25) of the largest
single interface (`classify_contact`). `contact_summary` aggregates per track
(time-in-class fractions + means).

**Integrated everywhere** the existing metrics flow:
- per-frame CSV (`per_frame_records` → contact columns; `with_contacts` toggle).
- per-cell summary (`exporters.per_cell_table`): `mean/median_contact_fraction`,
  `mean_n_contacts`, `mean_contact_length_um`, `frac_in_contact` /
  `frac_point_contact` / `frac_extensive_contact` — which **auto-appear as
  Comparison-window readouts** (numeric per-cell cols → `compare.aggregate`).
- Cell-Info plot series + Config metric menu (`cell_frame_table`,
  `BASE_FRAME_METRICS`): contact_fraction / n_contacts / contact_length /
  contact_state_code.
- **Colour-by** (`display_panel` + `colorby`): Contact fraction, Contact count
  (continuous + units bar), Contact class (categorical free/point/extensive,
  `CONTACT_COLOR`).
- `metric_docs` entries + units (`n_contacts` → count) → tooltips + Help reference.

Real data: WT/DMSO cells spend ~18–20% of their time in contact (mostly point;
`frac_extensive` ~0.01–0.02); the single-cell KO recording has none. Verified the
colour-by-contact-class overlay on Pos60 frame 68 (cells 8/11/7 = blue point
contact). Tests: +10 (`tests/test_contacts.py` — classification, extensive/point/
free geometry, gap tolerance, summary fractions, table + cell-info flow).
`pytest` **90 passed**; all files < 500 lines (cell_metrics 481).

Follow-ups (noted, not done): a dedicated contact overlay drawing the shared
interface lines; contact-event dynamics (formation/breakage duration + frequency
over a track) à la the edge-event detector.

---

## 2026-06-15 — Fix reported regressions (division, edge views) + 8 review-confirmed bugs

Three user-reported regressions on Pos60-DMSO + the bugs an adversarial multi-agent
review surfaced, all fixed in one pass.

**Reported regressions**
1. **Division `8→11` no longer detected/reported.** The scored detector
   (`lineage.infer_divisions`) was mis-calibrated for this project's 2-D footprints:
   `swell` measured an area *peak* (but keratinocytes **round up** as they divide, so
   the footprint *shrinks*), and `mass` assumed a ½-split (the parent keeps its ID), so
   both cues read 0 and the plain-mean score fell to 0.463 (< 0.5). Re-calibrated:
   `swell` is now a **bidirectional** departure from a **pre-split baseline** (up *or*
   down), `mass` is **lenient** (plausible-fraction plateau, not exactly ½), the score
   is a **weighted mean** (`_DIV_WEIGHTS` — proximity/persistence/roundedness carry it),
   plus a **parent-continuation gate** (the parent must persist past the split — rejects
   re-ID/hand-offs) and a `min_persist=0` divide-by-zero guard. `8→11` now scores
   **0.692** and is reported in the viewer. (Also fixed the `_circularity` 'balled'
   crop: sized from the cell's **true bbox** via `find_objects`, not the area-equivalent
   radius, so elongated parents aren't truncated into looking round.)
2. **Edge "sampling rectangles" + 3. "edge-this-frame intensity" not displayed.** Not a
   code break — both views need a Fluor channel, and the combo defaulted to "(none)".
   `edge_panel._populate_fluor` now **auto-selects the first fluorescence channel**
   (heuristic `_is_fluor_name`, skips DIC/brightfield/placeholder) on first population,
   while still respecting an explicit later "(none)". Both views render by default.

**Review-confirmed bugs** (adversarial workflow — 8 confirmed): `compare_window`
**`_current_plot` IndexError on the new Dir-autocorr tab** (HIGH — added the 4th plot
to the list); `registration._max_shift` could be **0** for sub-4-px images
(`max(1, …)`) + `_prep` **crashed on a 1-px strip** (`np.gradient` needs ≥2 samples);
`prep_dialog` preview **mixed a stored-shift ref with a raw moving layer** (now both
raw) + **`dy` spinbox bounded by width** (now height); `recording.apply_correction`
**crashed on a malformed shift/fov** (now skips); `edge_panel` velocity edge-map used
the **single-frame centroid** vs the kymograph's **mid-pair centroid** (now matched);
`compare_window` fluor **cache-key collision** (new `compare_tables.channel_tag` hashes
the raw name).

Tests: +6 (`test_lineage`: footprint-rounding split detected, re-ID rejected,
`min_persist=0`; `test_registration_fov`: `_max_shift`≥1, degenerate strip,
`apply_correction` malformed). `pytest` **80 passed**; `smoke_edgecases` green (now
asserts `_current_plot` on every tab + edge fluor auto-select); anomaly probe on real
WT+KO **NO ANOMALIES**. All edited files < 500 lines (compare_window back to 499 by
moving the hash into `channel_tag`).

---

## 2026-06-15 — Edge Dynamics: plot every per-sector metric on the edge-this-frame map

The "edge this frame" map (the cell boundary coloured by a per-sector metric) now
offers **all** available per-sector metrics, not just velocity + radius: added
**Edge this frame: intensity** (boundary coloured by the per-sector rectangle
fluorescence at the current frame, when a Fluor channel is chosen). `_draw_edge_frame`
takes a `metric` ("velocity" / "radius" / "intensity"); modes/indices reorganised
(`_FRAME_METRIC`, `_RECTANGLES`), CSV export + frame-redraw handle the new mode.
Verified on the sample: all three colour the 89 boundary points; intensity is empty
(prompt) without a channel. `pytest` 74 passed; GUI smokes green; edge_panel 431 lines.

---

## 2026-06-15 — Direction persistence: DiPer ensemble autocorrelation by condition

Incorporated the **DiPer** (Gorelik & Gautreau 2014) directional-persistence
methodology from `~/Documents/GitHub/diper_clone`. Its core metric — the **direction
autocorrelation** C(τ) = ⟨û(t)·û(t+τ)⟩ over unit step vectors — already matched
`motion.direction_autocorrelation` per cell; what was missing is DiPer's headline
output, the **ensemble decay curve per condition**.

- `compare.build_comparison` now also returns `autocorr_long` (per-recording ensemble
  direction autocorrelation, mean over cells, long form recording/condition/tau/autocorr)
  → it returns a **3-tuple** `(per_cell, msd, autocorr)`. `ensemble_by_condition` gained
  `value_col` so it averages either MSD or autocorr across recordings (recording = unit).
- New `compare_plots.ensemble_autocorr` + a **"Dir. autocorr"** tab in the Comparison
  window (kept last, so Scatter stays index 2) — mean±SEM or median+CI curves per
  condition, decaying from ~1 (persistent) toward 0 (random), y ∈ [−0.2, 1.05]. Reuses
  the existing MSD style controls (τ-bin / max-lag / points). Threaded compute, cache,
  and save/load now carry the autocorr frame.

Tests: `test_compare_extras` — the DiPer method (straight track → 1 at every lag; a 90°
zig-zag → 0 at lag 1) + the ensemble-autocorr aggregation. `smoke_compare_window`
exercises the new tab + save/load and writes `docs/screenshots/comparison_autocorr.png`
(synthetic). `pytest` **74 passed**; four GUI smokes green; all files < 500 lines.

---

## 2026-06-15 — Scored division inference (the original detector's cues, in-project)

`lineage.infer_divisions` is now a **scored** detector reproducing the original
pipeline's cue set — but computed from the **cleaned masks** in-project (still no
`divisions.json`). Each parent→daughter candidate (a daughter first appearing
adjacent to a parent present the previous frame, away from the border) gets five
[0,1] cues — **prox** (closeness), **swell** (parent area peak ÷ life baseline),
**balled** (parent circularity in the pre-split window, via `cell_metrics._perimeter`),
**persist** (daughter survival vs `min_persist`), **mass** (daughter:parent area near
½) — averaged into a `score`, kept above `score_threshold` (default 0.5). Each event
carries the score + sub-cues; `return_all` exposes rejected candidates for tuning.

On real Pos60-DMSO the one geometric candidate **8→11 @68 scores 0.46** (prox 0.58,
swell **0.00**, balled 0.74, persist 1.00, mass **0.00**) → **below 0.5, not flagged**:
cell 8 did not swell and the masses don't split ½, so the full cue set treats it as a
weak candidate rather than a confident division (the original scored that region low
too). The threshold is tunable per call.

Tests: `tests/test_lineage.py` — a realistic swelling division is detected with a high
score + sub-cues; the threshold gates it and `return_all` exposes it. `pytest`
**72 passed**; four GUI smokes green; all files < 500 lines.

---

## 2026-06-15 — Divisions overlay: parent→daughter links

The Divisions overlay now draws each division as a **parent→daughter link** — a line
from the parent (open circle) to the daughter (diamond) at the division's frame —
instead of two undifferentiated diamonds. `overlays.update_overlay` takes
`division_links` = `((parent_y,parent_x),(daughter_y,daughter_x))` pairs (built in
`viewer_window._update_overlays` from the masks-derived `self.divisions`); new
`div_link` / `div_parent` items. Verified on real Pos60-DMSO: the 8→11 division at
frame 68 draws a circle on cell 8 linked to a diamond on cell 11. `pytest` 71 passed;
all four GUI smokes green; files < 500 lines.

---

## 2026-06-15 — Lineage derived from masks; no pre-cleaning artifacts in any metric

Principle (from the phantom-division bug): **the loaded mask label stack is the
single analysis input** — every metric must be computed in-project from it, so IDs
or edits made before the masks were finalised are irrelevant. Audited the whole
package and closed the one live violation (lineage).

- **Audit result**: the live GUI analysis (shape, motion, edge, state, population,
  comparison via `build_comparison` + `state_metrics`) is already masks-derived; it
  uses `feature_tables` only for **constants** (`COND_COLOR`/`ARMS`) and **pure stats**
  (`arm_tests`), never its CSV readers. The only pre-cleaning dependency in the live
  path was **`divisions.json`**. (`feature_tables`' CSV/pickle readers are used solely
  by the exploratory follow-up scripts for cross-checking the original pipeline — now
  documented as legacy/validation-only.)
- **Lineage now derived from the masks**: new `lineage.infer_divisions(labels)` infers
  divisions from the track topology — a daughter track that first appears adjacent to
  a parent present the previous frame (centroid within rₚ+r_d; not first seen at the
  image border = entering the FOV). Every event references real, surviving tracks.
- **`divisions.json` reading removed entirely**: deleted `io/divisions.py` +
  `Entry.load_divisions` + exports; `viewer_window` computes `self.divisions =
  lineage.infer_divisions(labels)` on load. (`lineage.valid_divisions` kept as a
  generic safety util.)
- **On real Pos60-DMSO** the masks-derived inference gives the *correct* lineage —
  **8 → 11 at frame 68** (the cleaned masks really do show track 11 emerging beside
  track 8, matching the reported expectation), with **no phantom cell 16**. The cell
  table now shows cell 8 `daughters=11` and cell 11 `parent=8`.

Tests: `tests/test_lineage.py` gains `infer_divisions` coverage (split detected;
border-entry / distant-cell / translation not; degenerate → []). `pytest` **71 passed**;
four GUI smokes green; all files < 500 lines.

---

## 2026-06-15 — Fix phantom divisions (validate against the cleaned masks)

Bug (real data, Pos60-DMSO): the cell table showed cell 11 with `daughters = 16`
though no cell 16 exists and cell 11 never divides, and the Divisions overlay drew
diamonds in empty space at frames 55 & 63.

Root cause: `divisions.json` is written by the pipeline **before** the masks are
manually cleaned, and lists scored *candidate* events. After cleaning, the surviving
tracks here are `[1,2,3,4,5,7,8,10,11]`, but the two candidates reference daughter
track **16** (and parent **21**) — both removed in review. The app surfaced these
stale candidates as real divisions (the Population lineage tree already guarded
against missing tracks, but the cell table, cell-info, divisions overlay and
division-count timeline did not).

Fix (one place, all consumers): **`lineage.valid_divisions(divisions, labels)`** keeps
only events whose **parent and daughter tracks both exist** in the (cleaned,
FOV-cropped) mask stack; `viewer_window._load_entry` filters `self.divisions` through
it right after load, so the cell table / cell-info / overlay / timeline all get clean
data. `cell_table` additionally restricts parent/daughters to in-table cells and adds
the columns only when a real relationship exists. On Pos60-DMSO both phantom events
drop → no `daughters` column, no overlay diamonds.

Tests: new `tests/test_lineage.py` (`present_ids`, `valid_divisions` drops
absent-track events incl. the exact Pos60 case, keeps valid ones, `relatives` on the
cleaned set). `pytest` **68 passed**; four GUI smokes green; all files < 500 lines.

---

## 2026-06-15 — Single-cell crops (varying shape/length) + manual scale overrides

For a new experiment style that crops one cell per field — recordings vary in H×W
and length (only the frames where the cell is present, sometimes appearing partway
through) — and to handle files whose metadata is missing/wrong.

- **Single-cell crops work as-is**: recordings are analysed independently, so a
  project can mix arbitrary shapes/lengths. Verified (not just assumed) by the new
  `scripts/smoke_singlecell.py`, which generates 4 crops (5–12 frames, 48×56 …
  120×96, one cell appearing only in frames 2–8) and drives the viewer (channel +
  composite at each shape), the edge-movement↔intensity panel, off-thread
  Population/Cell-table computes, and `build_comparison` across the mixed project —
  no fixed-shape / fixed-length / present-from-frame-0 assumptions surfaced.
- **Manual pixel-size + time-scale overrides** (`gui/scale_dialog.py`, **Config ▸
  Pixel size & time scale…**): per-field override of **µm/px** and **min/frame**,
  stored on the `Project` (`px_size` / `frame_interval`) and applied to **every**
  recording (`Project.scaled`) — scale bar, all µm / µm-per-min metrics, and the
  comparison (`build_comparison(scale_override=…)`, `ComputeWorker`, cache key via
  `corrections_tag`). Unset = use each file's own metadata. Persists in the project
  JSON. `window_actions.open_scale_dialog` / `_apply_scale`; reloads to re-apply.

Tests: `pytest` **65 passed** (new `test_scale_override_applies_and_persists`);
four GUI smokes green (incl. `smoke_singlecell`); all files < 500 lines.

---

## 2026-06-15 — Real-data test drive (actin/Cy5) + auto-align robustness fix

Drove the GUI headless on the **real IC295 data** (48 recordings, 2048×2048,
~97 frames; channels `["Cy5", "DIC 10x", "None"]` — Cy5 = SiR-actin) to exercise
the new edge analysis + alignment and check nothing is broken.

- **Everything renders/runs on real data**: per-channel + DIC/Cy5 composite,
  the edge-movement↔intensity scatter + sampling-rectangle overlay + intensity
  kymograph, off-thread Population / Cell-table / Shape computes, cell-info + MSD,
  colour-by, and `build_comparison(piezo_channel="Cy5")`.
- **Biology checks out**: edge movement ↔ actin(Cy5) gives a strong, highly
  significant **negative** correlation (actin enriched at **retracting** edges;
  protruding-vs-retracting intensity hugely different) — the headline the edge
  analysis was built for, on real data.
- **Bug found + fixed**: `registration.estimate_shift` returned a spurious far
  peak (≈ −270, −360 px) on the real cross-modality DIC↔Cy5 pair, which *destroyed*
  the correlation when applied. Fixed by **bounding the phase-correlation peak
  search to ±`max_shift`** (default `min(100, min(H,W)//4)`; channel offsets are
  small). Auto-align now finds the **real ~(−4, −11) px DIC↔actin offset**, and
  applying it *strengthens* the correlation (r −0.41 → −0.51) — confirming the
  actin/DIC misalignment is real and that correcting it improves the analysis.
  New test `test_estimate_shift_bounded_rejects_far_peak`.

README screenshots for the edge-analysis + alignment panels now use a **real
WT-control** recording's actin (Cy5) channel (`edge_piezo.png`,
`edge_sampling_rectangles.png`, `prep_align_fov.png`) — baseline only, **no
treatment-comparison data** (the comparison screenshots stay synthetic).
`pytest` **64 passed**; all three GUI smokes green; all files < 500 lines.

---

## 2026-06-15 — Pre-analysis: channel alignment + FOV; any channel count

Two non-destructive pre-analysis tools (the actin channel was noticed slightly
offset from DIC, and recordings can carry black FOV borders — both bias the
mask-relative `edge_intensity` sampling), plus a robustness pass for arbitrary
channel counts.

- **`analysis/registration.py`** (new, tested): channel **translation** alignment
  via gradient-magnitude FFT phase-correlation (+ sub-pixel parabolic peak; robust
  across DIC↔fluorescence; no scikit-image — implemented in numpy/scipy).
  `estimate_shift` / `estimate_stack_shift` / `apply_shift`.
- **`analysis/fov.py`** (new, tested): `auto_fov` (inner rectangle by trimming
  near-zero borders; 2-D / (T,H,W) / (T,C,H,W)), `apply_fov` (zero labels outside
  the rect), `fov_mask`, `clamp_rect`.
- **`Recording`**: non-destructive `channel_shifts` + `fov`; `frame` /
  `aligned_channel` apply the shift on read; `apply_correction(rec, corr)`.
  **`Project`** persists per-recording `corrections` (JSON); `correction_for`.
- **`gui/prep_dialog.py`** (new): **Analysis ▸ Channel Alignment & FOV…** — reference/
  align channel pickers, **Auto-align** + manual dy/dx, **Auto-detect FOV** + manual
  rectangle, a live grey/magenta overlay preview with the FOV box. Apply stores the
  correction on the project + reloads (non-cumulative). `window_actions.open_prep_dialog`
  / `_apply_correction`; menu entry in `menus.py`.
- **Wired into display + analysis** (the chosen scope): the viewer reads aligned
  channels (`Recording.frame`) and FOV-crops masks on load; `edge_panel` samples
  `aligned_channel`; `compare.build_comparison(corrections=…)` aligns the fluor
  channel + FOV-crops masks per recording (threaded via `ComputeWorker`; cache keyed
  by `corrections_tag`). Raw files are never modified.
- **Any channel count (1 / 2 / N):** audited — `Recording` already promotes 1-channel
  inputs and the channel/composite UI builds widgets per channel; the new tools reduce
  over channels generically. New `scripts/smoke_channels.py` generates 1-, 2- and
  3-channel synthetic recordings and drives the viewer + prep dialog + edge panel +
  comparison for each.

Tests: `pytest` **63 passed** (new `tests/test_registration_fov.py`); three GUI
smokes green (`smoke_progress`, `smoke_compare_window`, `smoke_channels`); screenshot
`docs/screenshots/prep_align_fov.png`. All files < 500 lines.

---

## 2026-06-15 — Edge movement ↔ fluorescence intensity (faithful `cell_edge_analysis`)

Correlate cell-edge protrusion/retraction with a fluorescence channel (tagged
PIEZO1, **SiR-actin**, or any signal), in the Edge Dynamics tab and as a comparison
metric. This is a **faithful reproduction of the lab's `cell_edge_analysis`
9-step pipeline** (`~/Documents/GitHub/cell_edge_analysis_individual_scripts`),
adapted to this project's closed, tracked cells.

The original works on a single advancing edge `y(x)` (per-x displacement of the
uppermost edge point, vertical sampling rectangle into the cell, correlate the
rectangle's mean PIEZO1 intensity with that displacement). Here a cell is a closed
contour, so the per-x displacement becomes the **per-sector radial edge velocity**
about the mid-centroid (`edge_dynamics`, translation-removed) and the vertical
rectangle becomes a rectangle along the **inward normal** at each sector.

- **`analysis/edge_intensity.py`** (new, replaces the earlier approximate
  `edge_piezo.py`): `rectangle_intensity` / `intensity_kymograph` (mean fluorescence
  in a `depth`×`width` px rectangle reaching into the cell, coverage-gated),
  `movement_intensity_pairs` (local displacement ↔ rectangle intensity, `past`/
  `future`), `correlation_summary` (Pearson **r / R² / p / slope**; protruding/
  retracting/stable counts + mean intensities split at a displacement threshold;
  protrude−retract Δ; **t-test + Mann-Whitney** between protruding and retracting),
  `rectangles_for_frame`, `analyze_cell`.
- **Edge Dynamics tab**: a **Fluor** selector + new views — *Intensity kymograph*,
  the *Edge movement ↔ intensity* scatter (points coloured blue=protrude /
  grey=stable / red=retract, regression line, r/R²/p in the title) and a
  *Sampling rectangles* overlay (centres coloured by intensity); the by-movement-type
  means + Mann-Whitney are in the summary.
- **Comparison window**: `build_comparison(piezo_channel=…)` adds per-cell
  **`edge_piezo_corr`** (Pearson r), **`edge_piezo_slope`**, **`piezo_protr_minus_retr`**
  via `edge_intensity.analyze_cell`; **fluor** toolbar selector (channels read cheaply
  from the sidecar via `recording.channel_names_of`), threaded via
  `compare_tables.ComputeWorker`, cache keyed by channel. Flows into the
  distribution / stats / multivariate machinery.

Validated on the synthetic sample's fluorescence channel (the IC295 data has no
tagged PIEZO1; the method is channel-agnostic — SiR-actin Cy5 works identically).
Tests: `pytest` **53 passed** (new `tests/test_edge_intensity.py`, sign ± /
classification / degenerate / end-to-end on synthetic deforming cells; removed
`test_edge_piezo.py`); the progress smoke drives the panel + the comparison metric
and writes `docs/screenshots/edge_piezo.png`. Both GUI smokes green; all files
< 500 lines.

---

## 2026-06-14 — Self-drive test pass → multivariate test + zoom-to-cell

Drove the GUI on the **real 48-recording IC295 dataset** via the self-drive remote
(`MASKVIEWER_REMOTE`, offscreen): loaded recordings, composite Cy5+DIC, colour-by
metrics + units bar, threaded Population/Shape/Cell-table computes (progress bar),
cell selection, screenshots — all good. Two improvements fell out:

- **Analysis — multivariate phenotype test in the GUI** (`compare.multivariate_contrasts`
  + `compare_tables.multivariate_dialog`, Results ▾ ▸ *Multivariate test*): per-arm
  **PERMANOVA p + leave-one-recording-out AUC** over all per-recording metrics,
  reusing `multivariate.py`. Surfaces the headline KO-vs-WT multivariate phenotype
  (previously script-only).
- **UX — Zoom to Cell** (`ImageCanvas.focus`, `WindowActionsMixin.zoom_to_cell`,
  View ▸ Zoom to Cell / `Z` / remote `zoom_cell`): frames the canvas on the selected
  cell — in the real 2048² FOV cells are tiny dots, so this was the clearest pain
  point. Verified via the remote on real data (scale bar 200 µm → 20 µm).

Tests: `pytest` **47 passed** (multivariate_contrasts + ensemble bin/max-lag +
save/load + border-distance); compare smoke adds the multivariate dialog +
`_multivariate.png`; progress smoke adds zoom-to-cell. Both GUI smokes green; all
files < 500 lines. (Screenshots stay synthetic — public-repo policy; real data used
only for validation.)

Next ideas (not yet done): per-cell-pooled (cell=unit) stats toggle in the
Comparison window; SiR-actin (Cy5) cortical-intensity-vs-edge-velocity correlation;
a menu bar for the increasingly busy Comparison toolbar; double-click-to-zoom.

---

## 2026-06-14 — Compute-time MSD lag count exposed

Followed the display-time max-lag with the **compute-time** one:
`compare.build_comparison(max_lag=…)` parameterises the previously-hardcoded
`MAX_LAG=30`, and the Comparison-window toolbar gained a **lags** spin box (read
at Compute; lets the MSD reach longer τ, which the display cap can't). The
per-project pickle cache is now keyed by lag count (`_compare_<name>_lag<N>.pkl`)
so changing it recomputes cleanly. `pytest` 46 passed; smokes green.

---

## 2026-06-14 — Ensemble-MSD max-lag display option

Exposed the ensemble-MSD lag count as a plot option: `PlotStyle.msd_max_lag`
(graph options "Ensemble-MSD max lags", 0 = all) caps the number of lags/bins
shown — `compare.ensemble_by_condition(max_lag=…)` keeps the first N (smallest τ),
display-time (no recompute; the computed ceiling stays 30 lags). `pytest` 46
passed (new ensemble_by_condition test); smokes green.

---

## 2026-06-14 — Filter annotations, scatter-fit redesign, MSD-lag clarity

- **Filter annotations**: a `show_filter_note` option (graph options) labels the
  graphs (appended to each plot title via `compare_plots.set_filter_note`) and the
  tables (Stats omnibus + a Data-tab note) with the active filters when any are
  applied. `FilterMixin._filter_note` builds the summary; tables use
  `_table_filter_note` (group-visibility excluded — tables show all groups).
- **Scatter-fit redesign**: the model combo + fit checkboxes conflicted (a fit
  only drew when the combo was off "none"). Replaced with **two combos** — model
  (`fit_kind`: none / linear / polynomial-2 / polynomial-3 / power / exponential /
  log) × target (`fit_target`: all data / per group / both) + a ±SE-band checkbox.
  Added **polynomial (multiparameter) fits** (`_fit_xy` via `np.polyfit` degree
  2/3); power/exp/log stay linearised.
- **Ensemble-MSD lag**: clarified there is no hard-coded 50 — τ = lag × frame
  interval (min = one interval, e.g. 10 min; 30 lags). A 50 only appears when the
  **τ-bin** option is set; binning now positions each bin at the **mean** of the
  real lags it holds (never below the smallest lag).

Tests: `pytest` **45 passed**; the compare smoke exercises the filter annotation,
every fit model, and group visibility. Both GUI smokes green; all files < 500.

---

## 2026-06-14 — Comparison graph options expanded + save/load results

A big batch of Comparison-window graph options + results persistence.

- **Ensemble MSD**: `PlotStyle.msd_bin_min` (τ-bin width, `compare.ensemble_by_condition`
  rebins display-time), `msd_log` (log-log ↔ **linear axes**), `msd_points`
  (markers + per-point error bars, drawn as log-safe `PlotDataItem`s).
- **Group visibility**: a dynamic **Show groups** section in the style dialog
  (`PlotStyleDialog.set_groups`) → `CompareWindow.hidden_groups`; hidden groups
  drop from the **graphs** only (Stats / Data still cover all).
- **Background colour** (`PlotStyle.background`: default/black/white/grey, applied
  with a contrasting foreground in `_axes`) + **legend** (`PlotStyle.legend`,
  per-plot legends managed by `_prep_legend` + `_legend_entry`).
- **Scatter fit lines** (`fit_kind` linear/power/exponential/log · `fit_all` ·
  `fit_groups` · `fit_ci` ±SE band — `_fit_xy`/`_draw_fit`), for individual groups
  and/or all data.
- **Save / load comparison results** (`compare.save_results`/`load_results` +
  `ResultsIOMixin`): a **Results ▾** toolbar menu (Save / Load / Export CSVs) — the
  computed per-cell + MSD frames (+ design / exclusions) reload without recompute.
- **Config ▸ Comparison plot options…** in the main viewer opens the style dialog
  (`open_compare_plot_options`).
- File-size hygiene: results I/O + CSV export moved into `compare_tables.ResultsIOMixin`.

Tests: `pytest` **45 passed** (new save/load roundtrip). The compare smoke drives
background / legend / fits / msd-points / τ-bin / linear / group-visibility /
save-load / the Config entry. Both GUI smokes green; all files < 500 lines.

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
