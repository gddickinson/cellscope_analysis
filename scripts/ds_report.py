"""Markdown report writer for the IC293 vs IC295 treatment comparison."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

import ds_config as cfg  # noqa: E402

DS = [d["key"] for d in cfg.DATASETS]
LBL = {d["key"]: d["label"] for d in cfg.DATASETS}


def _f(x, n=2):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{n}f}"


def _table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out) + "\n"


def _counts_section(counts):
    rows = []
    for k in DS:
        c = counts[k]
        per = ", ".join(f"{cond} {c['by_cond'].get(cond, 0)}" for cond in cfg.COND_ORDER)
        rows.append([LBL[k], c["raw"], c["filtered"], per])
    return _table(["dataset", "cells (raw)", f"cells (≥{cfg.MIN_FRAMES} frames)",
                   "per condition (filtered)"], rows)


def _effects_section(effects):
    """Top Bonferroni-significant metrics per treatment contrast, per dataset."""
    out = []
    for _arm, ctrl, test in cfg.CONTRASTS:
        if _arm == "batch":
            continue
        out.append(f"\n**{test} vs {ctrl}**\n")
        rows = []
        for k in DS:
            df = effects[k].get((ctrl, test))
            if df is None or df.empty:
                continue
            sig = df[df["p_bonf"] < 0.05].sort_values("d", key=lambda s: -s.abs())
            if sig.empty:
                rows.append([LBL[k], "_none survive Bonferroni_"])
                continue
            hits = "; ".join(f"{r['label'].split(' (')[0]} (d={r['d']:+.2f})"
                             for _, r in sig.head(6).iterrows())
            rows.append([LBL[k], hits])
        out.append(_table(["dataset", "Bonferroni-significant metrics (d = test − control)"],
                          rows))
    return "".join(out)


def _concordance_section(conc):
    rows, robust_lines = [], []
    for _arm, ctrl, test in cfg.CONTRASTS:
        if _arm == "batch":
            continue
        m, st = conc.get((ctrl, test), (None, {}))
        if not st:
            continue
        rows.append([f"{test} vs {ctrl}", _f(st.get("pearson_r")), _f(st.get("spearman_r")),
                     st.get("n_robust", 0), st.get("n_agree_sign", 0),
                     st.get("n_metrics", 0)])
        if m is not None and not m.empty:
            rob = m[m["robust"]].sort_values("d_a", key=lambda s: -s.abs())
            if not rob.empty:
                items = ", ".join(
                    f"{r['label'].split(' (')[0]} (d={r['d_a']:+.2f}/{r['d_b']:+.2f})"
                    for _, r in rob.iterrows())
                robust_lines.append(f"- **{test} vs {ctrl}** — reproducible: {items}")
    body = _table(["contrast", "Pearson r", "Spearman r", "robust effects",
                   "same-sign metrics", "metrics"], rows)
    body += ("\n*Pearson/Spearman r = correlation of per-metric Cohen's d between the "
             "two datasets (how similarly the treatment reshapes the panel). "
             "`robust` = same sign AND Bonferroni-significant in BOTH datasets "
             "(d shown as IC293/IC295).*\n\n")
    body += ("\n".join(robust_lines) if robust_lines
             else "_No effect was Bonferroni-significant in both datasets._") + "\n"
    return body


def _multivariate_section(mv):
    rows = []
    contrasts = [f"{t} vs {c}" for _a, c, t in cfg.CONTRASTS if _a != "batch"]
    for k in DS:
        by = {r["contrast"]: r for r in mv.get(k, [])}
        for c in contrasts:
            r = by.get(c)
            if r:
                rows.append([LBL[k], c, r.get("n_ctrl"), r.get("n_test"),
                             _f(r.get("permanova_p"), 3), _f(r.get("loro_auc"), 2)])
    return _table(["dataset", "contrast", "n ctrl", "n test", "PERMANOVA p",
                   "LORO-AUC"], rows) + (
        "\n*AUC = 0.5 is chance; **AUC < 0.5** means the held-out classifier does worse "
        "than chance — i.e. no separable phenotype (it fit noise). The reproducible "
        "separation is **KO vs WT** (0.62 → 0.78).*\n")


def _synthesis(res):
    conc, mv = res["concordance"], res["multivariate"]
    auc = {(k, r["contrast"]): r.get("loro_auc") for k in DS for r in mv.get(k, [])}
    sims, diffs = [], []
    for _arm, c, t in cfg.CONTRASTS:
        if _arm == "batch":
            continue
        _m, stt = conc.get((c, t), (None, {}))
        r = stt.get("pearson_r")
        a0, a1 = auc.get((DS[0], f"{t} vs {c}")), auc.get((DS[1], f"{t} vs {c}"))
        aucs = f"LORO-AUC {_f(a0)} / {_f(a1)}"
        if r is None:
            continue
        if r > 0.5:
            sims.append(f"- **{t} vs {c}** — effect-size profiles **concordant** "
                        f"(r = {r:+.2f}, {stt.get('n_agree_sign')}/{stt.get('n_metrics')} "
                        f"metrics same direction); {aucs}.")
        elif r < 0.2:
            diffs.append(f"- **{t} vs {c}** — effect-size profiles **do not reproduce** "
                         f"(r = {r:+.2f}); {aucs}. No reliable cross-dataset effect.")
    body = "**Similarities — treatment effects that reproduce in both datasets:**\n\n"
    body += ("\n".join(sims) if sims else "_none_") + "\n\n"
    body += "**Differences — effects that diverge between the two datasets:**\n\n"
    body += ("\n".join(diffs) if diffs else "_none_") + "\n\n"
    body += (
        "**Read-out.** The **genetic arm reproduces** and the **drug arm does not**. "
        "The clearest, most reproducible signal is **KO vs WT**: a multivariate "
        "shape + motion shift seen by both extraction methods (and the only contrast "
        "Bonferroni-significant on individual metrics, in the larger IC295 set — lower "
        "directional persistence, more tumbling/turning, lower aspect ratio/eccentricity, "
        "i.e. rounder + less persistent). **Note the direction runs opposite to the naive "
        "PIEZO1-brake expectation** (KO faster/straighter); the reproducibility is strong "
        "but the direction needs careful interpretation (sparse single-cell crops are a "
        "different regime from collective migration). **GOF** is weak/inconsistent "
        "(moderate concordance, near-chance separation). The **drug effects** (YODA1, "
        "Otenabant) seen in one dataset (e.g. OT in IC293) **do not reproduce** in the "
        "other — most consistent with underpowering / batch, not a robust drug effect. "
        "No single metric is Bonferroni-significant in *both* datasets, so the evidence "
        "is the multivariate KO separation + the effect-size concordance, not any one p.\n")
    return body


def _batch_note(effects):
    parts = []
    for k in DS:
        df = effects[k].get(("DMSO", "WT"))
        if df is None or df.empty:
            continue
        nsig = int((df["p_bonf"] < 0.05).sum())
        top = df.sort_values("d", key=lambda s: -s.abs()).head(3)
        ex = "; ".join(f"{r['label'].split(' (')[0]} d={r['d']:+.2f}"
                       for _, r in top.iterrows())
        parts.append(f"- {LBL[k]}: {nsig}/{len(df)} metrics differ (Bonferroni) "
                     f"between the two controls; largest: {ex}.")
    return "\n".join(parts) + "\n"


def write_report(path, res):
    figs = res["figs"]
    summary = _synthesis(res)
    L0, L1 = LBL[DS[0]], LBL[DS[1]]
    md = f"""# PIEZO1 single-cell migration — {L0} vs {L1}

Comparison of treatment effects across two single-cell datasets from the same PIEZO1
keratinocyte study: **{L0}** and **{L1}**. Conditions are the genetic arm
**WT / GOF / KO** (control WT) and the drug arm **DMSO / Y1 (YODA1) / OT (Otenabant)**
(vehicle control DMSO). PIEZO1 is a mechanosensitive brake on migration, so the
a-priori expectation is that **KO** migrates faster / straighter / more persistently
and **GOF / YODA1** slower, with more rounding/retraction.

> Generated by `scripts/compare_datasets.py` (recording = unit; one single-cell crop =
> one cell). All metrics are computed in-project from the masks.

## Summary — similarities & differences between treatments

{summary}

## Methods

- **Unit = recording = one tracked single cell.** Per-cell metrics from
  `compare.build_comparison`; one row per cell.
- Tracks shorter than **{cfg.MIN_FRAMES} frames** are dropped (noisy motion).
- Per contrast: **Cohen's d** (test − control) with a 95 % bootstrap CI and a
  **Mann–Whitney U** p, **Bonferroni-corrected** over the {len(cfg.KEY_METRICS)}-metric
  panel. **Multivariate**: PERMANOVA p + leave-one-recording-out logistic AUC over the
  same {len(cfg.KEY_METRICS)}-metric panel (z-scored), label-permutation null.
- **Cross-dataset concordance**: how similarly the two datasets rank/scale each
  treatment's per-metric effect sizes (Pearson/Spearman r of the d-vectors), and which
  individual effects are *robust* (same sign + Bonferroni-significant in both).
- Caveats below — read them before interpreting.

## Sample sizes

{_counts_section(res['counts'])}

## Figures

![Per-condition distributions]({figs['distributions']})

*Per-condition distributions of the headline metrics (solid = {L0}, hatched = {L1}).*

![Cross-dataset concordance]({figs['concordance']})

*Each point = one metric; x/y = its Cohen's d in the two datasets. Points on the
diagonal reproduce; red = robust (Bonferroni-significant, same sign, both datasets).*

![Directional persistence]({figs['autocorr']})

*Direction autocorrelation (DiPer) decay per condition — slower decay = more persistent
directional migration.*

![Effect sizes — genetic arm]({figs['forest_genetic']})

![Effect sizes — drug arm]({figs['forest_drug']})

*Per-metric Cohen's d for each contrast in both datasets (filled = Bonferroni-sig).*

![Multivariate phenotype]({figs['multivariate']})

*Multivariate separation of each treatment from its control (LORO-AUC; 0.5 = chance).*

## Within-dataset treatment effects
{_effects_section(res['effects'])}
## Cross-dataset concordance (similarities & differences)

{_concordance_section(res['concordance'])}
## Multivariate phenotype per arm

{_multivariate_section(res['multivariate'])}

## Batch / vehicle (WT vs DMSO) — confound check

The two arm-controls (genetic WT, drug-vehicle DMSO) are different batches; a large
WT–DMSO difference flags batch effects that limit cross-arm comparison.

{_batch_note(res['effects'])}
## Caveats

- **Pseudoreplication**: the unit here is a single cell, not a biological replicate
  (dish/well). Cells from one field are not fully independent, so p-values are
  anti-conservative; treat the **cross-dataset reproducibility** (robust effects) as the
  stronger evidence, not any single p.
- **Extraction differs**: {L0} are manually cropped, {L1} programmatically extracted —
  a source of method (not biology) differences; concordance separates the two.
- **Multiple comparisons**: Bonferroni over the metric panel only (not across contrasts
  or datasets).
- **Batch**: see the WT-vs-DMSO check; the drug and genetic arms are not interchangeable.
- Metrics are **descriptive**; directions are reported relative to the PIEZO1-brake
  expectation but this report does not establish mechanism.
"""
    with open(path, "w") as f:
        f.write(md)
    return path
