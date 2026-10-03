from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_release_validator_imports_settings_from_container_layout(tmp_path: Path) -> None:
    image_root = tmp_path / "image"
    release_tools = image_root / "release_tools"
    app_core = image_root / "app" / "core"
    outside = tmp_path / "outside"
    release_tools.mkdir(parents=True)
    app_core.mkdir(parents=True)
    outside.mkdir()

    validator = release_tools / "validate_release_config.py"
    validator.write_bytes((ROOT / "scripts" / "validate_release_config.py").read_bytes())
    (image_root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (app_core / "__init__.py").write_text("", encoding="utf-8")
    (app_core / "config.py").write_text(
        "class Settings:\n"
        "    model_fields = {}\n",
        encoding="utf-8",
    )

    probe = (
        "import runpy; "
        f"ns = runpy.run_path({str(validator)!r}); "
        "print(ns['settings_class']().__name__)"
    )
    result = subprocess.run(
        [sys.executable, "-S", "-c", probe],
        cwd=outside,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Settings"
