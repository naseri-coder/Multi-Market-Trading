"""CI-only owner-side fixture PROCESS, never an actual private trading engine.

Run only in an ephemeral GitHub-hosted Actions runner; binds 127.0.0.1 and
accepts strictly synthetic US30 quotes. All certificates/keys are generated
per test outside the Git repository and never printed or committed.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import secrets
import ssl
import time
from pathlib import Path

from naseri_markets.a11_mtls import (
    make_fixture_server_context, read_frame, send_frame,
)
from naseri_markets.private_protocol import (
    ProtocolRefused, ReplayFence, sign_packet, verify_packet,
)

CLIENT_ID = "public-bot.fixture"


def checked_key(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size != 32:
        raise ValueError("A11_EPHEMERAL_KEY_REQUIRED")
    return path.read_bytes()


def response_for(request: dict, *, now: int) -> dict:
    payload = request["payload"]
    if not isinstance(payload, dict) or set(payload) != {"operation", "tick"}:
        raise ProtocolRefused("A11_FIXTURE_PAYLOAD")
    if payload["operation"] != "paper_analysis":
        raise ProtocolRefused("A11_FIXTURE_OPERATION")
    tick = payload["tick"]
    expected = {
        "market": "index", "provider": "fixture:quotes", "symbol": "US30",
        "timezone": "UTC", "quote_currency": "USD",
        "bid": "43000", "ask": "43001", "origin": "synthetic",
    }
    if not isinstance(tick, dict) or set(tick) != {*expected, "occurred_at"}:
        raise ProtocolRefused("A11_FIXTURE_TICK_FIELDS")
    if any(tick[k] != v or type(tick[k]) is not str for k, v in expected.items()):
        raise ProtocolRefused("A11_FIXTURE_TICK_SCOPE")
    timestamp = tick["occurred_at"]
    if type(timestamp) is not str or len(timestamp) > 48:
        raise ProtocolRefused("A11_FIXTURE_TICK_TIMESTAMP")
    # No algorithm is run. This invented fixture intent is always PAPER.
    signal = {
        "abi_version": 1,
        "signal_id": "a11-fixture-" + request["nonce"],
        "engine_id": "private_example",
        "engine_version": "1.0.0",
        "market": expected["market"], "provider": expected["provider"],
        "symbol": expected["symbol"], "timezone": expected["timezone"],
        "quote_currency": expected["quote_currency"],
        "direction": "long", "observed_at": timestamp,
        "entry": "43000", "stop": "42980", "targets": ["43070"],
        "evidence_mode": "paper",
    }
    return {
        "version": 1, "key_id": "owner_k1", "direction": "to_bot",
        "engine_id": "private_example", "engine_version": "1.0.0",
        "nonce": secrets.token_hex(16),
        "request_nonce": request["nonce"],
        "issued_at": now, "expires_at": now + 20,
        "payload": {
            "operation": "paper_analysis",
            "paper_envelope_b64": base64.b64encode(
                json.dumps(signal, sort_keys=True).encode("ascii")
            ).decode("ascii"),
        },
    }


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cert", type=Path, required=True)
    p.add_argument("--key", type=Path, required=True)
    p.add_argument("--ca", type=Path, required=True)
    p.add_argument("--client-hmac", type=Path, required=True)
    p.add_argument("--owner-hmac", type=Path, required=True)
    p.add_argument("--replay-db", type=Path, required=True)
    options = p.parse_args()

    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        raise SystemExit("A11_FIXTURE_REQUIRES_EPHEMERAL_GITHUB_RUNNER")

    context = make_fixture_server_context(
        ca=options.ca, cert=options.cert, key=options.key,
    )
    client_hmac = checked_key(options.client_hmac)
    owner_hmac = checked_key(options.owner_hmac)
    fence = ReplayFence(options.replay_db)

    async def handle(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ) -> None:
        try:
            peer = writer.get_extra_info("peercert")
            if not isinstance(peer, dict) or (
                "DNS", CLIENT_ID
            ) not in peer.get("subjectAltName", ()):
                return
            packet = await asyncio.wait_for(read_frame(reader), timeout=2)
            now = int(time.time())
            request = verify_packet(
                packet, key=client_hmac, key_id="client_k1",
                direction="to_owner", engine_id="private_example",
                engine_version="1.0.0", now=now,
            )
            answer = response_for(request, now=now)
            # Consume only validated requests. Replayed requests do not
            # produce another reply or trigger any strategy callback.
            fence.consume(
                direction="to_owner", key_id="client_k1",
                nonce=request["nonce"],
            )
            await asyncio.wait_for(
                send_frame(writer, sign_packet(answer, key=owner_hmac)),
                timeout=2,
            )
        except (ProtocolRefused, ValueError, asyncio.TimeoutError,
                asyncio.IncompleteReadError, ConnectionError, OSError):
            # No credentials, broker data or packet bodies in logs.
            return
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=0.3)
            except (asyncio.TimeoutError, ssl.SSLError, OSError):
                pass

    server = await asyncio.start_server(
        handle, host="127.0.0.1", port=0, ssl=context,
        ssl_handshake_timeout=2,
    )
    port = server.sockets[0].getsockname()[1]
    print(f"A11_FIXTURE_READY:{port}", flush=True)
    async with server:
        try:
            await server.serve_forever()
        finally:
            fence.close()


if __name__ == "__main__":
    asyncio.run(main())
