from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "results" / "default" / "metrics" / "robustness_aggregate.csv"
OUTPUT_DIR = ROOT / "results" / "default" / "figures"


def plot_metric(frame: pd.DataFrame, metric: str, title: str, filename: str) -> None:
    figure, axis = plt.subplots(figsize=(6.4, 4.0))
    subset = frame[frame["metric"] == metric]
    for method in ["source_union", "exact_direct", "cigma"]:
        rows = subset[subset["method"] == method].sort_values("nominal_deletion")
        x = rows["nominal_deletion"].to_numpy() * 100.0
        y = rows["mean"].to_numpy()
        lower = rows["ci95_lower"].to_numpy()
        upper = rows["ci95_upper"].to_numpy()
        axis.plot(x, y, marker="o", label=method)
        axis.fill_between(x, lower, upper, alpha=0.15)
    axis.set_title(title)
    axis.set_xlabel("Deleted entity-observation probability (%)")
    axis.set_ylabel("Mean score")
    axis.set_ylim(0.0, 1.05)
    axis.grid(True, alpha=0.25)
    axis.legend()
    figure.tight_layout()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT_DIR / filename, dpi=300)
    plt.close(figure)


def main() -> None:
    frame = pd.read_csv(INPUT)
    plot_metric(frame, "asset_f1", "Asset F1 under paired observation deletion", "asset_f1_robustness.png")
    plot_metric(frame, "edge_f1", "Typed-edge F1 under paired observation deletion", "edge_f1_robustness.png")
    print(OUTPUT_DIR)


if __name__ == "__main__":
    main()
