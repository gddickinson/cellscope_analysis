"""Shared config for the IC293 vs IC295-single-cell-crop treatment comparison
(scripts/compare_datasets.py). Study-specific; not part of the GUI/analysis package.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Where the cellscope result trees live (override on another machine).
CELLSCOPE = os.environ.get("CELLSCOPE_ROOT", "/Users/george/claude_test/cellscope")
OUT = os.path.join(REPO, "analysis_out", "ic293_vs_ic295")

DATASETS = [
    {"key": "ic293", "label": "IC293 (manual crops)",
     "root": os.path.join(CELLSCOPE, "ic293_analysis", "by_condition")},
    {"key": "ic295scc", "label": "IC295 (programmatic crops)",
     "root": os.path.join(CELLSCOPE, "ic295_single-cell-crop_analysis", "by_condition")},
]

# PIEZO1 study design: genetic (WT control) + drug (DMSO vehicle control) arms.
ARMS = {"genetic": {"control": "WT", "conditions": ["WT", "GOF", "KO"]},
        "drug": {"control": "DMSO", "conditions": ["DMSO", "Y1", "OT"]}}

# (label, control, test) — the within-arm treatment contrasts + the batch/vehicle pair.
CONTRASTS = [("genetic", "WT", "GOF"), ("genetic", "WT", "KO"),
             ("drug", "DMSO", "Y1"), ("drug", "DMSO", "OT"),
             ("batch", "DMSO", "WT")]

COND_ORDER = ["WT", "GOF", "KO", "DMSO", "Y1", "OT"]
COND_COLOR = {"WT": "#1f77b4", "GOF": "#2ca02c", "KO": "#d62728",
              "DMSO": "#7f7f7f", "Y1": "#9467bd", "OT": "#ff7f0e"}

# Drop very short tracks (cell present only briefly) — motion metrics are noisy there.
MIN_FRAMES = 10

# Permutation counts for the multivariate phenotype (AUC is exact; these only set the
# resolution/cost of the permutation p). Smaller than the GUI's defaults so the whole
# report runs inline in ~1 min instead of being dominated by 8 full permutation nulls.
PERM_LORO = 99
PERM_PMANOVA = 299

# Curated, non-redundant metrics for effect sizes + concordance (interpretable subset
# of the full per-recording table; the multivariate test still uses ALL metrics).
KEY_METRICS = [
    "mean_speed_um_per_min", "net_disp_um", "total_path_um", "straightness",
    "persistence_dir_autocorr", "persistence_time_min", "furth_D_um2_per_min",
    "frac_tumble", "mean_tumble_angle_deg",
    "mean_area_um2", "mean_circularity", "mean_eccentricity", "mean_aspect_ratio",
    "mean_extent", "mean_convexity",
    "frac_rounded", "area_cv", "area_max_min_ratio",
]
# Metrics that get their own per-condition distribution panel in the figures.
PANEL_METRICS = ["mean_speed_um_per_min", "persistence_dir_autocorr", "straightness",
                 "frac_rounded", "mean_circularity", "area_cv"]
