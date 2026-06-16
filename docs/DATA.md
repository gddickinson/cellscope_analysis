# Data — what's in `data/`, and how the masks were made

This project **views and analyses** results; it does **not** produce them.
The recordings and masks come from the
[CellScope](https://github.com/gddickinson/cellscope) pipeline. This doc
explains what the `data/` folder contains, the layout of one recording, and
how the detection masks were generated — so the numbers can be interpreted
and reproduced.

> `data/` is a **local, gitignored** folder of symlinks into a CellScope
> tree, created by `python scripts/link_data.py` (see CLAUDE.md). Nothing in
> it is committed — it points at private local data.

---

## The dataset: IC295

48 recordings of migrating **keratinocytes**, imaged by DIC + Cy5
fluorescence (SiR-actin), one position per recording:

| property | value |
|---|---|
| frames | 97 per recording |
| frame size | 2048 × 2048 px |
| pixel size | **0.6523 µm/px** (from the `.ome.json` sidecar) |
| interval | **10 min** between frames |
| channels | `Cy5`, `DIC 10x`, `None` (3-channel OME-TIFF) |

Six treatment conditions in **two independent experiments + a vehicle check**
(this structure matters for the stats — cross-arm comparisons are not valid):

| arm | control | treatments |
|---|---|---|
| **genetic** | WT | GOF, KO |
| **drug** | DMSO (vehicle) | YODA1 (Y1), OT |
| **vehicle** | — | WT vs DMSO |

n = 8 recordings per condition.

**What the conditions are (the biology).** This is a **PIEZO1** mechanosensitive
ion-channel study. The genetic arm is PIEZO1 **WT / GOF (gain-of-function) /
KO (knockout)**; the drug arm is **DMSO** (vehicle) / **Y1 = YODA1** (the
canonical PIEZO1 *agonist*) / **OT = Otenabant** (a CB1 cannabinoid-receptor
antagonist/inverse agonist — note this is *not* a PIEZO1 compound). PIEZO1 acts
as a brake on keratinocyte migration: KO tends to migrate faster/straighter,
while GOF and YODA1 slow migration and increase rear retraction (Holt et al.
2021 *eLife* 65415; Ravichandran et al. 2024 *PLOS Comp Biol*). The Cy5 channel
is SiR-actin, which labels cortical/stress-fibre actin (not fresh lamellipodia).

---

## `data/` layout

```
data/
├── by_condition/<cond>/<label>/      whole CellScope tree (one folder/recording)
├── recordings/<cond>__<label>        flat symlink to each recording folder (48)
├── results/
│   ├── compare/                      recording-level aggregate analysis + plots
│   └── compare_pooled/               cell-level (pooled) aggregate analysis
└── gt/
    ├── ic295_gt_full/                hand-labelled ground-truth masks
    └── legacy_gt/                    older ground-truth set
```

The viewer's `config.json` points its `data_root` at `data/by_condition`.

### One recording folder (`by_condition/<cond>/<label>/`)

| file | what it is |
|---|---|
| `*_MMStack_<label>.ome.tif` | the recording, `(T=97, C=3, H, W)` uint16 |
| `*.ome.json` | sidecar: `um_per_px`, `time_interval_min`, `channel_names` (**authoritative scale**) |
| `*_metadata.txt` | original Micro-Manager acquisition metadata |
| `pipeline_results/masks.npz` | **current** masks — key `labels` `(T,H,W)` int32, 0=bg, IDs track-consistent across frames |
| `pipeline_results/masks_reviewed.npz` | masks after manual review, before cleaning |
| `pipeline_results/masks_precleanup.npz` | backup just before the cleaning pass — also carries `fusion_source_stack` (per-pixel detection source: 1=DIC, 2=Cy5, 3=both) |
| `pipeline_results/masks_original.npz` | raw detector output, before any human edits (also carries `fusion_source_stack`) |
| `pipeline_results/divisions.json` | detected cell-division events (parent → daughters, frame) |
| `pipeline_results/RUN_METADATA.json` | provenance: pipeline name, n_frames, n_tracks, runtime, etc. |
| `per_cell.csv` | one row per tracked cell — state-stratified metrics (see below) |
| `analysis.json` | per-cell records (machine-readable form of `per_cell.csv`) |
| `recording_summary.json` | this recording reduced to one row of aggregate metrics |
| `<label>.cellscope` | CellScope project file (drag-loads the recording + masks into its GUI for editing) |

`per_cell.csv` columns include `cell_id, first_frame, frames_tracked,
parent_id, division_frame, frac_rounded, frac_spread, n_frames_edge,
frac_in_view`, and **per-state** motility/shape metrics
(`mean_speed_{rounded,spread}`, `persistence_*`, `straightness_*`,
`mean_area_um2_*`, `mean_circularity_*`, …). Edge-truncated cell-frames are
excluded from shape/state metrics but still counted/tracked.

---

## How the masks were produced

The `pipeline` field in `RUN_METADATA.json` reads
**`unified_detection.detect_recording (auto)`**. The masks are the output of
that pipeline, **then manually reviewed and cleaned** (the `masks_*.npz`
variants above are the audit trail). Full detail lives in CellScope's
`docs/pipeline_description.md`; the summary:

**1 — Detection (per frame).** Cellpose-SAM (`cpsam`, a Vision-Transformer
Cellpose) on the DIC channel, **auto-routed** per recording: a probe samples
11 frames and uses the 75th-percentile cell count — < 1.5 → `cpsam_dic`
(DIC fine-tune, tighter on isolated cells); ≥ 1.5 → raw `cpsam` (handles
touching cells, which `cpsam_dic` tends to merge). Optionally union-refined
with **DeepSea** (a brightfield/phase time-lapse segmentation model).

**2 — Tracking.** Detections are linked across frames by a Hungarian
assignment into track-consistent IDs (the integer labels you see), with cell
**division** detection (recorded in `divisions.json`).

**3 — Gap fill.** Where a track has internal gaps (missed detections), a
four-phase cascade recovers the cell: TTA re-detection → a CP3/MedSAM/DeepSea
fallback → **SAM2 video propagation** (for cells that retract/dim) → simple
mask translation. Propagated frames are tagged so they can be distinguished
from real detections.

**4 — Cy5 filter.** A `persistence_guard` step uses the Cy5 channel to drop
spurious/non-persistent objects (multichannel recordings only).

**5 — Manual review + cleaning.** Each recording's masks were inspected and
corrected in the CellScope editor (`masks_reviewed.npz`), then a hole-fill +
despeckle cleaning pass produced the final `masks.npz` (`masks_precleanup.npz`
is the pre-cleaning backup). All 48 recordings were reviewed.

Detection ran at CellScope's pipeline **defaults** (no per-recording
parameter overrides); recordings were downsampled to ~1024 px for detection
and labels upscaled back. Exact params, software versions, and git commit for
each run are in that recording's `RUN_METADATA.json`.

> **Scale caveat:** trust the **`.ome.json`** for `um_per_px` (0.6523) and
> `time_interval_min` (10). Some `RUN_METADATA.json` files carry placeholder
> `um_per_px: 1.0` / `time_interval_min: 1.0` — don't use those for physical
> units.

---

## Aggregate results (`data/results/`)

Produced by CellScope's `ic295_*` comparison scripts (arm-structured stats:
per-arm Kruskal-Wallis + within-arm Bonferroni; recording = experimental
unit):

- `results/compare/` — recording-level: `per_recording.csv`,
  `stats_arms.json`, and plots (`plots_arms/`, `flower_plots/`,
  `motility_stats/`, histograms, …).
- `results/compare_pooled/` — the same at the cell level (pooled).

The headline conclusions (n = 8): the IC295 phenotype is in cell
**shape/state**, not migration — see `compare/motility_stats/REPORT.md` and
CellScope's `SESSION_LOG.md` for the full write-up.

---

## Ground truth (`data/gt/`)

Hand-labelled masks used to validate detection (`ic295_gt_full/`,
`legacy_gt/`). Treat these as the reference standard when assessing detection
quality; do not overwrite them.

---

*Authoritative source for anything pipeline-related: the CellScope repo
(`docs/pipeline_description.md`, `CLAUDE.md`, `ic295_analysis/README.md`).*
