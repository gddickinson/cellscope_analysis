#!/usr/bin/env python
"""Figures for the follow-up investigation (the multivariate finding).

Writes to analysis_out/ (gitignored — derived from private data):
  multivariate_genetic_pca.png  recordings of the genetic arm in PC1-PC2
                                feature space, coloured by condition (WT/KO
                                separate; the effect univariate tests missed)
  ko_fingerprint.png            KO-vs-WT per-feature Cohen's d — what the
                                multivariate signal is made of

    conda run -n cellscope_analysis python scripts/plot_followup.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from maskviewer.analysis import feature_tables as ft
from maskviewer.analysis import multivariate as mv

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "analysis_out")


def pca_plot(df, path):
    conds = ft.ARMS["genetic"]["conditions"]
    dfp = mv.add_shape_score(df)[0]                  # shape→1 score, no double-count
    X, lab = mv._matrix(dfp, conds, features=mv.FEATURES_COMBINED)
    X = X - X.mean(0)
    U, S, Vt = np.linalg.svd(X, full_matrices=False)
    pcs = U[:, :2] * S[:2]
    var = (S ** 2 / (S ** 2).sum())[:2] * 100
    fig, ax = plt.subplots(figsize=(6.4, 5.2))
    for c in conds:
        m = lab == c
        ax.scatter(pcs[m, 0], pcs[m, 1], s=70, color=ft.COND_COLOR[c],
                   edgecolor="#222", label=f"{c} (n={m.sum()})")
    ax.set_xlabel(f"PC1 ({var[0]:.0f}%)")
    ax.set_ylabel(f"PC2 ({var[1]:.0f}%)")
    ax.set_title("Genetic arm — recordings in feature space\n"
                 "KO vs WT: PERMANOVA p=0.004, leave-one-out AUC=0.80")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(path, dpi=140); plt.close(fig)


def fingerprint_plot(df, path):
    dfp = mv.add_shape_score(df)[0]                  # 4 collinear shape feats → 1
    ld = mv.loadings(dfp, "WT", "KO", features=mv.FEATURES_COMBINED,
                     top=len(mv.FEATURES_COMBINED))[::-1]
    feats = [f.replace("_mean", "").replace("mean_", "") for f, _ in ld]
    ds = [d for _, d in ld]
    cols = ["#2ca02c" if f == "shape_roundness" else
            ("#d62728" if d > 0 else "#1f77b4") for f, d in ld]
    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    ax.barh(feats, ds, color=cols)
    ax.axvline(0, color="#222", lw=1)
    ax.set_xlabel("Cohen's d  (KO − WT, recording-level)")
    ax.set_title("KO-vs-WT phenotype fingerprint (de-duplicated: shape→1 score)\n"
                 "spread cells rounder/more compact, less persistent")
    fig.tight_layout(); fig.savefig(path, dpi=140); plt.close(fig)


def main():
    os.makedirs(OUT, exist_ok=True)
    df = ft.recordings()
    pca_plot(df, os.path.join(OUT, "multivariate_genetic_pca.png"))
    fingerprint_plot(df, os.path.join(OUT, "ko_fingerprint.png"))
    print(f"Wrote figures → {OUT}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
