"""Documentation for every analysis metric — what it indicates + how it's
calculated. One GUI-free source that powers the Help ▸ Metrics reference dialog
and the GUI tooltips, so descriptions never drift from the code.
"""
from __future__ import annotations

# key -> (what it indicates, how it is calculated)
METRICS = {
    "area": ("Cell footprint size.",
             "Pixel count of the mask × (µm/px)²."),
    "perimeter": ("Boundary length.",
                  "Crofton estimate from the mask boundary (matches "
                  "scikit-image), × µm/px."),
    "circularity": ("How round the outline is (1 = perfect circle).",
                    "4π·area / perimeter²."),
    "eccentricity": ("Elongation of the best-fit ellipse (0 = circle, →1 = line).",
                     "√(1 − minor²/major²) from the second central moments."),
    "aspect_ratio": ("Elongation (long vs short axis).",
                     "major_axis / minor_axis of the second-moment ellipse."),
    "solidity": ("Convexity by area (1 = convex; lower = ruffled / concave).",
                 "area / convex-hull area (SciPy hull of the mask pixels)."),
    "convexity": ("Boundary roughness/ruffling (≤1; lower = spiky/ruffled).",
                  "convex-hull perimeter / actual perimeter — perimeter-based, far "
                  "more sensitive to fine membrane ruffling than solidity."),
    "rel_area": ("Footprint collapse vs the cell's own spread size (scale-free).",
                 "area / the cell's 90th-percentile area."),
    "major_axis": ("Length of the long axis of the fitted ellipse.",
                   "4·√(largest second-moment eigenvalue) × µm/px."),
    "minor_axis": ("Length of the short axis of the fitted ellipse.",
                   "4·√(smallest second-moment eigenvalue) × µm/px."),
    "orientation": ("Angle of the long axis (radians).",
                    "½·atan2(2·µ11, µ20−µ02) from central moments."),
    "extent": ("Fraction of the bounding box filled.",
               "area / (bbox height × width)."),
    "equiv_diameter": ("Diameter of a circle with the same area.",
                       "√(4·area/π) × µm/px."),
    "state_code": ("Cell state (0 unknown · 1 spread · 2 rounded · 3 edge).",
                   "Rounded if area ≤ 960 µm² AND eccentricity ≤ 0.85 (CellScope "
                   "IC295 rule); edge-truncated → edge; too small → unknown."),
    "shape_mode": ("VAMPIRE shape-mode cluster id.",
                   "Aligned radial contour signatures across the recording → PCA "
                   "→ K-means; this cell-frame's cluster (mode 0 = most common)."),
    "speed": ("Instantaneous migration speed.",
              "Centroid step distance between consecutive frames ÷ frame "
              "interval (µm/min)."),
    "displacement_from_start": ("Straight-line distance from the first position.",
                                "‖centroid(t) − centroid(first)‖ × µm/px."),
    "turning_angle": ("Change of direction between steps (radians).",
                      "Signed angle between consecutive centroid step vectors."),
    "iou_prev": ("Mask overlap with the previous frame (tracking stability).",
                 "intersection / union of the cell mask at t and t−1."),
    "area_change": ("Relative frame-to-frame area change (quality flag).",
                    "|area(t) − area(t−1)| / area(t−1)."),
    "nn_dist": ("Distance to the nearest other cell (crowding).",
                "Minimum centroid-to-centroid distance to any other cell in the "
                "frame × µm/px."),
    "n_neighbors": ("Local crowding.",
                    "Number of other cells whose centroid is within 50 µm."),
    "contact_fraction": ("How much of the cell's membrane touches another cell.",
                         "Boundary pixels within 1.5 px of another cell ÷ the cell's "
                         "boundary pixels (0 = free, 1 = fully engaged). Actual mask "
                         "adjacency — distinct from the centroid-distance nn_dist."),
    "max_contact_fraction": ("The single largest cell–cell interface.",
                             "Max over partners of (shared boundary px ÷ boundary px); "
                             "the point-vs-extensive discriminator."),
    "n_contacts": ("Number of other cells physically touching this one.",
                   "Distinct cells with ≥2 shared boundary pixels (within 1.5 px)."),
    "contact_length": ("Length of the cell–cell interface.",
                       "Contacting boundary pixels × µm/px (interface extent)."),
    "contact_state": ("Contact class: free / point / extensive.",
                      "From max_contact_fraction: free (no contact), point (a small "
                      "contact < 25% of the boundary) or extensive (≥ 25%)."),
    "frac_in_contact": ("Fraction of a cell's time in contact with any other cell.",
                        "Frames classed point or extensive ÷ all present frames."),
    "frac_point_contact": ("Fraction of time in a small (point) contact.",
                           "point-class frames ÷ all present frames."),
    "frac_extensive_contact": ("Fraction of time in an extensive contact.",
                               "extensive-class frames ÷ all present frames."),
    "n_contact_events": ("How many distinct contact episodes the cell has.",
                         "Contiguous in-contact runs over its track (a frame gap "
                         "ends a run) — contact formation/breakage frequency."),
    "contact_duration": ("Average length of a contact episode.",
                         "Mean in-contact run length × frame interval (min)."),
    "contact_events": ("Contact formation rate.",
                       "Number of contact episodes ÷ the cell's tracked time."),
    "frac_rounded": ("Fraction of a cell's classifiable time spent rounded.",
                     "rounded frames / (rounded + spread frames); edge-truncated "
                     "and undefined frames are excluded from the denominator."),
    "frac_spread": ("Fraction of a cell's classifiable time spent spread.",
                    "spread frames / (rounded + spread frames)."),
    "frames_tracked": ("How many frames a cell is present (track length).",
                       "Count of frames where the cell's mask is non-empty."),
    "n_cells": ("Number of tracked cells in the recording.",
                "Distinct positive label IDs present in ≥1 frame."),
    "border_dist": ("Distance from the cell to the nearest image edge "
                    "(field-of-view position / edge-proximity QC).",
                    "min(x, y, W−1−x, H−1−y) of the centroid × µm/px; the "
                    "`min_…` column is the closest the cell ever comes to a "
                    "border, the `mean_…` column averages over its frames."),
}

# dynamic per-channel metric prefixes
PREFIX = {
    "intensity_": ("Mean image intensity inside the cell for this channel "
                   "(e.g. SiR-actin Cy5 cortical signal).",
                   "Mean of the channel's pixel values within the mask."),
    "membrane_contrast_": ("Edge/membrane contrast for this channel "
                           "(boundary quality / cortical enrichment).",
                           "|mean inside-ring − mean outside-ring| intensity "
                           "across the boundary."),
    "boundary_grad_": ("Edge sharpness for this channel (boundary confidence).",
                       "Mean |∇(blurred image)| sampled along the contour — a "
                       "derivative on the boundary line, distinct from the "
                       "inside/outside intensity step."),
    "membrane_score_": ("Composite membrane-fidelity score for this channel.",
                        "0.15·intensity-contrast + 0.85·max(texture-contrast, 0), "
                        "where texture = inside − outside local-std."),
}

# track / motion / edge summaries (reported, not per-frame plots)
EXTRA = {
    "straightness": ("Directional persistence by net/path (speed-biased).",
                     "net displacement / total path length (0 random … 1 "
                     "straight). Speed-biased — prefer the autocorrelation "
                     "persistence."),
    "persistence (dir. autocorr)": ("Speed-unbiased directional persistence.",
                                    "Mean cosine between consecutive step-"
                                    "direction unit vectors (lag-1)."),
    "MSD": ("Mean squared displacement vs lag.",
            "⟨‖r(t+τ)−r(t)‖²⟩ over all t, per lag τ; α/D from MSD = 4D·τ^α "
            "(α≈1 Brownian, >1 directed, <1 confined)."),
    "Fürth fit (D, persistence time)": ("Persistent-random-walk migration model.",
        "Fit MSD = 4D·(t − P·(1 − e^(−t/P))) → motility coefficient D and a "
        "directional-memory persistence time P (minutes)."),
    "speed_isolated / speed_crowded / frac_isolated": ("Contact effect on speed.",
        "Mean step speed split by neighbour count at the step (0 vs ≥1 neighbours), "
        "and the fraction of frames with no neighbour."),
    "track_quality": ("Composite 0–1 track-reliability score.",
        "0.5·frames-present + 0.3·(1 − area CV) + 0.2·(path / 50 µm)."),
    "area_stability": ("Area-jump QC.",
        "area CV, max/min ratio, and # of >30% consecutive area changes."),
    "run_and_tumble": ("Directed runs vs reorientation tumbles.",
        "A step turning > 60° from the previous one is a tumble; the directed "
        "segments between tumbles are runs. n_runs, mean run length (steps) / duration "
        "(min), tumble rate (per min) + mean tumble angle — a sensitive persistence "
        "readout that resolves run length from turn frequency."),
    "track_jumps": ("Track-continuity QC (suspected ID swaps).",
        "Steps whose length exceeds 5× the cell's median step — abnormal displacement "
        "that suggests a tracking error / ID swap. n_track_jumps, frac_track_jumps and "
        "the max single step."),
    "edge velocity": ("Membrane protrusion (+) / retraction (−) speed.",
                      "Per-angular-sector change in boundary radius about the "
                      "mid-centroid ÷ interval (µm/min)."),
    "ruffling": ("Edge activity.",
                 "Mean over sectors of the temporal std of edge velocity."),
    "edge_front_velocity": ("Edge velocity at the cell front (migration direction).",
        "Mean edge velocity in the forward cone after rotating each frame-pair's "
        "sectors to the cell's migration direction (+protrusion; µm/min). Includes "
        "migration-driven leading-edge advance."),
    "edge_rear_velocity": ("Edge velocity at the cell rear.",
        "Mean edge velocity in the backward cone (−retraction; µm/min)."),
    "edge_polarity_index": ("Front−rear morphodynamic polarity.",
        "front_velocity − rear_velocity: large when the front protrudes and the rear "
        "retracts. Correlated with migration speed — read with the speed-adjusted OLS."),
    "edge_rear_retraction_fraction": ("How concentrated retraction is at the rear.",
        "Σ rear-sector retraction ÷ Σ all retraction (0–1) — a spatial concentration "
        "(more speed-independent than the magnitude); the PIEZO1 rear-retraction "
        "signature (GOF / YODA1 ↑ rear retraction)."),
    "edge_piezo_lag": ("Does the fluorescence lead or follow edge motion?",
        "Frame lag of the strongest edge-velocity ↔ rectangle-intensity correlation: "
        "peak_lag < 0 = the signal enriches BEFORE the movement (leads it, e.g. actin "
        "before protrusion), > 0 = follows; peak_r is that correlation."),
    "edge_piezo_corr": ("Edge-movement ↔ fluorescence-intensity coupling (e.g. "
                        "tagged PIEZO1). +ve = the channel is brighter where the "
                        "edge protrudes; −ve = brighter where it retracts.",
                        "Pearson r between the local edge displacement (per-sector "
                        "radial velocity) and the mean fluorescence in a rectangle "
                        "reaching into the cell from that edge point, over all "
                        "(frame, sector) — the faithful `cell_edge_analysis` "
                        "method. `edge_piezo_slope` is the regression slope; "
                        "`piezo_protr_minus_retr` is the mean intensity at "
                        "protruding minus retracting points."),
}


_UNIT_SUFFIXES = ("_um2_per_min", "_px2_per_min", "_um_per_min", "_px_per_min",
                  "_um_per_frame", "_px_per_frame", "_um2", "_px2", "_um", "_px")


def _split_state(col: str):
    """Peel a trailing per-state suffix → (base, 'rounded'|'spread'|None)."""
    for s in ("_rounded", "_spread"):
        if col.endswith(s):
            return col[: -len(s)], s[1:]
    return col, None


def column_units(col: str) -> str:
    """Display units for an aggregated comparison column (from its suffix).
    Dimensionless (ratios/scores) → ''. State-segmented columns
    (``…_spread`` / ``…_rounded``) use their base metric's units."""
    c, _ = _split_state(col)
    for per, lab in (("_per_min", "/min"), ("_per_frame", "/frame")):
        if c.endswith(per):
            base = c[: -len(per)]
            if base.endswith("_um2"):
                return "µm²" + lab
            if base.endswith("_um"):
                return "µm" + lab
            if base.endswith("_px"):
                return "px" + lab
            return "1" + lab
    if "area" in c and c.endswith("_px"):
        return "px²"
    for suf, u in (("_um2", "µm²"), ("_px2", "px²"), ("_um", "µm"), ("_px", "px")):
        if c.endswith(suf):
            return u
    if c.endswith("_min") or "persistence_time" in c:
        return "min"
    if c.startswith("frac_") or c == "track_quality":
        return ""                       # fraction / 0–1 score
    if (c == "n_cells" or c.startswith("n_") or "n_neighbors" in c
            or "n_contacts" in c):
        return "count"
    if "frames" in c:
        return "frames"
    return ""


def column_label(col: str) -> str:
    """Human-readable metric name (drops the unit suffix; underscores → spaces;
    a per-state subset is shown as ``… [spread]`` / ``… [rounded]``)."""
    c, st = _split_state(col)
    for suf in _UNIT_SUFFIXES:
        if c.endswith(suf):
            c = c[: -len(suf)]
            break
    else:
        for suf in ("_per_min", "_per_frame", "_min"):   # bare rate / time suffixes
            if c.endswith(suf):
                c = c[: -len(suf)]
                break
    lab = c.replace("_", " ").strip()
    return f"{lab} [{st}]" if st else lab


def axis_label(col: str) -> str:
    """`label (units)` for a plot axis / table header (units omitted if none)."""
    u = column_units(col)
    lab = column_label(col)
    return f"{lab} ({u})" if u else lab


def doc(key: str):
    """(what, how) for a metric key (handles per-channel prefixes)."""
    if key in METRICS:
        return METRICS[key]
    for pre, val in PREFIX.items():
        if key.startswith(pre):
            return val
    return EXTRA.get(key, ("", ""))


def tooltip(key: str) -> str:
    what, how = doc(key)
    return f"{what}\nHow: {how}" if what else ""


# ---- comparison columns (aggregated + per-state) --------------------------
_KEY_ALIASES = {
    "speed": "speed", "mean_speed": "speed",
    "persistence": "persistence (dir. autocorr)",
    "persistence_dir_autocorr": "persistence (dir. autocorr)",
    "straightness": "straightness",
    "net_disp": "MSD", "total_path": "MSD",
    "furth_d": "Fürth fit (D, persistence time)",
    "persistence_time": "Fürth fit (D, persistence time)",
    "area_cv": "area_stability", "area_max_min_ratio": "area_stability",
    "n_large_area_jumps": "area_stability",
    "speed_isolated": "speed_isolated / speed_crowded / frac_isolated",
    "speed_crowded": "speed_isolated / speed_crowded / frac_isolated",
    "frac_isolated": "speed_isolated / speed_crowded / frac_isolated",
    "min_border_dist": "border_dist", "mean_border_dist": "border_dist",
    "nn_dist": "nn_dist", "mean_nn_dist": "nn_dist", "median_nn_dist": "nn_dist",
    "edge_piezo_slope": "edge_piezo_corr",
    "piezo_protr_minus_retr": "edge_piezo_corr",
    "edge_piezo_peak_lag": "edge_piezo_lag", "edge_piezo_peak_r": "edge_piezo_lag",
    "n_runs": "run_and_tumble", "run_steps": "run_and_tumble",
    "run_duration": "run_and_tumble", "tumble_rate": "run_and_tumble",
    "frac_tumble": "run_and_tumble", "tumble_angle_deg": "run_and_tumble",
    "n_track_jumps": "track_jumps", "max_step": "track_jumps",
    "frac_track_jumps": "track_jumps",
}


def _metric_key(col: str) -> str:
    """Resolve an aggregated / per-state comparison column to a doc key."""
    base, _ = _split_state(col)
    if base.startswith("mean_"):
        base = base[5:]
    elif base.startswith("median_"):
        base = base[7:]
    for suf in _UNIT_SUFFIXES:
        if base.endswith(suf):
            base = base[: -len(suf)]
            break
    else:
        for suf in ("_per_min", "_per_frame", "_min"):
            if base.endswith(suf):
                base = base[: -len(suf)]
                break
    base = base.strip("_").lower()
    return _KEY_ALIASES.get(base, base)


def comparison_doc(col: str):
    """(what, how) for a Comparison-window column — resolves the base metric and
    annotates the per-state subset + recording-as-unit aggregation."""
    base, state = _split_state(col)
    what, how = doc(_metric_key(col))
    if not what:
        what = column_label(col)
    notes = []
    if state:
        notes.append(f"Measured over the cell's <b>{state}</b> frames only "
                     "(state-segmented — matches the original analysis).")
    if base.startswith("mean_"):
        notes.append("Per-cell mean, then averaged across recordings "
                     "(recording = unit).")
    elif base.startswith("median_"):
        notes.append("Per-cell median, then averaged across recordings.")
    return what, (how + (" " + " ".join(notes) if notes else ""))


def comparison_tooltip(col: str) -> str:
    what, how = comparison_doc(col)
    u = column_units(col)
    head = f"{column_label(col)}" + (f" ({u})" if u else "")
    return f"{head}\n{what}\nHow: {how}" if what else head


_COMPARISON_HTML = """
<h3>Cross-recording comparison (Comparison window)</h3>
<p><b>Unit of analysis = the recording.</b> Cells in one recording share a field
of view / dish, so they are not independent; every test treats the
<i>recording</i> as the replicate. A metric's per-recording value is the mean
over its cells; conditions are then compared recording-to-recording.</p>
<p><b>Whole-track vs state-segmented metrics.</b> A plain metric (e.g.
<i>mean_speed</i>, <i>mean_area_um2</i>) is averaged over a cell's whole track,
mixing its rounded and spread phases. Columns suffixed <b>_spread</b> /
<b>_rounded</b> are computed <i>separately over the frames in that state</i> —
this matches the original CellScope analysis (a whole-track average conflates how
a cell behaves in a state with how long it spends there). Speed is a per-step
value taken at the step's start frame, with edge-touching steps dropped and a
15&nbsp;µm/min cap; persistence and straightness use contiguous same-state
segments (≥5 frames). Edge-truncated frames are excluded throughout.</p>
<p><b>Filters.</b> min frames tracked, min track-quality, min cells/recording
(drops low-N recordings), and a cell-state filter (keep cells that are mostly
spread / rounded).</p>
<p><b>Statistics.</b> Per arm: omnibus Kruskal–Wallis across the arm's groups,
then Mann–Whitney U of each treatment vs the arm's control with Bonferroni
correction; Cohen's d effect size; and an optional covariate-adjusted OLS
(treatment effect after frac_spread + density). A vehicle/batch pair test and a
condition ensemble MSD (mean±SEM or median+bootstrap-CI) are also reported.</p>
<p><b>Ranked report.</b> The Stats tab's <i>Ranked report…</i> button lists
<i>every</i> group-vs-group pair for the current metric, ordered by the likelihood
of a significant difference (smallest p first) — Mann–Whitney U + Cohen's d with a
Bonferroni correction over the pairs. Unlike the per-contrast table above (which is
design-driven: control vs test within arms), this scans <i>all</i> group pairs so
you see which groups differ most on a feature. Exportable to CSV.</p>
<p><b>What gets computed.</b> Config ▸ Settings ▸ <i>Comparison analysis</i> toggles
the heavier optional families — cell–cell contacts, state-segmented metrics,
solidity — to speed the per-recording pass; changing a toggle recomputes.</p>
"""

_CONTACTS_HTML = """
<h3>Cell–cell contact (shared membrane)</h3>
<p>Distinct from nearest-neighbour <i>proximity</i> (centroid distance): a cell is
<b>in contact</b> where its mask boundary is adjacent (within ~1.5&nbsp;px) to
another cell's. Per frame each cell gets a <b>contact_fraction</b> (share of its
boundary engaged), an interface <b>contact_length</b>, <b>n_contacts</b> (cells
touched), and a class — <b>free</b> / <b>point</b> (a small contact &lt;25% of the
boundary) / <b>extensive</b> (≥25%). Over a track: time-in-class fractions
(frac_in_contact / _point / _extensive) and <b>episode dynamics</b>
(n_contact_events, mean_contact_duration, formation rate). The <b>Cell contacts</b>
overlay draws the touching boundary pixels (blue point / red extensive), colour-by
offers <i>contact fraction / count / class</i>, and <b>Export CSV</b> writes a
<b>cell-pair</b> table — which cells touch, when (frames), and the degree.</p>
"""


def as_html() -> str:
    def section(title, items):
        out = [f"<h3>{title}</h3>"]
        for k, (what, how) in items:
            out.append(f"<p><b>{k}</b> — {what}<br>"
                       f"<i>How:</i> {how}</p>")
        return "".join(out)
    return ("<html><body>"
            + section("Per-frame metrics", METRICS.items())
            + section("Per-channel metrics (one per image channel)",
                      [(p + "&lt;channel&gt;", v) for p, v in PREFIX.items()])
            + section("Track / motion / edge summaries", EXTRA.items())
            + _CONTACTS_HTML
            + _COMPARISON_HTML
            + "</body></html>")
