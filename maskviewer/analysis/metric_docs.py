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
    "edge velocity": ("Membrane protrusion (+) / retraction (−) speed.",
                      "Per-angular-sector change in boundary radius about the "
                      "mid-centroid ÷ interval (µm/min)."),
    "ruffling": ("Edge activity.",
                 "Mean over sectors of the temporal std of edge velocity."),
}


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
            + "</body></html>")
