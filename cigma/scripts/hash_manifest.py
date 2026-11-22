from __future__ import annotations

from hashlib import sha256
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "SHA256SUMS"
EXCLUDED = {"SHA256SUMS"}


def digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    rows = []
    for path in sorted(item for item in ROOT.rglob("*") if item.is_file()):
        relative = path.relative_to(ROOT).as_posix()
        if relative in EXCLUDED or "/.git/" in f"/{relative}/" or "__pycache__" in relative:
            continue
        rows.append(f"{digest(path)}  {relative}")
    OUTPUT.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
