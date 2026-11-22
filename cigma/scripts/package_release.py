#!/usr/bin/env python3
"""Create a normalized clean-room source archive outside the repository."""

from __future__ import annotations

import argparse
from pathlib import Path
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".pytest_cache", "__pycache__", "build", "dist", ".venv", "venv"}
FIXED_TIME = (2026, 8, 26, 0, 0, 0)


def include(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return not any(part in EXCLUDED_PARTS for part in relative.parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT.parent / "cigma-reference-implementation-v0.1.0-clean-room.zip",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in ROOT.rglob("*") if item.is_file() and include(item)):
            relative = Path(ROOT.name) / path.relative_to(ROOT)
            info = zipfile.ZipInfo(relative.as_posix(), date_time=FIXED_TIME)
            info.create_system = 3
            executable = bool(path.stat().st_mode & stat.S_IXUSR)
            mode = 0o100755 if executable else 0o100644
            info.external_attr = mode << 16
            archive.writestr(info, path.read_bytes())
    print(args.output)


if __name__ == "__main__":
    main()
