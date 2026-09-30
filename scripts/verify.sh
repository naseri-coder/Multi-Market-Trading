#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
test "$(wc -l < production_source/SHA256SUMS)" -eq 348
( cd production_source && sha256sum --status -c SHA256SUMS )
python3 - <<'PY'
from pathlib import Path
import ast,hashlib
root=Path('production_source')
entries=[]
for line in (root/'SHA256SUMS').read_text().splitlines():
    digest,rel=line.split('  ',1)
    item=Path(rel)
    assert not item.is_absolute() and '..' not in item.parts
    full=root/item
    assert full.is_file() and not full.is_symlink()
    assert hashlib.sha256(full.read_bytes()).hexdigest()==digest
    entries.append(rel)
assert len(entries)==348 and len(set(entries))==348
parsed=0
for rel in entries:
    if rel.endswith('.py'):
        ast.parse((root/rel).read_bytes(),filename=rel)
        parsed+=1
ast.parse(Path('production_checks/verify_historical_probability_regression.py').read_bytes())
print('SOURCE_SHA256_PASS entries=348; PYTHON_AST_PASS count='+str(parsed))
PY
bash -n scripts/install.sh scripts/verify.sh
python3 -m py_compile scripts/bootstrap_env.py scripts/check_env.py
test -f Dockerfile.production && test -f compose.yaml && test -f requirements.lock
echo STAGED_STATIC_VERIFICATION_PASS
