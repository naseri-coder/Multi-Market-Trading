import hashlib, json
from decimal import Decimal
from pathlib import Path

FIXTURE=Path(__file__).resolve().parents[1]/'fixtures'/'phase_4_2_41_84_exact_14_candidates.json'
EXPECTED_SHA='328eac08ea98bdd4d4b22922efecf6750f0cdfbedfe5550607123bebd98405d3'

def test_exact_fixture_sha_and_count_are_frozen():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest()==EXPECTED_SHA
    data=json.loads(FIXTURE.read_text())
    assert data['candidate_count']==14 and len(data['candidates'])==14
    assert len({x['identity_sha256'] for x in data['candidates']})==14

def test_exact_fixture_geometry_is_directionally_valid():
    for x in json.loads(FIXTURE.read_text())['candidates']:
        entry=Decimal(x['entry']); stop=Decimal(x['stop']); targets=[Decimal(v) for v in x['targets']]
        if x['direction']=='LONG': assert stop<entry and all(t>entry for t in targets)
        else: assert stop>entry and all(t<entry for t in targets)
