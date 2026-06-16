"""Configurable analysis options + tunable parameters (the Config window's data).

Split out of `compare_tables.py` (file-size hygiene). Defines the comparison-analysis
family toggles (``COMPARE_OPTIONS``), the numeric tunables (``ANALYSIS_PARAMS``) and the
categorical ones (``ANALYSIS_CHOICES``), plus the readers that pull them from QSettings
and ``apply_analysis_params`` which pushes them onto the analysis-module globals so they
take effect everywhere — comparison + interactive views — by being read at call time
(the analysis functions reference the globals, not bound defaults). ``analysis_params_tag``
folds them into the comparison compute-cache key so a change recomputes.
"""
from __future__ import annotations

from PyQt5 import QtCore

# Comparison-analysis families the Config window toggles (what build_comparison
# computes). Keyed for QSettings ("compare/opt_<key>"); the cache key folds them in,
# so changing a toggle recomputes. Edge↔fluorescence is set by the channel selector.
COMPARE_OPTIONS = [
    ("contacts", "Cell–cell contacts", False,
     "Per-cell contact fraction / count / interface / class + episode dynamics."),
    ("state_segmented", "State-segmented metrics (rounded / spread)", False,
     "Speed / persistence / area split by cell state — the CellScope reproduction."),
    ("solidity", "Solidity (convex hull)", False,
     "area ÷ convex-hull area per frame — slower (a SciPy hull per cell-frame)."),
    ("edge_dynamics", "Edge dynamics (protrusion / retraction / polarity)", False,
     "Per-cell membrane protrusion/retraction summary + events + front–rear "
     "polarity — slowest (a radial edge-velocity kymograph per cell)."),
    ("cil", "Contact-inhibition of locomotion (CIL)", False,
     "Per-cell speed free-vs-in-contact, speed change at contact onset, and "
     "velocity alignment with contacting neighbours."),
    ("fluor_metrics", "Fluorescence intensity + membrane (per channel)", False,
     "Per-cell mean intensity + membrane score / boundary gradient / contrast for "
     "every channel (e.g. SiR-actin / tagged-PIEZO1 level + cortical enrichment)."),
    ("shape_modes", "Shape-mode usage (VAMPIRE)", False,
     "Per-cell dominant shape mode, # modes visited, mode entropy + switch rate."),
]


def compare_options(settings=None) -> dict:
    """``{key: bool}`` comparison-analysis toggles from QSettings (Config window)."""
    s = settings or QtCore.QSettings("cellscope_analysis", "viewer")
    return {k: s.value(f"compare/opt_{k}", d, type=bool)
            for k, _label, d, _tip in COMPARE_OPTIONS}


# Numeric tunables (Config ▸ Analysis parameters). Each:
# (key, label, default, min, max, decimals, section, tooltip).
ANALYSIS_PARAMS = [
    ("nn_radius", "Neighbour radius (µm)", 50.0, 1.0, 2000.0, 0, "Neighbours & contact",
     "Cells within this centroid distance count as neighbours (n_neighbors / crowding "
     "/ density-stratified speed)."),
    ("contact_gap", "Contact gap tolerance (px)", 1.5, 0.5, 10.0, 1,
     "Neighbours & contact",
     "Max boundary-pixel separation treated as a cell–cell contact (touching masks "
     "sit ~1 px apart)."),
    ("extensive_frac", "Extensive-contact threshold", 0.25, 0.05, 1.0, 2,
     "Neighbours & contact",
     "A neighbour interface ≥ this fraction of the cell's boundary is 'extensive' "
     "(else 'point')."),
    ("contact_min_px", "Min contact size (px)", 2.0, 1.0, 50.0, 0,
     "Neighbours & contact",
     "Boundary-pixel contacts smaller than this are ignored (noise floor for cell–cell "
     "touching)."),
    ("rounded_area_um2", "Rounded: max area (µm²)", 960.0, 50.0, 10000.0, 0,
     "State classification (rounded vs spread)",
     "A cell is 'rounded' only if its footprint is ≤ this AND not elongated; drives "
     "state / frac_rounded / all state-segmented metrics."),
    ("rounded_ecc", "Rounded: max eccentricity", 0.85, 0.1, 1.0, 2,
     "State classification (rounded vs spread)",
     "A cell is 'rounded' only if its eccentricity is ≤ this (and small)."),
    ("state_min_area_px", "Min cell area (px)", 200.0, 0.0, 5000.0, 0,
     "State classification (rounded vs spread)",
     "Cells smaller than this footprint are 'unknown' (too small to classify, and "
     "excluded from shape-mode fitting)."),
    ("shape_n_modes", "Number of shape modes", 5, 2, 12, 0, "Shape modes (VAMPIRE)",
     "How many clusters the VAMPIRE shape-mode model uses (re-fits + re-caches)."),
    ("run_tumble_turn_deg", "Run/tumble turn angle (°)", 60.0, 5.0, 175.0, 0, "Motion",
     "Turning angle above which a step counts as a reorientation 'tumble' (run-and-"
     "tumble decomposition / tumble rate)."),
    ("jump_factor", "Jump-step factor (× median)", 5.0, 1.5, 50.0, 1, "Motion",
     "A step longer than this × the median step length is flagged as a tracking jump "
     "(track-quality QC)."),
    ("edge_front_deg", "Front/rear half-cone (°)", 60.0, 10.0, 90.0, 0, "Edge dynamics",
     "Half-angle from the migration direction defining 'front' vs 'rear' edge sectors "
     "(polarity index / rear-retraction fraction)."),
    ("edge_temporal_sigma", "Kymograph time smoothing (σ frames)", 1.0, 0.0, 5.0, 1,
     "Edge dynamics",
     "Gaussian σ (frames) applied along time to the edge-velocity kymograph (0 = none)."),
    ("edge_angular_window", "Kymograph angular window (sectors)", 5.0, 3.0, 15.0, 0,
     "Edge dynamics",
     "Savitzky-Golay window (odd, in sectors) smoothing each frame's boundary radius "
     "around the cell."),
    ("edge_rect_depth_px", "Sampling rectangle depth (px)", 12.0, 2.0, 60.0, 0,
     "Edge ↔ fluorescence sampling",
     "How far each edge-intensity sampling rectangle reaches inward from the boundary."),
    ("edge_rect_width_px", "Sampling rectangle width (px)", 7.0, 2.0, 60.0, 0,
     "Edge ↔ fluorescence sampling",
     "Width of each edge-intensity sampling rectangle along the boundary."),
    ("edge_min_coverage", "Sampling min in-cell coverage", 0.3, 0.0, 1.0, 2,
     "Edge ↔ fluorescence sampling",
     "A sampling rectangle is dropped if less than this fraction of it lies inside the "
     "cell mask."),
    ("edge_rect_search_angles", "Rectangle search angles", 18.0, 4.0, 72.0, 0,
     "Edge ↔ fluorescence sampling",
     "For the 'search' positioning method: how many orientations (0–360°) to try when "
     "recovering a low-coverage rectangle (more = finer, slower)."),
    ("cil_window", "CIL speed window (frames)", 3.0, 1.0, 20.0, 0,
     "Contact inhibition (CIL)",
     "± frames around a contact event over which the speed change is measured "
     "(negative = slowing as contact forms)."),
]

# Categorical (combo) analysis parameters: (key, label, default, choices, section, tip)
ANALYSIS_CHOICES = [
    ("edge_rect_rotation", "Rectangle positioning", "none",
     ["none", "flip", "search"], "Edge ↔ fluorescence sampling",
     "How an edge-intensity sampling rectangle is placed when the straight inward one "
     "falls below the min coverage (concave edge / image border): 'none' = inward only; "
     "'flip' = also try the 180° opposite; 'search' = rotate through the search angles "
     "and keep the best in-cell coverage (after the original cell_edge_analysis)."),
]


def analysis_params(settings=None) -> dict:
    s = settings or QtCore.QSettings("cellscope_analysis", "viewer")
    return {k: float(s.value(f"analysis/{k}", d, type=float))
            for k, _l, d, *_ in ANALYSIS_PARAMS}


def analysis_choices(settings=None) -> dict:
    """``{key: str}`` for the categorical (combo) analysis parameters."""
    s = settings or QtCore.QSettings("cellscope_analysis", "viewer")
    return {k: str(s.value(f"analysis/{k}", d, type=str))
            for k, _l, d, *_ in ANALYSIS_CHOICES}


def apply_analysis_params(settings=None):
    """Push the configured analysis parameters onto the analysis module globals so
    every computation (comparison + interactive) reads them at call time."""
    from ..analysis import (neighbors, contacts, state, shape_modes, motion,
                            edge_dynamics, edge_intensity, cil)
    p = analysis_params(settings)
    neighbors.DEFAULT_RADIUS_UM = p["nn_radius"]
    contacts.DEFAULT_GAP_PX = p["contact_gap"]
    contacts.EXTENSIVE_FRAC = p["extensive_frac"]
    contacts.MIN_CONTACT_PX = int(p["contact_min_px"])
    state.ROUNDED_AREA_UM2 = p["rounded_area_um2"]
    state.ROUNDED_ECC = p["rounded_ecc"]
    state.MIN_AREA_PX = int(p["state_min_area_px"])
    shape_modes.N_MODES = int(p["shape_n_modes"])
    motion.RUN_TUMBLE_TURN_DEG = p["run_tumble_turn_deg"]
    motion.JUMP_FACTOR = p["jump_factor"]
    edge_dynamics.POLARITY_FRONT_DEG = p["edge_front_deg"]
    edge_dynamics.TEMPORAL_SIGMA = p["edge_temporal_sigma"]
    edge_dynamics.ANGULAR_SG_WINDOW = int(p["edge_angular_window"])
    edge_intensity.DEPTH_PX = int(p["edge_rect_depth_px"])
    edge_intensity.WIDTH_PX = int(p["edge_rect_width_px"])
    edge_intensity.MIN_COVERAGE = p["edge_min_coverage"]
    edge_intensity.RECT_SEARCH_ANGLES = int(p["edge_rect_search_angles"])
    cil.DEFAULT_WINDOW = int(p["cil_window"])
    edge_intensity.RECT_ROTATION = analysis_choices(settings)["edge_rect_rotation"]


def analysis_params_tag(settings=None) -> str:
    """Cache-key fragment for the analysis params (only when non-default) so the
    comparison recomputes when they change."""
    p = analysis_params(settings)
    ch = analysis_choices(settings)
    nums_default = all(abs(p[k] - d) < 1e-9 for k, _l, d, *_ in ANALYSIS_PARAMS)
    ch_default = all(ch[k] == d for k, _l, d, *_ in ANALYSIS_CHOICES)
    if nums_default and ch_default:
        return ""
    nums = "_".join(f"{p[k]:g}" for k, *_ in ANALYSIS_PARAMS)
    cats = "_".join(ch[k] for k, *_ in ANALYSIS_CHOICES)
    return f"_p{nums}_{cats}"
