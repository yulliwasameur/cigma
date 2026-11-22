#!/usr/bin/env python3
"""Generate the human-readable repository inventory."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "MANIFEST.md"
EXCLUDED_PARTS = {".git", ".pytest_cache", "__pycache__", "build", "dist"}


def description(relative: str) -> str:
    exact = {
        ".github/workflows/ci.yml": "Private-repository CI workflow for Python 3.11 and 3.12.",
        ".gitignore": "Generated-file, environment, cache, and secret exclusions.",
        "CHANGELOG.md": "Versioned record of clean-room implementation changes.",
        "CITATION.cff": "Software citation metadata and clean-room warning.",
        "CONTRIBUTING.md": "Private contribution and scientific-integrity rules.",
        "LICENSE": "Current private all-rights-reserved license.",
        "Makefile": "Single-command fixture, test, campaign, scaling, and seal runners.",
        "MANIFEST.md": "This complete file inventory.",
        "NOTICE.md": "Clean-room reconstruction and historical-artifact boundary.",
        "README.md": "Project overview, commands, methods, and repository map.",
        "SECURITY.md": "Sensitive-evidence and vulnerability-reporting policy.",
        "configs/default.yaml": "Frozen quality, reliability, identity, path, ranking, and evaluation policy.",
        "pyproject.toml": "Python package metadata, dependencies, and CLI entry point.",
        "requirements.txt": "Pinned runtime dependencies.",
        "requirements-dev.txt": "Pinned test and build dependencies.",
        "SHA256SUMS": "SHA-256 inventory of every release file except itself.",
    }
    if relative in exact:
        return exact[relative]
    if relative.startswith("docs/"):
        return "Technical documentation: " + Path(relative).stem.replace("_", " ").lower() + "."
    if relative.startswith("schemas/"):
        return "JSON Schema for " + Path(relative).stem.replace(".", " ") + "."
    if relative.startswith("data/cigma_lab/public/"):
        return "Generated public CIGMA-Lab observation data; contains no oracle IDs."
    if relative.startswith("data/cigma_lab/oracle/"):
        return "Evaluator-only CIGMA-Lab truth, mappings, targets, or priorities."
    if relative == "data/cigma_lab/fixture_statistics.json":
        return "Declared and generated fixture counts by source family."
    if relative == "data/cigma_lab/manifest.json":
        return "Fixture file hashes and clean-room generator metadata."
    if relative.startswith("examples/minimal/public/"):
        return "Minimal cross-source public observation stream."
    if relative.startswith("examples/minimal/output/graphs/"):
        return "Minimal example's resulting evidence graph."
    if relative.startswith("examples/minimal/output/rankings/"):
        return "Minimal example's resulting ranked actions."
    if relative == "examples/minimal/generate.py":
        return "Generates the smallest CMDB plus TLS end-to-end example."
    if relative == "examples/minimal/README.md":
        return "Commands and interpretation for the minimal example."
    if relative.startswith("src/cigma/adapters/"):
        return "Source-family adapter implementation: " + Path(relative).stem + "."
    if relative.startswith("src/cigma/"):
        return "Core CIGMA module: " + Path(relative).stem.replace("_", " ") + "."
    if relative.startswith("tests/"):
        return "Unit or invariant tests: " + Path(relative).stem.replace("test_", "").replace("_", " ") + "."
    if relative.startswith("scripts/"):
        return "Reproducibility utility: " + Path(relative).stem.replace("_", " ") + "."
    if relative.startswith("results/default/graphs/"):
        return "Complete-fixture graph output for method " + Path(relative).stem + "."
    if relative.startswith("results/default/rankings/"):
        return "Complete-fixture ranking output for method " + Path(relative).stem + "."
    if relative.startswith("results/default/metrics/"):
        return "Machine-readable deterministic campaign metric table."
    if relative.startswith("results/default/figures/"):
        return "Regenerated host-independent robustness figure."
    if relative == "results/default/paper_macros.tex":
        return "Generated LaTeX macros from current clean-room metrics."
    if relative == "results/default/manifest.json":
        return "Deterministic campaign configuration, input, and output bindings."
    if relative == "results/default/summary.json":
        return "Concise clean-room campaign summary and result boundary."
    if relative.startswith("results/seal-demo/predictions/"):
        return "Phase-1 public-only prediction or prediction-seal file."
    if relative.startswith("results/seal-demo/evaluation/"):
        return "Phase-2 evaluator-only sealed evaluation output."
    if relative.startswith("results/seal-demo/"):
        return "Captured command output for the two-phase seal demonstration."
    if relative.startswith("results/scaling/"):
        return "Host-dependent scaling diagnostic; excluded from accuracy claims."
    if relative.startswith("reports/"):
        return "Verification, build, or release-readiness record."
    return "Project file."


def main() -> None:
    files = []
    for path in sorted(item for item in ROOT.rglob("*") if item.is_file()):
        relative_path = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative_path.parts):
            continue
        relative = relative_path.as_posix()
        if relative == "SHA256SUMS":
            # It is generated after MANIFEST; still document it explicitly.
            continue
        files.append(relative)
    if "MANIFEST.md" not in files:
        files.append("MANIFEST.md")
    files = sorted(set(files + ["SHA256SUMS"]))
    lines = [
        "# CIGMA clean-room repository manifest",
        "",
        "- Implementation: `0.1.0-clean-room`",
        "- Supported Python: `>=3.11`",
        "- Full command: `PYTHONDONTWRITEBYTECODE=1 make verify`",
        "- Scaling diagnostic: `PYTHONDONTWRITEBYTECODE=1 make scaling`",
        "- Integrity inventory: `python scripts/hash_manifest.py`",
        f"- Files documented: **{len(files)}**",
        "",
        "This manifest describes the clean-room repository, not the lost historical artifact.",
        "",
        "## Files",
        "",
        "| Path | Description |",
        "|---|---|",
    ]
    for relative in files:
        lines.append(f"| `{relative}` | {description(relative)} |")
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
