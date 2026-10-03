#!/usr/bin/env python3
"""Check future runner Compose plan without printing resolved environment values."""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('RUNNER_ONLY: Compose configuration preflight')
project = os.environ.get('TEST_PROJECT', '')
run_id = os.environ.get('GITHUB_RUN_ID', '')
attempt = os.environ.get('GITHUB_RUN_ATTEMPT', '')
if not run_id.isdecimal() or not attempt.isdecimal() or project != f'stage3b-{run_id}-{attempt}':
    raise SystemExit('Invalid disposable project identity')
cmd = ['docker','compose','-p',project,'-f','compose.yaml','--env-file','.env',
       'config','--format','json']
result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
if result.returncode != 0:
    raise SystemExit('Compose preflight failed (details suppressed)')
config = json.loads(result.stdout)
services = config['services']
assert set(services) == {'bot','postgres'}
for name in ('bot','postgres'):
    svc = services[name]
    assert not svc.get('ports') and not svc.get('privileged', False)
    assert svc.get('network_mode') not in ('host','service:host')
assert services['bot'].get('read_only') is True
assert not services['bot'].get('volumes')
volumes = services['postgres'].get('volumes', [])
assert len(volumes) == 1 and volumes[0]['type'] == 'volume'
assert all(not net.get('external', False) for net in config.get('networks', {}).values())
bot_env = services['bot'].get('environment', {})
for flag in ('TELEGRAM_RUNTIME_ENABLED','BROOKS_RUNTIME_ENABLED',
             'BROOKS_OPERATIONS_ENABLED','PAPER_RUNTIME_ENABLED',
             'PERFORMANCE_REPORTS_ENABLED','DB_ECHO'):
    assert str(bot_env.get(flag, '')).lower() == 'false'
assert not bot_env.get('TELEGRAM_BOT_TOKEN')
print('COMPOSE_ISOLATION_PREFLIGHT_PASS: no ports, no bind mounts, runtime disabled')
