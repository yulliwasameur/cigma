"""Stable JSON/JSONL I/O and integrity helpers."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from .config import canonical_json
from .schema import EntityObservation, RelationObservation




def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes for identifiers and evidence."""
    return canonical_json(value).encode("utf-8")

def write_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(canonical_json(dict(row)) + "\n")


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_number}: {path}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row must be an object at line {line_number}: {path}")
            yield value


def load_observations(
    entity_path: str | Path,
    relation_path: str | Path,
) -> tuple[list[EntityObservation], list[RelationObservation]]:
    entities = [EntityObservation.from_dict(row) for row in read_jsonl(entity_path)]
    relations = [RelationObservation.from_dict(row) for row in read_jsonl(relation_path)]
    return entities, relations


def sha256_file(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(root: str | Path) -> str:
    base = Path(root)
    digest = sha256()
    for path in sorted(item for item in base.rglob("*") if item.is_file()):
        relative = path.relative_to(base).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        file_hash = bytes.fromhex(sha256_file(path))
        digest.update(file_hash)
    return digest.hexdigest()
