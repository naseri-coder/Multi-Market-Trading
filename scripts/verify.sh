#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

test "$(wc -l < production_source/SHA256SUMS)" -eq 362
( cd production_source && sha256sum --status -c SHA256SUMS )

python3 - <<'PY'
from pathlib import Path
import ast
import hashlib
import tomllib

root = Path("production_source")
entries = []
for line in (root / "SHA256SUMS").read_text().splitlines():
    digest, rel = line.split("  ", 1)
    item = Path(rel)
    assert not item.is_absolute() and ".." not in item.parts
    full = root / item
    assert full.is_file() and not full.is_symlink()
    assert hashlib.sha256(full.read_bytes()).hexdigest() == digest
    entries.append(rel)
assert len(entries) == 362 and len(set(entries)) == 362

parsed = 0
for rel in entries:
    if rel.endswith(".py"):
        ast.parse((root / rel).read_bytes(), filename=rel)
        parsed += 1
ast.parse(Path("production_checks/verify_historical_probability_regression.py").read_bytes())

project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
assert project["project"]["version"] == "0.3.2"
print("SOURCE_SHA256_PASS entries=362; PYTHON_AST_PASS count=" + str(parsed))
print("PACKAGE_VERSION_PASS 0.3.2")
PY

bash -n   naseri.sh   scripts/install.sh   scripts/manager.sh   scripts/lib/manager_common.sh   scripts/lib/manager_backup.sh   scripts/lib/manager_runtime.sh   scripts/test_manager.sh   scripts/verify.sh
bash scripts/manager.sh --self-test

python3 -m py_compile   scripts/bootstrap_env.py   scripts/check_env.py   scripts/validate_release_config.py
python3 scripts/validate_release_config.py --env-file .env.example --mode template

for path in   Dockerfile.production compose.yaml requirements.lock requirements.hashed.lock   requirements-dev.lock docs/INSTALLATION.md docs/REBUILD_RESTORE.md   .github/workflows/v0.3.0-rc.yml naseri.sh scripts/manager.sh; do
  test -s "$path"
done
grep -Fxq 'ruff==0.16.9' requirements-dev.lock
grep -Fxq 'pytest==9.1.1' requirements-dev.lock
grep -Fq 'version-v0.3.2' README.md

echo STAGED_STATIC_VERIFICATION_PASS
