# cellscope_analysis — Session Log

Chronological log of substantive changes. Append an entry for any non-trivial
change. Most recent first.

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
