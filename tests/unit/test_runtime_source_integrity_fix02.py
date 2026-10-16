"""MMT-FIX-02: verify frozen and public-extra source integrity without rewriting pins."""
from __future__ import annotations

import ast
import shutil
from pathlib import Path

import pytest

from scripts.verify_runtime_integrity import (
    MANIFEST_SHA256,
    PUBLIC_EXTRAS,
    InventoryRefused,
    verify_runtime_integrity,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "production_source"


@pytest.fixture
def snapshot(tmp_path: Path) -> Path:
    target = tmp_path / "production_source"
    shutil.copytree(SOURCE, target)
    return target


def test_valid_legacy_tree_and_extra_inventory() -> None:
    assert verify_runtime_integrity(SOURCE) == (359, 3)


def test_original_brooks_pins_are_identical_to_independent_verifier() -> None:
    tree = ast.parse((ROOT / "naseri_markets/brooks_replay.py").read_text())
    pinned = {}
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if isinstance(target, ast.Name) and target.id in (
                "LEGACY_MANIFEST_SHA256", "LEGACY_PUBLIC_EXTRA_SHA256"
            ):
                pinned[target.id] = ast.literal_eval(statement.value)
    assert pinned["LEGACY_MANIFEST_SHA256"] == MANIFEST_SHA256
    assert pinned["LEGACY_PUBLIC_EXTRA_SHA256"] == PUBLIC_EXTRAS


@pytest.mark.parametrize("name", sorted(PUBLIC_EXTRAS))
def test_tampered_extra_python_fails_closed(snapshot: Path, name: str) -> None:
    target = snapshot / name
    target.write_bytes(target.read_bytes() + b"\n# malicious addition\n")
    with pytest.raises(InventoryRefused, match="INTEGRITY_PUBLIC_EXTRA_CHANGED"):
        verify_runtime_integrity(snapshot)


@pytest.mark.parametrize("name", sorted(PUBLIC_EXTRAS))
def test_removed_extra_python_fails_closed(snapshot: Path, name: str) -> None:
    (snapshot / name).unlink()
    with pytest.raises(InventoryRefused, match="INTEGRITY_PYTHON_INVENTORY_MISMATCH"):
        verify_runtime_integrity(snapshot)


def test_unlisted_runtime_python_fails_closed(snapshot: Path) -> None:
    added = snapshot / "app/modules/signal_intelligence/unapproved.py"
    added.write_text("print('unexpected')\n")
    with pytest.raises(InventoryRefused, match="INTEGRITY_PYTHON_INVENTORY_MISMATCH"):
        verify_runtime_integrity(snapshot)


def test_symlinked_extra_python_fails_closed(snapshot: Path) -> None:
    target = snapshot / sorted(PUBLIC_EXTRAS)[0]
    real = target.with_suffix(".source")
    target.rename(real)
    target.symlink_to(real)
    with pytest.raises(InventoryRefused, match="INTEGRITY_SYMLINK_DENIED"):
        verify_runtime_integrity(snapshot)


def test_symlinked_directory_fails_closed(snapshot: Path) -> None:
    target = snapshot / "app/modules/signal_intelligence"
    real = target.with_name("signal_intelligence_original")
    target.rename(real)
    target.symlink_to(real, target_is_directory=True)
    with pytest.raises(InventoryRefused, match="INTEGRITY_SYMLINK_DENIED"):
        verify_runtime_integrity(snapshot)


def test_modified_frozen_entry_fails_closed(snapshot: Path) -> None:
    name = (snapshot / "SHA256SUMS").read_text().splitlines()[0].split("  ", 1)[1]
    target = snapshot / name
    target.write_bytes(target.read_bytes() + b"\n# mutation\n")
    with pytest.raises(InventoryRefused, match="INTEGRITY_FROZEN_FILE_CHANGED"):
        verify_runtime_integrity(snapshot)


def test_mutated_frozen_manifest_fails_closed(snapshot: Path) -> None:
    manifest = snapshot / "SHA256SUMS"
    manifest.write_bytes(manifest.read_bytes() + b"\n")
    with pytest.raises(InventoryRefused, match="INTEGRITY_FROZEN_MANIFEST_CHANGED"):
        verify_runtime_integrity(snapshot)


def test_verify_sh_invokes_inventory_protection() -> None:
    script = (ROOT / "scripts/verify.sh").read_text()
    assert "python3 scripts/verify_runtime_integrity.py" in script
    assert len((SOURCE / "SHA256SUMS").read_text().splitlines()) == 359
