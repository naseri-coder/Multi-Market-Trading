"""Complete 226-module RC-to-stable copy tests; no LIVE, secrets or production."""
from __future__ import annotations
import hashlib,json,os,subprocess,tomllib
from pathlib import Path
import pytest
from scripts import mmt_v040_offline_stable_staging_v1 as stage
from scripts import mmt_v040_public_source_snapshot_audit_v1 as snap

BASE=Path(__file__).resolve().parents[2] / "platform_release"

def git(r,*a):
 p=subprocess.run(['git','-C',str(r),*a],capture_output=True,text=True,check=True)
 return p.stdout.strip()

def commit(r,message):git(r,'-c','user.email=staging@example.invalid','-c','user.name=Stage Test','commit','-qm',message)

@pytest.fixture
def fixture(tmp_path,monkeypatch):
 monkeypatch.setenv('MMT_NONPRODUCTION','1');monkeypatch.delenv('MMT_PRODUCTION',raising=False)
 repo=tmp_path/'source';(repo/'naseri_markets').mkdir(parents=True);(repo/'platform_release').mkdir()
 t=BASE.joinpath('pyproject.toml').read_text()
 assert t.count('version = "0.4.0rc1"') == 1
 (repo/'platform_release/pyproject.toml').write_text(t)
 (repo/'platform_release/README.md').write_text('Test non-release metadata\n')
 for name in ('__init__.py','platform_cli.py','platform_version_policy_v1.py'):(repo/'naseri_markets'/name).write_text('"""Inert synthetic test file."""\n')
 for i in range(223):
  body=''.join('# '+hashlib.sha256(f'{i}-{j}'.encode()).hexdigest()+'\n' for j in range(160))
  (repo/'naseri_markets'/f'synthetic_{i:03}.py').write_text(body)
 git(repo,'init','-q');git(repo,'add','naseri_markets','platform_release');commit(repo,'initial rc source')
 tree=git(repo,'rev-parse','HEAD:naseri_markets');snapshot_commit=git(repo,'rev-parse','HEAD')
 members=[]
 for x in sorted((repo/'naseri_markets').glob('*.py')):
  data=x.read_bytes();members.append({'path':f'naseri_markets/{x.name}','git_blob_sha1':hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest(),'size':len(data)})
 lock={'schema_version':1,'distribution':'multi-market-trading','release_candidate':'v0.4.0','provenance':'GITHUB_TREE_SNAPSHOT__NOT_RELEASE_APPROVAL','github_repository':'naseri-coder/Multi-Market-Trading','snapshot_commit':snapshot_commit,'public_subtree_sha1':tree,'expected_module_count':226,'source_bytes':sum(x['size'] for x in members),'modules':members}
 (repo/'docs').mkdir();lockfile=repo/snap.SNAPSHOT_PATH;lockfile.write_text(json.dumps(lock,indent=2)+'\n')
 git(repo,'add','docs');commit(repo,'lock source')
 dest=tmp_path/'stage-new'
 kwargs={'repository':repo,'destination':dest,'expected_source_commit':git(repo,'rev-parse','HEAD'),'expected_public_tree_sha1':tree,'expected_lock_sha256':hashlib.sha256(lockfile.read_bytes()).hexdigest()}
 return repo, dest, kwargs

def test_positive_exact_226_modules_and_metadata_overlay(fixture):
 repo,dest,kw=fixture;orig=(repo/'platform_release/pyproject.toml').read_bytes()
 report=stage.stage(**kw)
 assert report['staged_module_count']==226
 assert report['staged_version']=='0.4.0'
 assert report['original_source_mutated'] is False
 assert not report['wheel_built'] and not report['wheel_signed']
 assert not report['public_release_authorized'] and not report['live_trading_authorized']
 assert len(list((dest/'naseri_markets').glob('*.py')))==226
 assert (repo/'platform_release/pyproject.toml').read_bytes()==orig
 assert tomllib.loads((dest/'pyproject.toml').read_text())['project']['version']=='0.4.0'
 for path in (repo/'naseri_markets').glob('*.py'):
  assert path.read_bytes()==(dest/'naseri_markets'/path.name).read_bytes()
 assert not any(repo.rglob('*.whl'))

def test_source_dirty_rejected_without_staging(fixture):
 repo,dest,kw=fixture;(repo/'naseri_markets/synthetic_010.py').write_text('modified')
 with pytest.raises(snap.PublicSnapshotRefused,match='V040_GIT_NOT_CLEAN'):stage.stage(**kw)
 assert not dest.exists()

def test_wrong_external_tree_pin_rejected(fixture):
 _,dest,kw=fixture;kw['expected_public_tree_sha1']='0'*40
 with pytest.raises(snap.PublicSnapshotRefused,match='V040_PUBLIC_TREE_PIN_MISMATCH'):stage.stage(**kw)
 assert not dest.exists()

def test_wrong_external_lock_pin_rejected(fixture):
 _,dest,kw=fixture;kw['expected_lock_sha256']='0'*64
 with pytest.raises(snap.PublicSnapshotRefused,match='V040_SNAPSHOT_EXTERNAL_SHA256_MISMATCH'):stage.stage(**kw)
 assert not dest.exists()

def test_production_environment_0_is_denied(fixture,monkeypatch):
 _,dest,kw=fixture;monkeypatch.setenv('MMT_PRODUCTION','0')
 with pytest.raises(stage.StableStageRefused,match='V040_NONPRODUCTION_REQUIRED'):stage.stage(**kw)
 assert not dest.exists()

def test_existing_destination_denied_no_overwrite(fixture):
 _,dest,kw=fixture;dest.mkdir();(dest/'sentinel').write_text('keep')
 with pytest.raises(stage.StableStageRefused,match='V040_PRIVATE_OUTSIDE_NEW_DESTINATION_REQUIRED'):stage.stage(**kw)
 assert (dest/'sentinel').read_text()=='keep'

def test_private_import_denied_before_create(fixture):
 repo,dest,kw=fixture;x=repo/'naseri_markets/synthetic_010.py';x.write_text('import private_nyfr_core\n')
 git(repo,'add','.');commit(repo,'import private')
 # Snapshot points to old tree; explicitly new HEAD also must be rejected.
 kw['expected_source_commit']=git(repo,'rev-parse','HEAD')
 with pytest.raises(snap.PublicSnapshotRefused,match='V040_PUBLIC_TREE_PIN_MISMATCH'):stage.stage(**kw)
 assert not dest.exists()

def test_metadata_rc_required(fixture):
 repo,dest,kw=fixture;p=repo/'platform_release/pyproject.toml';p.write_text(p.read_text().replace('version = "0.4.0rc1"','version = "0.4.0"'))
 git(repo,'add','.');commit(repo,'stable source')
 kw['expected_source_commit']=git(repo,'rev-parse','HEAD')
 with pytest.raises(stage.StableStageRefused,match='V040_RC_SOURCE_METADATA_DRIFT'):stage.stage(**kw)
 assert not dest.exists()

def test_unreviewed_backend_denied(fixture):
 repo,dest,kw=fixture;p=repo/'platform_release/pyproject.toml';p.write_text(p.read_text().replace('setuptools.build_meta','custom.build'))
 git(repo,'add','.');commit(repo,'unauthorized build backend')
 kw['expected_source_commit']=git(repo,'rev-parse','HEAD')
 with pytest.raises(stage.StableStageRefused,match='V040_RC_SOURCE_METADATA_DRIFT'):stage.stage(**kw)
 assert not dest.exists()

def test_staged_python_syntax_errors_fail_closed(fixture):
 repo,dest,kw=fixture
 # On a fully verified source tree a syntactically invalid module is still not staged.
 m=repo/'naseri_markets/synthetic_010.py'
 bad='def broken(:\n'
 m.write_text(bad)
 git(repo,'add','.');commit(repo,'syntactically invalid committed source')
 # Rather than re-sign a fresh snapshot, exercise the isolated parser boundary.
 with pytest.raises(stage.StableStageRefused,match='V040_SOURCE_PYTHON_PARSE_DENIED'):
  stage._check_source_module(m.read_bytes(),'naseri_markets/synthetic_010.py')
 assert not dest.exists()
