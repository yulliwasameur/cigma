#!/usr/bin/env python3
"""Generate the paper's result figures from the result files (no number is typed by hand).

python scripts/make_figures.py --results ../results/extensions --out ../paper/figures
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--results", default="../results/extensions")
ap.add_argument("--out", default="../paper/figures")
a = ap.parse_args()
R, O = Path(a.results), Path(a.out)
O.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.size": 8, "font.family": "serif", "figure.dpi": 200})

# One full-width figure with three panels (legible at print size: fonts >= 7 pt)
plt.rcParams.update({"font.size": 8, "axes.labelsize": 8, "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7})
fig, (axa, axb, axc) = plt.subplots(1, 3, figsize=(6.22, 1.92))

# (a) Poisoning campaign
s = pd.read_csv(R / "e7_poisoning_summary.csv")
for method, lab, m in (("source_union", "Union F1", "s"), ("cigma_fixed", "CIGMA F1", "o")):
    d = s[s["method"] == method]
    axa.plot(d["k"], d["typed_edge_f1"], m + "-", ms=3, lw=0.9, label=lab)
for method, lab, m in (("cigma_fixed", "flagged, fixed r", "o"), ("cigma_learned_copy_aware", "flagged, learned r", "^")):
    d = s[(s["method"] == method) & (s["k"] > 0)]
    axa.plot(d["k"], d["poisoned_flagged"] / d["poisoned_accepted"], m + "--", ms=3, lw=0.9, label=lab)
axa.set_xlabel("Injected false relations k")
axa.set_ylim(0.28, 1.04)
axa.legend(frameon=False, loc="lower left", handlelength=1.6)
axa.set_title("(a) Poisoning", fontsize=8)

# (b) Conformal selection: FDR vs power
c = pd.read_csv(R / "e8_conformal_summary.csv")
offsets = {"0.05": (-24, 6), "0.1": (-6, 9), "0.10": (-6, 9), "0.2": (4, -9), "0.20": (4, -9)}
for _, row in c.iterrows():
    rule = row["rule"]
    if "fixed_support" in rule:
        continue
    if rule.startswith("conformal_learned_score_alpha_"):
        a_ = rule.rsplit("_", 1)[-1]
        name, style, off = "α=" + a_, "o", offsets.get(a_, (3, 3))
    elif rule == "accept_all":
        name, style, off = "accept all", "s", (-44, 4)
    else:
        name, style, off = rule.replace("_", " "), "s", (-62, -10) if "0.5" in rule else (4, 2)
    axb.errorbar(row["power_mean"], row["fdr_mean"],
                 yerr=[[row["fdr_mean"] - row["fdr_ci95_low"]], [row["fdr_ci95_high"] - row["fdr_mean"]]],
                 fmt=style, ms=4, capsize=2, lw=0.7, color="0.2")
    axb.annotate(name, (row["power_mean"], row["fdr_mean"]), fontsize=7, xytext=off, textcoords="offset points")
for alpha in (0.05, 0.10, 0.20):
    axb.axhline(alpha, ls=":", lw=0.6, color="0.6")
axb.set_xlabel("Power (true edges accepted)")
axb.set_ylabel("Observed FDR")
axb.set_title("(b) Conformal selection", fontsize=8)

# (c) Pareto front urgency / breakage, with the fixed orders
p = pd.read_csv(R / "e9_pareto_front.csv")
axc.plot(p["movr"], p["exposure_auc"], "o-", color="0.4", ms=3, lw=0.9, label=r"blend $\lambda$")
f = R / "e11_e13_orders_on_fixture.csv"
if f.exists():
    o = pd.read_csv(f)
    marks = {"sharma2026": ("s", "Sharma 2026"), "optimal_cp_sat": ("*", "CP-SAT"), "interop_aware": ("^", "interop-aware")}
    for key, (m, lab) in marks.items():
        row = o[o["order"] == key]
        if len(row):
            axc.plot(row["movr"], row["exposure_auc"], m, ms=8 if m == "*" else 5, label=lab)
lo, hi = axc.get_ylim(); axc.set_ylim(lo - 0.02 * (hi - lo), hi + 0.08 * (hi - lo)); axc.set_xlim(-0.006, 0.135)
axc.set_xlabel("MOVR (fewer breaks →0)")
axc.set_ylabel("Exposure AUC")
axc.legend(frameon=False, loc="lower right", handlelength=1.2, borderaxespad=0.2)
axc.set_title("(c) Urgency vs breakage", fontsize=8)
fig.tight_layout(w_pad=1.0)
fig.savefig(O / "fig_results.pdf")
print("figures written to", O)
