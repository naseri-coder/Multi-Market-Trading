"""R42 local synthetic, ephemeral keys; no actual market/provider account used."""
import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts import mmt_r42_signed_market_account_audit_v1 as r

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


def wire(v):
    return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode() + b'\n'


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    monkeypatch.setenv('MMT_NONPRODUCTION', '1')
    monkeypatch.delenv('MMT_PRODUCTION', raising=False)
    root = tmp_path / 'private'
    root.mkdir(mode=0o700)
    policy = {
        'schema':1,'purpose':'OFFLINE_RESEARCH_ONLY','venue':'synthetic_venue',
        'market':'CRYPTO','instrument_id':'contract_100', 'symbol':'BTCUSDT',
        'timeframe':'5m','account_id':'paper_account', 'currency':'USDT',
        'region_status':'UNVERIFIED_FOR_TRADING','session_status':'UNVERIFIED_FOR_TRADING',
        'price_tick':'0.01','max_feed_age_seconds':60,
        'max_account_age_seconds':60, 'max_pair_skew_seconds':15,
        'max_spread_bps':10,'max_equity_diff':'0.01',
        'max_exposure_diff':'0.01','min_feed_sequence':50,
        'min_account_sequence':200,'valid_from':'2026-10-16T11:00:00Z',
        'valid_until':'2026-10-16T13:00:00Z'
    }
    feed = {
        'schema':1,'origin':'OFFLINE_UNVERIFIED_CAPTURE', 'venue':'synthetic_venue',
        'market':'CRYPTO','instrument_id':'contract_100','symbol':'BTCUSDT','timeframe':'5m',
        'sequence':50,'bar_open_at':'2026-10-16T11:55:00Z',
        'bar_close_at':'2026-10-16T12:00:00Z','captured_at':'2026-10-16T12:00:00Z',
        'open':'100.00','high':'102.00','low':'99.00', 'close':'101.00',
        'volume':'10','bid':'100.99','ask':'101.01',
        'price_basis':'TRADE','volume_semantics':'TRADED'
    }
    primary = {
        'schema':1,'origin':'OFFLINE_PRIMARY_CAPTURE','venue':'synthetic_venue',
        'account_id':'paper_account','currency':'USDT',
        'observed_at':'2026-10-16T12:00:00Z','equity':'1000.00',
        'gross_exposure':'50.00','open_order_ids':['order_0001','order_0002'],
        'position_ids':['pos_0001'],
        'sequence':200
    }
    review = copy.deepcopy(primary)
    review['origin']='OFFLINE_INDEPENDENT_REVIEW'
    records={'feed':feed, 'primary':primary, 'review':review}
    keys={role:Ed25519PrivateKey.generate() for role in records}
    args={'policy_path':root/'policy.json','policy_sha256':'', 'now':NOW}

    def sign_role(role):
        raw=wire(records[role]); args[role+'_path']=root/(role+'.json')
        args[role+'_path'].write_bytes(raw)
        args[role+'_signature']=root/(role+'.sig')
        tag={'feed':'FEED','primary':'ACCOUNT_PRIMARY','review':'ACCOUNT_REVIEW'}[role]
        args[role+'_signature'].write_bytes(keys[role].sign(('MMT-R42-'+tag+'-V1\n').encode()+raw))
        args[role+'_public_key']=root/(role+'.pem')
        pub=keys[role].public_key()
        args[role+'_public_key'].write_bytes(pub.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        spki=pub.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
        args[role+'_key_spki_sha256']=hashlib.sha256(spki).hexdigest()
        args[role+'_sha256']=hashlib.sha256(raw).hexdigest()

    def sign_policy():
        raw=wire(policy)
        args['policy_path'].write_bytes(raw)
        args['policy_sha256']=hashlib.sha256(raw).hexdigest()

    def refresh():
        sign_policy()
        for role in records:
            sign_role(role)

    refresh()
    return args,policy,records,refresh,keys


def verify(case):
    return r.audit(**case[0])


def test_good_three_distinct_signed_captures_release_denied(evidence):
    result=verify(evidence)
    assert result['verdict']=='R42_SIGNED_OFFLINE_CAPTURES_CONSISTENT_RELEASE_DENIED'
    assert result['three_distinct_pinned_signers_verified']
    for name in ('real_provider_provenance_verified','real_account_reconciliation_verified',
                 'venue_session_and_region_eligible','broker_order_authorized',
                 'telegram_authorized','live_authorized','public_release_authorized',
                 'files_written'):
        assert result[name] is False


def test_no_files_modified(evidence):
    args=evidence[0]
    before={p:p.read_bytes() for p in args.values() if isinstance(p,Path)}
    assert verify(evidence)==verify(evidence)
    assert all(p.read_bytes()==old for p,old in before.items())


@pytest.mark.parametrize('field,value,part',[
    ('policy_sha256','0'*64,'POLICY_PIN_MISMATCH'),
    ('feed_sha256','0'*64,'SIGNED_PAYLOAD_PIN_MISMATCH'),
    ('primary_sha256','0'*64,'SIGNED_PAYLOAD_PIN_MISMATCH'),
    ('review_sha256','0'*64,'SIGNED_PAYLOAD_PIN_MISMATCH'),
    ('feed_key_spki_sha256','0'*64,'TRUSTED_KEY_MISMATCH')])
def test_wrong_external_pin_denied(evidence,field,value,part):
    evidence[0][field]=value
    with pytest.raises(r.R42Refused,match=part): verify(evidence)


@pytest.mark.parametrize('role', ['feed','primary','review'])
def test_bad_signature_denied(evidence,role):
    evidence[0][role+'_signature'].write_bytes(b'X'*64)
    with pytest.raises(r.R42Refused,match='INVALID_SIGNATURE'): verify(evidence)


@pytest.mark.parametrize('role', ['feed','primary','review'])
def test_missing_signature_denied(evidence,role):
    evidence[0][role+'_signature'].unlink()
    with pytest.raises(r.R42Refused,match='FILE_UNREADABLE'): verify(evidence)


def test_reused_key_fingerprint_denied(evidence):
    evidence[0]['review_key_spki_sha256']=evidence[0]['primary_key_spki_sha256']
    with pytest.raises(r.R42Refused,match='INDEPENDENT_SIGNERS'): verify(evidence)


def test_bad_venue_policy_denied(evidence):
    _,p,_,refresh,_=evidence
    p['region_status']='ALLOWED'
    refresh()
    with pytest.raises(r.R42Refused,match='TRADING_ELIGIBILITY'): verify(evidence)


def test_expired_policy_denied(evidence):
    _,p,_,refresh,_=evidence
    p['valid_until']='2026-10-16T11:00:00Z';refresh()
    with pytest.raises(r.R42Refused,match='POLICY_EXPIRED'):verify(evidence)


def test_replayed_feed_sequence_denied(evidence):
    _,_,records,refresh,_=evidence
    records['feed']['sequence']=49;refresh()
    with pytest.raises(r.R42Refused,match='FEED_SEQUENCE_REPLAY'):verify(evidence)


def test_future_feed_denied(evidence):
    _,_,records,refresh,_=evidence
    records['feed']['captured_at']='2026-10-16T12:00:01Z';refresh()
    with pytest.raises(r.R42Refused,match='STALE_OR_CAUSALLY'):verify(evidence)


def test_stale_account_denied(evidence):
    _,_,records,refresh,_=evidence
    records['primary']['observed_at']='2026-10-16T11:58:59Z';refresh()
    with pytest.raises(r.R42Refused,match='CAPTURE_STALE'):verify(evidence)


@pytest.mark.parametrize('field,value', [
    ('equity','1001.00'),('gross_exposure','51.00'),
    ('open_order_ids',['other_order']),('position_ids',['pos_other']),
    ('sequence',201)])
def test_disagreement_denied(evidence,field,value):
    _,_,records,refresh,_=evidence
    records['review'][field]=value;refresh()
    with pytest.raises(r.R42Refused,match='DISAGREE'):verify(evidence)


def test_order_list_duplicate_denied(evidence):
    _,_,records,refresh,_=evidence
    records['primary']['open_order_ids']=['a_order','a_order'];refresh()
    with pytest.raises(r.R42Refused,match='ORDER_IDS_INVALID'):verify(evidence)


def test_feed_bad_spread_denied(evidence):
    _,_,records,refresh,_=evidence
    records['feed']['ask']='102.00';refresh()
    with pytest.raises(r.R42Refused,match='INVALID_OHLC_SPREAD'):verify(evidence)


def test_feed_bad_tick_denied(evidence):
    _,_,records,refresh,_=evidence
    records['feed']['close']='101.005';refresh()
    with pytest.raises(r.R42Refused,match='INVALID_OHLC_SPREAD'):verify(evidence)


def test_skewed_accounts_denied(evidence):
    _,_,records,refresh,_=evidence
    records['review']['observed_at']='2026-10-16T11:59:30Z';refresh()
    with pytest.raises(r.R42Refused,match='TIME_SKEW'):verify(evidence)


@pytest.mark.parametrize('flag',['0','1','true',''])
def test_explicit_production_denied(evidence,monkeypatch,flag):
    monkeypatch.setenv('MMT_PRODUCTION',flag)
    with pytest.raises(r.R42Refused,match='NONPRODUCTION'):verify(evidence)


def test_unsigned_modified_payload_denied(evidence):
    _,_,records,refresh,_=evidence
    records['feed']['volume']='100';refresh()
    evidence[0]['feed_path'].write_bytes(evidence[0]['feed_path'].read_bytes().replace(
        b'"volume":"100"', b'"volume":"200"'))
    with pytest.raises(r.R42Refused,match='SIGNED_PAYLOAD_PIN_MISMATCH'):verify(evidence)


def test_bad_origin_denied(evidence):
    _,_,records,refresh,_=evidence
    records['feed']['origin']='LIVE';refresh()
    with pytest.raises(r.R42Refused,match='FEED_ORIGIN'):verify(evidence)


def test_bad_account_origin_denied(evidence):
    _,_,records,refresh,_=evidence
    records['review']['origin']='OFFLINE_PRIMARY_CAPTURE';refresh()
    with pytest.raises(r.R42Refused,match='ACCOUNT_IDENTITY'):verify(evidence)


def test_policy_duplicate_field_denied(evidence):
    args=evidence[0]
    before=args['policy_path'].read_bytes()
    bad=before.strip()[:-1]+b',"schema":1}\n'
    args['policy_path'].write_bytes(bad)
    args['policy_sha256']=hashlib.sha256(bad).hexdigest()
    with pytest.raises(r.R42Refused,match='DUPLICATE_JSON_FIELD'):verify(evidence)


def test_signed_feed_wrong_timeframe_denied(evidence):
    _,_,records,refresh,_=evidence
    records['feed']['timeframe']='15m';refresh()
    with pytest.raises(r.R42Refused,match='FEED_IDENTITY'):verify(evidence)


def test_bad_signed_account_future_denied(evidence):
    _,_,records,refresh,_=evidence
    records['review']['observed_at']='2026-10-16T12:00:30Z';refresh()
    with pytest.raises(r.R42Refused,match='CAPTURE_STALE'):verify(evidence)


def test_invalid_account_numeric_denied(evidence):
    _,_,records,refresh,_=evidence
    records['primary']['equity']='NaN';refresh()
    with pytest.raises(r.R42Refused,match='DECIMAL_FORMAT'):verify(evidence)


@pytest.mark.parametrize('role', ['feed','primary','review'])
def test_key_symlink_denied(evidence,role):
    args=evidence[0]
    link=args[role+'_public_key'].with_name(role+'.link')
    link.symlink_to(args[role+'_public_key'])
    args[role+'_public_key']=link
    with pytest.raises(r.R42Refused,match='REGULAR_ABSOLUTE_UNLINKED'):verify(evidence)


def test_feed_account_cross_skew_denied(evidence):
    _,_,records,refresh,_=evidence
    records['review']['observed_at']='2026-10-16T11:59:44Z'
    records['primary']['observed_at']='2026-10-16T11:59:44Z'
    refresh()
    with pytest.raises(r.R42Refused, match='TIME_SKEW'):verify(evidence)


def test_unhashable_timeframe_denied(evidence):
    _,policy,_,refresh,_=evidence
    policy['timeframe']=['5m'];refresh()
    with pytest.raises(r.R42Refused,match='POLICY_TIMEFRAME_INVALID'):verify(evidence)


def test_decimal_overprecision_in_signed_feed_denied(evidence):
    _,_,records,refresh,_=evidence
    huge='999999999999999999999999999999999999999.00'
    for field in ('open','high','low','close','bid','ask'):
        records['feed'][field]=huge
    refresh()
    with pytest.raises(r.R42Refused, match='DECIMAL_PRECISION_UNSAFE'):
        verify(evidence)


def test_feed_wrong_volume_semantics_denied(evidence):
    _, _, records, refresh, _ = evidence
    records['feed']['volume_semantics'] = 'UNKNOWN'
    refresh()
    with pytest.raises(r.R42Refused, match='FEED_ORIGIN_OR_SEMANTICS_INVALID'):
        verify(evidence)


def test_cross_currency_account_review_denied(evidence):
    _, _, records, refresh, _ = evidence
    records['review']['currency'] = 'USD'
    refresh()
    with pytest.raises(r.R42Refused, match='ACCOUNT_IDENTITY_OR_ORIGIN_MISMATCH'):
        verify(evidence)
