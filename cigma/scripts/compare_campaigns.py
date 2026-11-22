"""Compare two complete CIGMA campaign directories by canonical tree digest."""

from __future__ import annotations

import argparse
from pathlib import Path

from cigma.io import sha256_tree


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("left")
    parser.add_argument("right")
    args = parser.parse_args()
    left = sha256_tree(Path(args.left))
    right = sha256_tree(Path(args.right))
    print(f"left : {left}")
    print(f"right: {right}")
    if left != right:
        raise SystemExit("campaign directories differ")
    print("determinism-check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
