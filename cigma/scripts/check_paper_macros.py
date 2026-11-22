"""Verify that campaign summary values and generated LaTeX macros agree."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from cigma.io import read_json


MACRO_PATTERN = re.compile(r"\\newcommand\{\\(?P<name>[^}]+)\}\{(?P<value>[^}]*)\}")


def parse_macros(path: Path) -> dict[str, str]:
    return {match.group("name"): match.group("value") for match in MACRO_PATTERN.finditer(path.read_text(encoding="utf-8"))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", required=True)
    parser.add_argument("--macros", required=True)
    args = parser.parse_args()
    summary = read_json(args.summary)
    macros = parse_macros(Path(args.macros))
    expected = {
        "CIGMARobustnessRuns": str(summary["robustness_method_runs"]),
        "CIGMARobustnessScenarios": str(summary["robustness_scenarios"]),
        "CIGMAPlannedContrasts": str(summary["planned_contrasts"]),
    }
    missing = {key: value for key, value in expected.items() if macros.get(key) != value}
    if missing:
        raise SystemExit(f"paper macro mismatch: {missing}; observed={macros}")
    print("paper-macros-check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
