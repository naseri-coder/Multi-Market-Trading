"""Prepare an isolated build context from verified, public modules only.

Writes exclusively to an explicit NEW output directory. Does not import
strategies, clone private repositories, contact services, or modify git files.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {"r0_engine", "private_nyfr_core"}


def _check_module(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError("NONREGULAR_MODULE")
    if path.stem in FORBIDDEN:
        raise ValueError("PRIVATE_MODULE_NOT_ALLOWED")
    tree = ast.parse(path.read_bytes())
    for n in ast.walk(tree):
        if isinstance(n, ast.Import) and any(
            k.name.split(".")[0] in FORBIDDEN for k in n.names
        ):
            raise ValueError("PRIVATE_IMPORT_NOT_ALLOWED")
        if (
            isinstance(n, ast.ImportFrom)
            and (n.module or "").split(".")[0] in FORBIDDEN
        ):
            raise ValueError("PRIVATE_IMPORT_NOT_ALLOWED")


def prepare(destination: Path) -> dict:
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("OUTPUT_MUST_NOT_EXIST")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise ValueError("OUTPUT_PARENT_MUST_EXIST_AND_NOT_BE_SYMLINK")
    if destination == ROOT or ROOT in destination.parents:
        raise ValueError("OUTPUT_MUST_BE_OUTSIDE_REPOSITORY")

    source = ROOT / "naseri_markets"
    modules = sorted(source.glob("*.py"))
    if not modules or (source / "platform_cli.py") not in modules:
        raise ValueError("PLATFORM_MODULE_MISSING")
    for module in modules:
        _check_module(module)
    static = [
        ROOT / "platform_release/pyproject.toml",
        ROOT / "platform_release/README.md",
    ]
    if any(not path.is_file() or path.is_symlink() for path in static):
        raise ValueError("PACKAGE_METADATA_UNSAFE")
    destination.mkdir(mode=0o700)
    pkg = destination / "naseri_markets"
    pkg.mkdir()
    digests = {}
    for path in [*modules, *static]:
        rel = (Path("naseri_markets") / path.name) if path in modules else Path(path.name)
        data = path.read_bytes()
        (destination / rel).write_bytes(data)
        digests[str(rel)] = hashlib.sha256(data).hexdigest()
    return {
        "version": "0.4.0rc1",
        "module_count": len(modules),
        "sha256": digests,
        "source_was_mutated": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--destination", required=True, type=Path)
    args = p.parse_args()
    try:
        result = prepare(args.destination)
    except (OSError, ValueError, SyntaxError) as exc:
        print(f"A6_STAGE_REFUSED:{type(exc).__name__}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
