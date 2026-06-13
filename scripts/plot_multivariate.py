#!/usr/bin/env python
"""Explain-and-illustrate plots for the multivariate KO finding.

Writes to analysis_out/ (gitignored):
  mv_story_panel.png    6-panel walkthrough — why multivariate beats
                        univariate, the held-out separation, ROC, the
                        permutation null, effect across contrasts, fingerprint
  mv_feature_heatmap.png  recordings × z-scored features (genetic arm), KO's
                        coherent shift visible as a column block
  mv_top_pair.png       top-2 fingerprint features: individually overlapping,
                        jointly separable

    conda run -n cellscope_analysis python scripts/plot_multivariate.py
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
_SHORT = lambda f: f.replace("_mean", "").replace("mean_", "")   # noqa: E731
CONTRASTS = [("WT", "KO"), ("WT", "GOF"), ("DMSO", "Y1"), ("DMSO", "OT"),
             ("WT", "DMSO")]


# ---------- individual panel painters (take an Axes) -----------------------
def _panel_why(ax, df):
    uni = mv.univariate_p(df, "WT", "KO")
    uni.sort(key=lambda kv: kv[1])
    names = [_SHORT(f) for f, _ in uni]
    nlp = [-np.log10(max(p, 1e-6)) for _, p in uni]
    ax.barh(names[::-1], nlp[::-1], color="#888")
    ax.axvline(-np.log10(0.05), color="#d62728", ls="--", lw=1.3,
               label="p=0.05 (raw)")
    ax.axvline(-np.log10(0.05 / len(uni)), color="#7a0000", ls=":", lw=1.3,
               label="Bonferroni")
    ax.axvline(-np.log10(0.004), color="#1f77b4", lw=2,
               label="multivariate p=0.004")
    ax.set_xlabel("-log10 p  (WT vs KO)")
    ax.set_title("Why multivariate: no single feature survives correction,\n"
                 "but the joint test does", fontsize=9)
    ax.legend(fontsize=6, loc="lower right")


def _panel_scores(ax, detail, y, conds=("WT", "KO")):
    rng = np.random.default_rng(0)
    for val, c in ((0, conds[0]), (1, conds[1])):
        s = detail["scores"][y == val]
        x = rng.normal(val, 0.05, len(s))
        ax.scatter(x, s, s=45, color=ft.COND_COLOR[c], edgecolor="#222",
                   zorder=3, label=f"{c} (n={len(s)})")
    ax.axhline(0.5, color="#888", ls="--", lw=1)
    ax.set_xticks([0, 1]); ax.set_xticklabels(conds)
    ax.set_ylim(-0.05, 1.05)
    ax.set_ylabel("held-out P(KO)")
    ax.set_title(f"Leave-one-recording-out scores\nAUC={detail['auc']:.2f}, "
                 f"perm p={detail['p']:.3f}", fontsize=9)
    ax.legend(fontsize=7)


def _panel_roc(ax, detail, y):
    from sklearn.metrics import roc_curve
    fpr, tpr, _ = roc_curve(y, detail["scores"])
    ax.plot(fpr, tpr, color="#1f77b4", lw=2.2, label=f"AUC={detail['auc']:.2f}")
    ax.plot([0, 1], [0, 1], color="#888", ls="--", lw=1)
    ax.set_xlabel("false positive rate"); ax.set_ylabel("true positive rate")
    ax.set_title("ROC — KO vs WT (held-out)", fontsize=9)
    ax.legend(fontsize=8, loc="lower right")


def _panel_null(ax, detail):
    ax.hist(detail["perm_aucs"], bins=24, color="#bbb", edgecolor="#888")
    ax.axvline(detail["auc"], color="#d62728", lw=2.4,
               label=f"observed {detail['auc']:.2f}")
    ax.set_xlabel("AUC under label permutation")
    ax.set_ylabel("count")
    ax.set_title(f"Permutation null (p={detail['p']:.3f})\n"
                 "the classifier isn't just overfitting", fontsize=9)
    ax.legend(fontsize=7)


def _panel_contrasts(ax, df):
    labels, aucs, ps, cols = [], [], [], []
    for ctrl, test in CONTRASTS:
        X, lab = mv._matrix(df, [ctrl, test])
        d = mv.loro_detail(X, (lab == test).astype(int), b=499)
        labels.append(f"{test} vs {ctrl}")
        aucs.append(d["auc"]); ps.append(d["p"])
        cols.append(ft.COND_COLOR.get(test if test != "DMSO" else "DMSO"))
    yy = np.arange(len(labels))
    ax.barh(yy, aucs, color=cols, edgecolor="#222")
    ax.axvline(0.5, color="#888", ls="--", lw=1.2, label="chance")
    for i, (a, p) in enumerate(zip(aucs, ps)):
        ax.text(a + 0.01, i, ("*" if p < 0.05 else "ns"), va="center",
                fontsize=9)
    ax.set_yticks(yy); ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis(); ax.set_xlim(0, 1.0); ax.set_xlabel("leave-one-out AUC")
    ax.set_title("Effect across contrasts:\nKO + vehicle separate; drug arm flat",
                 fontsize=9)
    ax.legend(fontsize=7, loc="lower right")


def _panel_fingerprint(ax, df):
    ld = mv.loadings(df, "WT", "KO", top=len(mv.FEATURES))
    feats = [_SHORT(f) for f, _ in ld][::-1]
    ds = [d for _, d in ld][::-1]
    ax.barh(feats, ds, color=["#d62728" if d > 0 else "#1f77b4" for d in ds])
    ax.axvline(0, color="#222", lw=1)
    ax.set_xlabel("Cohen's d (KO − WT)")
    ax.set_title("Fingerprint: KO spread cells rounder,\nless persistent",
                 fontsize=9)


# ---------- standalone figures --------------------------------------------
def heatmap(df, path):
    conds = ft.ARMS["genetic"]["conditions"]
    X, lab = mv._matrix(df, conds)
    ld = mv.loadings(df, "WT", "KO", top=len(mv.FEATURES))
    order = [mv.FEATURES.index(f) for f, _ in ld]          # by |KO-WT effect|
    csort = np.argsort([conds.index(c) for c in lab])
    M = X[csort][:, order].T
    fig, ax = plt.subplots(figsize=(11, 5.4))
    im = ax.imshow(M, aspect="auto", cmap="RdBu_r", vmin=-2.5, vmax=2.5)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([_SHORT(mv.FEATURES[i]) for i in order], fontsize=8)
    ax.set_xticks([])
    x = 0
    for c in conds:
        n = int((lab == c).sum())
        ax.add_patch(plt.Rectangle((x - 0.5, -1.4), n, 0.8, color=ft.COND_COLOR[c],
                                   clip_on=False))
        ax.text(x + n / 2 - 0.5, -1.9, c, ha="center", fontsize=10)
        x += n
    fig.colorbar(im, ax=ax, label="z-score", shrink=0.7)
    ax.set_title("Genetic-arm recordings × features (z-scored, ordered by "
                 "KO-vs-WT effect)\nThe KO shift is modest + noisy per "
                 "recording and spread across features — why it must be "
                 "aggregated (top row, eccentricity, is the strongest single "
                 "axis: WT red → KO blue)", fontsize=10)
    fig.tight_layout(); fig.savefig(path, dpi=140); plt.close(fig)


def top_pair(df, path):
    ld = mv.loadings(df, "WT", "KO", top=2)
    fx, fy = ld[0][0], ld[1][0]
    fig, ax = plt.subplots(figsize=(6.2, 5.6))
    for c in ft.ARMS["genetic"]["conditions"]:
        s = df[df["condition"] == c]
        ax.scatter(s[fx], s[fy], s=70, color=ft.COND_COLOR[c], edgecolor="#222",
                   label=c)
    ax.set_xlabel(_SHORT(fx)); ax.set_ylabel(_SHORT(fy))
    ax.set_title("Top-2 fingerprint features: KO (red) trends to lower "
                 "eccentricity / higher\ncircularity than WT, but overlaps — "
                 "partial per-feature, sharper across all 12", fontsize=9)
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(path, dpi=140); plt.close(fig)


def story_panel(df, path):
    X, lab = mv._matrix(df, ["WT", "KO"])
    y = (lab == "KO").astype(int)
    detail = mv.loro_detail(X, y, b=999)
    fig = plt.figure(figsize=(15.5, 9))
    gs = fig.add_gridspec(2, 3, hspace=0.42, wspace=0.32,
                          left=0.07, right=0.98, top=0.9, bottom=0.08)
    _panel_why(fig.add_subplot(gs[0, 0]), df)
    _panel_scores(fig.add_subplot(gs[0, 1]), detail, y)
    _panel_roc(fig.add_subplot(gs[0, 2]), detail, y)
    _panel_null(fig.add_subplot(gs[1, 0]), detail)
    _panel_contrasts(fig.add_subplot(gs[1, 1]), df)
    _panel_fingerprint(fig.add_subplot(gs[1, 2]), df)
    for ax, L in zip(fig.axes, "ABCDEF"):
        ax.text(-0.12, 1.06, L, transform=ax.transAxes, fontsize=15,
                fontweight="bold")
    fig.suptitle("The multivariate story: KO has a real, classifier-validated "
                 "phenotype that single-feature tests miss "
                 "(PERMANOVA p=0.004, AUC=0.80)", fontsize=13, y=0.97)
    fig.savefig(path, dpi=150); plt.close(fig)


def main():
    os.makedirs(OUT, exist_ok=True)
    df = ft.recordings()
    story_panel(df, os.path.join(OUT, "mv_story_panel.png"))
    heatmap(df, os.path.join(OUT, "mv_feature_heatmap.png"))
    top_pair(df, os.path.join(OUT, "mv_top_pair.png"))
    print(f"Wrote multivariate story plots → {OUT}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
