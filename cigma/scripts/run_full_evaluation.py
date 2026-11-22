from __future__ import annotations

from pathlib import Path

from cigma.benchmark import generate_cigma_lab
from cigma.experiment import run_campaign


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    generate_cigma_lab(ROOT / "data" / "cigma_lab")
    summary = run_campaign(
        data_root=ROOT / "data" / "cigma_lab",
        config_path=ROOT / "configs" / "default.yaml",
        output_root=ROOT / "results" / "default",
    )
    print(summary)


if __name__ == "__main__":
    main()
