"""Stage30 tests use in-memory ASGI calls: NO sockets, SSL listener or Docker."""
from __future__ import annotations

import asyncio
import base64
import json

import pytest

pytest.importorskip("cryptography")

from naseri_markets.a24_publisher_admission import canonical
from naseri_markets.authenticated_developer_intake_stage29_v1 import _LOGIN_DOMAIN
from naseri_markets.offline_developer_api_stage30_v1 import (
    OfflineDeveloperAsgiGateway, ReviewedUploadTarget, Stage30Refused,
)
from naseri_markets.publisher_package_registry_stage28_v1 import Stage28Refused
from test_durable_isolated_core_gate_stage22_v1 import host  # noqa: F401
from test_signed_core_candidate_stage23_v1 import trusted  # noqa: F401
from test_publisher_package_registry_stage28_v1 import (
    KEY_ID, NOW, PUB, TENANT, roster, submit_args,  # noqa: F401
)
from test_authenticated_developer_intake_stage29_v1 import intake  # noqa: F401


@pytest.fixture
def api(intake):  # noqa: F811
    gateway, ticks, signer, original = intake
    registry, _stage22, witness, *_ = original
    a = submit_args(original)
    app = OfflineDeveloperAsgiGateway(
        gateway, reviewed_targets={
            "binding_a": ReviewedUploadTarget(
                manifest=a["manifest"], binding=a["binding"],
                signed_witness=witness, pinned_image=a["expected_image"])},
        operator_ack=True)
    return app, gateway, ticks, signer, original


def request(app, path, data=None, *, token=None, method="POST",
            scheme="https", client="127.0.0.1", extra_headers=(),
            query=b"", raw_body=None, declared=None, parts=None):
    body = (canonical({} if data is None else data)
            if raw_body is None else raw_body)
    headers = ([] if method=="GET" else [(b"content-type",b"application/json")])
    if token is not None:
        headers.append((b"authorization", ("Bearer "+token).encode("ascii")))
    if declared is not None:
        headers.append((b"content-length", str(declared).encode("ascii")))
    headers.extend(extra_headers)
    events = []
    async def send(value):
        events.append(value)
    pieces = [body] if parts is None else parts
    tasks = [
        {"type":"http.request","body":part,"more_body":i<len(pieces)-1}
        for i,part in enumerate(pieces)
    ]
    async def receive():
        return tasks.pop(0)
    async def run():
        await app({
            "type":"http", "scheme":scheme,
            "client":(client,12345), "method":method,"path":path,
            "query_string":query,"headers":headers,
        },receive,send)
    asyncio.run(run())
    assert len(events)==2
    assert events[0]["type"]=="http.response.start"
    assert events[1]["type"]=="http.response.body"
    assert b"no-store" in dict(events[0]["headers"])[b"cache-control"]
    assert b"nosniff"==dict(events[0]["headers"])[b"x-content-type-options"]
    return events[0]["status"], json.loads(events[1]["body"])


def session(api, *, client="127.0.0.1"):
    app, _intake, _ticks, signer, _original = api
    status, out = request(app,"/v1/developers/challenge",{
        "tenant_id":TENANT,"publisher":PUB,"key_id":KEY_ID,
    },client=client)
    assert status==200
    claim=out["challenge"]
    assert out["public_plugin_install_authorized"] is False
    signature=base64.b64encode(
        signer.sign(_LOGIN_DOMAIN+canonical(claim))).decode("ascii")
    status, out = request(app,"/v1/developers/session",{
        "challenge":claim,"signature_b64":signature,
    },client=client)
    assert status==200, out
    assert not out["broker_order_authorized"]
    return out["token"],claim,signature


def post(api, token, *, path="/v1/developers/quarantine",
         body=None, client="127.0.0.1"):
    app,_gateway,_clock,_signer,original=api
    args=submit_args(original)
    payload=(body if body is not None else {
        "binding_id":"binding_a",
        "package_b64":base64.b64encode(args["package"]).decode("ascii"),
        "candidate_b64":base64.b64encode(args["signed_candidate"]).decode("ascii"),
    })
    return request(app,path,payload,token=token,client=client)


def test_full_http_shaped_crypto_login_and_one_time_inert_submission(api,monkeypatch):
    app,gateway,_ticks,_signer,original=api
    registry,stage22,_witness,*_=original
    calls=[]
    monkeypatch.setattr(stage22.host,"evaluate",
                        lambda *_args,**_kwargs:calls.append("not_allowed"))
    token,_claim,_sig=session(api)
    status,me=request(app,"/v1/developers/me",method="GET",
                      raw_body=b"",token=token)
    assert status==200
    assert me["tenant_id"]==TENANT
    assert me["scope"]=="QUARANTINE_SUBMIT_ONCE"
    status,result=post(api,token)
    assert status==202,result
    assert result["state"]=="QUARANTINED_PUBLIC_SOURCE_NOT_EXECUTABLE"
    assert result["public_plugin_install_authorized"] is False
    assert result["source_execution_authorized"] is False
    assert result["telegram_publish_authorized"] is False
    assert result["broker_order_authorized"] is False
    assert stage22.state(TENANT,"binding_a")["state"]=="DISABLED"
    assert stage22.state(TENANT,"binding_a")["public_untrusted_intake_pending"]
    assert stage22.db.execute(
        "SELECT state FROM secure29_sessions").fetchone()[0]=="CONSUMED"
    assert len(tuple(registry.quarantine_dir.iterdir()))==1
    assert calls==[]
    status,replay=post(api,token)
    assert status==403
    assert "token" not in str(replay).lower()
    status,_=request(app,"/v1/developers/me",method="GET",
                     raw_body=b"",token=token)
    assert status==403


def test_authentication_replay_fake_key_and_wrong_issuer(api):
    app,gateway,_ticks,signer,_original=api
    _,claim,signature=session(api)
    status,code=request(app,"/v1/developers/session",{
        "challenge":claim,"signature_b64":signature,
    })
    assert status==403
    assert "token" not in code
    status,_=request(app,"/v1/developers/session",{
        "challenge":{**claim,"tenant_id":"tenant_beta"},
        "signature_b64":signature,
    })
    assert status==403


def test_logout_irrevocably_invalidates_session(api):
    app,*_=api
    token,_,_=session(api)
    status,data=request(app,"/v1/developers/logout",{},token=token)
    assert status==200 and data["state"]=="SESSION_REVOKED"
    assert request(app,"/v1/developers/me",method="GET",
                   raw_body=b"",token=token)[0]==403
    assert post(api,token)[0]==403


def test_expired_token_and_retired_signer_fail_closed(api):
    app,gateway,ticks,_signer,original=api
    token,_,_=session(api)
    ticks[0]+=301
    assert post(api,token)[0]==403
    ticks[0]=NOW
    token2,_,_=session(api,client="127.0.0.2")
    registry,*_=original
    registry.revoke(tenant_id=TENANT,publisher=PUB,
                    key_id=KEY_ID,expected_revision=1,now=NOW,
                    operator_ack=True)
    assert post(api,token2,client="127.0.0.2")[0]==403


def test_bad_package_scope_cannot_touch_existing_binding(api):
    app,gateway,ticks,_signer,original=api
    token,_,_=session(api)
    status,error=post(api,token,body={
        "binding_id":"unknown_external_core",
        "package_b64":"YQ==","candidate_b64":"YQ==",
    })
    assert status==403 and "UNREVIEWED" in error["error"]
    assert not original[1].db.execute(
        "SELECT 1 FROM secure22_bindings").fetchone()
    assert gateway.status(token=token)["tenant_id"]==TENANT


@pytest.mark.parametrize("bad", [
    {"binding_id":"binding_a","package_b64":"%%%","candidate_b64":"YQ=="},
    {"binding_id":"binding_a","package_b64":"YQ==","candidate_b64":"fake"},
    {"binding_id":"binding_a","package_b64":"YQ==","candidate_b64":"YQ==",
     "secret":"extra"},
    {"binding_id":123,"package_b64":"YQ==","candidate_b64":"YQ=="},
])
def test_bad_base64_wrong_types_and_extra_fields_refused(api,bad):
    token,_,_=session(api)
    status,_=post(api,token,body=bad)
    assert status in (400,403)
    assert not api[-1][1].db.execute("SELECT 1 FROM secure22_bindings").fetchone()


def test_content_length_header_smuggling_and_trust_boundaries(api):
    app,*_=api
    opts=dict(tenant_id=TENANT,publisher=PUB,key_id=KEY_ID)
    route="/v1/developers/challenge"
    assert request(app,route,opts,scheme="http")[0]==403
    assert request(app,route,opts,client="spoofed")[0]==403
    assert request(app,route,opts,extra_headers=[
        (b"x-forwarded-for",b"127.0.0.1")])[0]==400
    assert request(app,route,opts,extra_headers=[
        (b"transfer-encoding",b"chunked")])[0]==400
    assert request(app,route,opts,extra_headers=[
        (b"content-type",b"application/json")])[0]==400
    assert request(app,route,opts,extra_headers=[
        (b"cookie",b"session=attacker")])[0]==400
    assert request(app,route,opts,query=b"debug=1")[0]==405
    assert request(app,route,opts,declared=999999)[0]==413
    assert request(app,route,opts,declared=3)[0]==400
    assert request(app,route,opts,method="GET")[0]==405
    assert request(app,route,opts,raw_body=b'{"tenant_id":"x",'
                   b'"tenant_id":"x","publisher":"x","key_id":"x"}')[0]==400


def test_bounded_chunks_body_size_and_denied_paths(api):
    app,*_=api
    route="/v1/developers/challenge"
    assert request(app,route,raw_body=b"x"*9000)[0]==413
    assert request(app,route,parts=[b"x"]*33)[0]==413
    assert request(app,route,raw_body=b'{"tenant_id":NaN}')[0]==400
    assert request(app,"/v1/developers/admin/install",{})[0]==404
    assert request(app,"/v1/developers/live-trading",{})[0]==404


def test_atomic_rate_limit_shared_by_different_gateway_instances(api):
    app,gateway,*_=api
    other=OfflineDeveloperAsgiGateway(
        gateway,reviewed_targets=app.targets,operator_ack=True)
    for i in range(12):
        which=app if i%2==0 else other
        status,_=request(which,"/v1/developers/not-a-real-route",{})
        assert status==404
    assert request(other,"/v1/developers/not-a-real-route",{})[0]==429
    # No client-provided XFF override; other peer has a separate quota.
    assert request(other,"/v1/developers/not-a-real-route",{},
                   client="127.0.0.2")[0]==404


def test_session_token_rejected_as_body_and_request_framing(api):
    app,*_=api
    token,_,_=session(api)
    assert request(app,"/v1/developers/quarantine",
                   {"token":token},token=token)[0]==400
    assert request(app,"/v1/developers/logout",{},
                   token=token,extra_headers=[
                       (b"authorization",b"Bearer wrong")])[0]==400
    assert request(app,"/v1/developers/me",method="GET",
                   raw_body=b"x",token=token)[0]==400


def test_missing_operator_ack_and_research_only_environment(api,monkeypatch):
    app,gateway,*_=api
    with pytest.raises(Stage30Refused):
        OfflineDeveloperAsgiGateway(
            gateway,reviewed_targets=app.targets,operator_ack=False)
    monkeypatch.setenv("MMT_PRODUCTION","1")
    with pytest.raises(Stage28Refused):
        OfflineDeveloperAsgiGateway(
            gateway,reviewed_targets=app.targets,operator_ack=True)
