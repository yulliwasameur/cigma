#!/usr/bin/env python3
import pathlib
"""Check that every key number printed in paper/main.tex matches the result files.

python scripts/check_paper_numbers.py --paper ../paper/main.tex --results ../results
Exit code 1 if a number is missing from the paper or differs from the files.
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--paper", default="../paper/main.tex")
ap.add_argument("--results", default="../results")
a = ap.parse_args()
tex = Path(a.paper).read_text()
R = Path(a.results)
X = R / "extensions"
checks = []


def chk(label, value, fmt, must_appear=True):
    s = fmt.format(value)
    ok = (s in tex) if must_appear else True
    checks.append((label, s, ok))


mm = pd.read_csv(R / "cigma-lab/metrics/method_metrics.csv").set_index("method")
chk("ExactDirect typed-edge F1", mm.loc["exact_direct", "typed_edge_f1"], "{:.3f}")
chk("no-alias asset F1", mm.loc["cigma_no_aliases", "asset_f1"], "{:.3f}")
chk("no-paths typed-edge F1", mm.loc["cigma_no_paths", "typed_edge_f1"], "{:.3f}")
chk("no-gate asset F1", mm.loc["cigma_no_quality_gate", "asset_f1"], "{:.3f}")
chk("TLS-only asset F1 (table)", round(mm.loc["tls_inventory", "asset_f1"] * 1000), ".{:03d} &")
rob = pd.read_csv(R / "cigma-lab/metrics/robustness_aggregate.csv")
q = rob[(rob.nominal_deletion == 0.5) & (rob.metric == "asset_f1")].set_index("method")
chk("50% deletion CIGMA asset F1", q.loc["cigma", "mean"], "{:.3f}")
chk("50% deletion SourceUnion asset F1", q.loc["source_union", "mean"], "{:.3f}")
chk("50% deletion ExactDirect asset F1", q.loc["exact_direct", "mean"], "{:.3f}")
mt = pd.read_csv(X / "e2_multitool.csv").set_index("method")
chk("multi-tool CIGMA F1", mt.loc["cigma_fixed_reliability", "typed_edge_f1"], "{:.3f}")
chk("multi-tool vote F1", mt.loc["majority_vote_then_cigma", "typed_edge_f1"], "{:.3f}")
chk("multi-tool union F1", mt.loc["union_all_tools", "typed_edge_f1"], "{:.3f}")
info = json.loads((X / "e2_multitool_info.json").read_text())
chk("learned+copy tool_a", info["learned_with_copy"]["reliabilities"]["cbom:tool_a"], "{:.3f}")
chk("learned+copy tool_b", info["learned_with_copy"]["reliabilities"]["cbom:tool_b"], "{:.3f}")
chk("learned no-copy tool_b", info["learned_without_copy"]["reliabilities"]["cbom:tool_b"], "{:.3f}")
p7 = pd.read_csv(X / "e7_poisoning_summary.csv")
row = lambda m, k: p7[(p7.method == m) & (p7.k == k)].iloc[0]
chk("poison k16 CIGMA F1", row("cigma_fixed", 16)["typed_edge_f1"], "{:.3f}")
chk("poison k16 union F1", row("source_union", 16)["typed_edge_f1"], "{:.3f}")
r16 = row("cigma_learned_copy_aware", 16)
chk("poison flagged % learned", 100 * r16["poisoned_flagged"] / r16["poisoned_accepted"], "{:.0f}\\%")
f16 = row("cigma_fixed", 16)
chk("poison flagged % fixed", 100 * f16["poisoned_flagged"] / f16["poisoned_accepted"], "{:.0f}\\%")
c8 = pd.read_csv(X / "e8_conformal_summary.csv").set_index("rule")
chk("conformal a=.10 FDR", c8.loc["conformal_learned_score_alpha_0.1", "fdr_mean"], "{:.3f}")
chk("conformal a=.05 FDR", c8.loc["conformal_learned_score_alpha_0.05", "fdr_mean"], "{:.3f}")
chk("conformal a=.20 FDR", c8.loc["conformal_learned_score_alpha_0.2", "fdr_mean"], "{:.3f}")
chk("threshold .85 FDR", c8.loc["threshold_0.85", "fdr_mean"], "{:.3f}")
chk("accept-all FDR", c8.loc["accept_all", "fdr_mean"], "{:.3f}")
s10 = pd.read_csv(X / "e10_signed_observations.csv").set_index("scenario")
chk("insider poisoned accepted", int(s10.loc["insider_stolen_trusted_key", "poisoned_accepted"]), "{} poisoned")
o = pd.read_csv(X / "e11_e13_orders_on_fixture.csv").set_index("order") if (X / "e11_e13_orders_on_fixture.csv").exists() else None
if o is not None:
    chk("CP-SAT exposure", o.loc["optimal_cp_sat", "exposure_auc"], "{:.3f}")
    chk("interop exposure", o.loc["interop_aware", "exposure_auc"], "{:.3f}")
    chk("Sharma exposure", o.loc["sharma2026", "exposure_auc"], "{:.3f}")
    chk("Sharma MOVR", o.loc["sharma2026", "movr"], "{:.2f}")
e5 = json.loads((X / "e5_commitment.json").read_text())
chk("receipt disclosed %", 100 * e5["mean_disclosed_fraction"], "{:.1f}\\%")
chk("leaves", e5["leaves"], "{} leaves")
e15 = pd.read_csv(X / "e15_validator_adversarial.csv") if (X / "e15_validator_adversarial.csv").exists() else None
if e15 is not None:
    adv = e15[e15.attack != "valid_direct_with_injected_rationale"]["submitted"].sum()
    chk("adversarial candidates", f"{adv:,}".replace(",", "{,}"), "{}")
rq5 = ROOT / "results" / "rq5" / "rq3_calls.csv" if "ROOT" in globals() else pathlib.Path(__file__).resolve().parents[2] / "results" / "rq5" / "rq3_calls.csv"
if rq5.exists():
    d5 = pd.read_csv(rq5); ok5 = d5[d5.parse_error.isna()]
    chk("RQ5 calls", f"{len(d5):,}".replace(",", "{,}"), "{} calls")
    chk("RQ5 parsable", f"{len(ok5):,}".replace(",", "{,}"), "({} parsable)")
    chk("RQ5 proposed", f"{int(ok5.proposed.sum()):,}".replace(",", "{,}"), "{} candidate")
    chk("RQ5 accepted", int(ok5.accepted.sum()), "accepted {}")
    chk("RQ5 false accepted", int(ok5.accepted_false.sum()), "{} false accepted") if ok5.accepted_false.sum() else None

EA = pathlib.Path(__file__).resolve().parents[2] / "results" / "equal_access"
if (EA / "e17_complete.csv").exists():
    e17 = pd.read_csv(EA / "e17_complete.csv").set_index("method")
    chk("E17 equal-access paths F1", e17.loc["fellegi_sunter_paths", "edge_f1"], "{:.3f}")
    chk("E17 rule any-id F1", e17.loc["rules_any_id_paths", "edge_f1"], "{:.3f}")
    e19 = pd.read_csv(EA / "e19_noisy_identifiers.csv")
    g = e19[e19.decoys == 4].groupby("method").mean(numeric_only=True)
    chk("E19 rule F1 k=4", g.loc["rules_any_id_paths", "edge_f1"], "{:.3f}")
    chk("E19 rule FP k=4", g.loc["rules_any_id_paths", "edge_fp_rate"], "{:.3f}")
    chk("E19 CIGMA F1 k=4", g.loc["cigma", "edge_f1"], "{:.3f}")
    chk("E19 guard F1 k=4", g.loc["cigma_guard", "edge_f1"], "{:.3f}")
    chk("E19 guard FP k=4", g.loc["cigma_guard", "edge_fp_rate"], "{:.3f}")
    e18 = pd.read_csv(EA / "e17_e18_deletion.csv")
    m = e18[e18.method == "cigma"].groupby("p").edge_f1_recoverable.mean()
    chk("E18 CIGMA recoverable F1 (min over p)", m.min(), "{:.3f}")
bad = [c for c in checks if not c[2]]
for label, s, ok in checks:
    print(("OK   " if ok else "MISS ") + f"{label}: {s}")
print(f"\n{len(checks) - len(bad)}/{len(checks)} numbers found in the paper")
sys.exit(1 if bad else 0)
