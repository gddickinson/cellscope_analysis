"""Figures for the dataset comparison (matplotlib/Agg → PNG). Each function takes
already-computed inputs and writes one figure; the orchestrator wires them up.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from maskviewer.analysis import compare, metric_docs  # noqa: E402
import ds_config as cfg  # noqa: E402

DS_KEYS = [d["key"] for d in cfg.DATASETS]
DS_LABEL = {d["key"]: d["label"] for d in cfg.DATASETS}
DS_MARKER = {DS_KEYS[0]: "o", DS_KEYS[1]: "s"}


def _vals(df, cond, metric):
    v = df.loc[df["condition"] == cond, metric].to_numpy(float)
    return v[np.isfinite(v)]


def _short(metric):
    return metric_docs.column_label(metric)


# ---------------------------------------------------------------- distributions
def fig_distributions(per_rec_by_ds, path):
    mets = [m for m in cfg.PANEL_METRICS
            if all(m in per_rec_by_ds[k].columns for k in DS_KEYS)]
    rng = np.random.default_rng(0)
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for ax, metric in zip(axes.ravel(), mets):
        pos = 0
        ticks, ticklab = [], []
        for cond in cfg.COND_ORDER:
            for j, key in enumerate(DS_KEYS):
                v = _vals(per_rec_by_ds[key], cond, metric)
                if v.size:
                    bp = ax.boxplot(v, positions=[pos], widths=0.7, patch_artist=True,
                                    showfliers=False)
                    fc = cfg.COND_COLOR.get(cond, "#888")
                    bp["boxes"][0].set(facecolor=fc, alpha=0.45 if j else 0.9)
                    if j:
                        bp["boxes"][0].set_hatch("///")
                    ax.scatter(rng.normal(pos, 0.09, v.size), v,
                               s=6, color=fc, alpha=0.4, zorder=3, edgecolors="none")
                pos += 1
            ticks.append(pos - 1.5)
            ticklab.append(cond)
            pos += 0.6
        ax.set_xticks(ticks)
        ax.set_xticklabels(ticklab, fontsize=8)
        ax.set_title(_short(metric), fontsize=9)
        ax.axvline(ticks[2] + 0.9, color="0.8", lw=1)        # genetic | drug divider
    for ax in axes.ravel()[len(mets):]:
        ax.axis("off")
    fig.suptitle("Per-condition distributions — solid = {} · hatched = {} "
                 "(box = recordings/cells; left arm genetic, right arm drug)"
                 .format(DS_LABEL[DS_KEYS[0]], DS_LABEL[DS_KEYS[1]]), fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(path, dpi=130)
    plt.close(fig)


# ---------------------------------------------------------------- concordance
def fig_concordance(conc_by_contrast, path):
    items = [(k, v) for k, v in conc_by_contrast.items() if v is not None and not v.empty]
    n = len(items)
    fig, axes = plt.subplots(1, n, figsize=(4.2 * n, 4.3), squeeze=False)
    for ax, ((ctrl, test), m) in zip(axes.ravel(), items):
        da, db = m["d_a"].to_numpy(float), m["d_b"].to_numpy(float)
        rob = m["robust"].to_numpy(bool)
        lim = max(1.0, np.nanmax(np.abs(np.r_[da, db])) * 1.1)
        ax.axhline(0, color="0.8", lw=0.8); ax.axvline(0, color="0.8", lw=0.8)
        ax.plot([-lim, lim], [-lim, lim], "k--", lw=0.8, alpha=0.5)
        ax.scatter(da[~rob], db[~rob], s=28, color="0.6", edgecolors="k", lw=0.4)
        ax.scatter(da[rob], db[rob], s=42, color="#d62728", edgecolors="k", lw=0.5,
                   zorder=4, label="robust (both Bonferroni-sig, same sign)")
        for _, r in m.iterrows():
            if abs(r["d_a"]) > 0.45 or abs(r["d_b"]) > 0.45 or r["robust"]:
                ax.annotate(r["label"].split(" (")[0], (r["d_a"], r["d_b"]),
                            fontsize=6, alpha=0.8)
        pr = m.attrs.get("pearson_r")
        ax.set_title(f"{test} vs {ctrl}" + (f"  (r={pr:+.2f})" if pr is not None else ""),
                     fontsize=10)
        ax.set_xlabel(f"Cohen's d — {DS_LABEL[DS_KEYS[0]]}", fontsize=8)
        ax.set_ylabel(f"Cohen's d — {DS_LABEL[DS_KEYS[1]]}", fontsize=8)
        ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim)
    axes.ravel()[0].legend(fontsize=7, loc="upper left")
    fig.suptitle("Cross-dataset concordance of treatment effects "
                 "(each point = one metric; d>0 → higher in the treatment)", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(path, dpi=130)
    plt.close(fig)


# ---------------------------------------------------------------- autocorr decay
def fig_autocorr(autocorr_by_ds, path):
    fig, axes = plt.subplots(2, len(DS_KEYS), figsize=(5.4 * len(DS_KEYS), 8),
                             squeeze=False)
    for col, key in enumerate(DS_KEYS):
        ac = autocorr_by_ds[key]
        for row, (arm, spec) in enumerate(cfg.ARMS.items()):
            ax = axes[row][col]
            sub = ac[ac["condition"].isin(spec["conditions"])] if not ac.empty else ac
            curves = compare.ensemble_by_condition(sub, stat="mean",
                                                   value_col="autocorr")
            for cond in spec["conditions"]:
                if cond not in curves:
                    continue
                taus, c, lo, hi = (np.asarray(x, float) for x in curves[cond])
                col_ = cfg.COND_COLOR.get(cond, "#888")
                ax.plot(taus, c, "-", color=col_, lw=2, label=cond)
                ax.fill_between(taus, lo, hi, color=col_, alpha=0.15)
            ax.axhline(0, color="0.8", lw=0.8)
            ax.set_xlabel("lag τ (min)", fontsize=8)
            ax.set_ylabel("direction autocorrelation", fontsize=8)
            ax.set_title(f"{DS_LABEL[key]} — {arm} arm", fontsize=9)
            ax.legend(fontsize=8)
    fig.suptitle("Directional persistence (DiPer direction autocorrelation, "
                 "recording = unit, mean ± SEM)", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(path, dpi=130)
    plt.close(fig)


# ---------------------------------------------------------------- effect forest
def fig_forest(eff_by_ds, contrasts, path):
    fig, axes = plt.subplots(1, len(contrasts), figsize=(4.6 * len(contrasts), 6.5),
                             squeeze=False)
    for ax, (ctrl, test) in zip(axes.ravel(), contrasts):
        ref = eff_by_ds[DS_KEYS[0]].get((ctrl, test))
        if ref is None or ref.empty:
            ax.axis("off"); continue
        order = ref.sort_values("metric")["metric"].tolist()
        ys = np.arange(len(order))
        ax.axvline(0, color="0.7", ls="--", lw=0.8)
        for j, key in enumerate(DS_KEYS):
            df = eff_by_ds[key].get((ctrl, test))
            if df is None or df.empty:
                continue
            d = df.set_index("metric").reindex(order)
            off = (j - 0.5) * 0.3
            sig = (d["p_bonf"] < 0.05).to_numpy()
            col = np.where(sig, "#d62728" if j == 0 else "#1f77b4", "0.6")
            ax.errorbar(d["d"], ys + off, xerr=[d["d"] - d["lo"], d["hi"] - d["d"]],
                        fmt=DS_MARKER[key], ms=5, lw=1, color="0.4", ecolor="0.7",
                        mfc="none", zorder=2)
            ax.scatter(d["d"], ys + off, c=col, marker=DS_MARKER[key], s=34, zorder=3,
                       label=DS_LABEL[key])
        ax.set_yticks(ys)
        ax.set_yticklabels([_short(m).split(" (")[0] for m in order], fontsize=7)
        ax.set_xlabel(f"Cohen's d ({test} − {ctrl})", fontsize=9)
        ax.set_title(f"{test} vs {ctrl}", fontsize=10)
    axes.ravel()[0].legend(fontsize=7, loc="lower right")
    fig.suptitle("Effect sizes per metric (filled = Bonferroni-significant; "
                 "circle = {} · square = {})".format(*[DS_LABEL[k] for k in DS_KEYS]),
                 fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(path, dpi=130)
    plt.close(fig)


# ---------------------------------------------------------------- multivariate
def fig_multivariate(mv_by_ds, path):
    contrasts = [f"{t} vs {c}" for _a, c, t in cfg.CONTRASTS if _a != "batch"]
    x = np.arange(len(contrasts))
    fig, ax = plt.subplots(figsize=(8, 4.5))
    w = 0.38
    for j, key in enumerate(DS_KEYS):
        by = {f"{r['contrast']}": r for r in mv_by_ds.get(key, [])}
        auc = [by.get(c, {}).get("loro_auc") for c in contrasts]
        auc = [a if a is not None else np.nan for a in auc]
        bars = ax.bar(x + (j - 0.5) * w, auc, w, label=DS_LABEL[key],
                      color="#4c72b0" if j == 0 else "#dd8452", edgecolor="k", lw=0.5)
        for c, b in zip(contrasts, bars):
            p = by.get(c, {}).get("permanova_p")
            if p is not None and np.isfinite(b.get_height()):
                ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.01,
                        ("p<.001" if p < 1e-3 else f"p={p:.3f}"), ha="center", fontsize=7)
    ax.axhline(0.5, color="0.5", ls="--", lw=1)
    ax.set_xticks(x); ax.set_xticklabels(contrasts)
    ax.set_ylabel("leave-one-recording-out AUC"); ax.set_ylim(0, 1.05)
    ax.set_title("Multivariate phenotype per arm-contrast (PERMANOVA p + LORO-AUC, "
                 "recording = unit)", fontsize=10)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
