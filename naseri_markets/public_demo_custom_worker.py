"""Public toy Custom plugin (offline PAPER demo), NOT a trading strategy.

External ABI stdin: JSON {abi_version,engine_id,engine_version,tick}; stdout:
A7 exact PAPER SignalIntent envelope OR {"status":"no_signal"}.
No network, imports from the platform, broker/order or private IP.
"""
import hashlib
import json
import sys
from decimal import Decimal

def main():
    raw = sys.stdin.buffer.read(2048)
    request = json.loads(raw)
    tick = request["tick"]
    if request["abi_version"] != 1 or request["engine_id"] != "public_toy_demo":
        raise ValueError("DEMO_CONTRACT_MISMATCH")
    if request["engine_version"] != "1.0.0":
        raise ValueError("DEMO_VERSION_MISMATCH")
    if tick["origin"] not in ("replay", "synthetic"):
        raise ValueError("DEMO_LIVE_DENIED")
    ask = Decimal(tick["ask"])
    bid = Decimal(tick["bid"])
    if ask - bid > ask / Decimal("100"):
        print('{"status":"no_signal"}')
        return
    risk = min(ask / Decimal("100"), Decimal("30"))
    if ask <= risk:
        print('{"status":"no_signal"}')
        return
    fingerprint = hashlib.sha256(json.dumps(
        [tick["market"], tick["provider"], tick["symbol"],
         tick["occurred_at"]], separators=(",", ":")).encode()).hexdigest()[:20]
    envelope = {
        "abi_version": 1,
        "signal_id": "toy-" + fingerprint,
        "engine_id": "public_toy_demo",
        "engine_version": "1.0.0",
        "market": tick["market"],
        "provider": tick["provider"],
        "symbol": tick["symbol"],
        "timezone": tick["timezone"],
        "quote_currency": tick["quote_currency"],
        "direction": "long",
        "observed_at": tick["occurred_at"],
        "entry": str(ask),
        "stop": str(ask-risk),
        "targets": [str(ask+2*risk)],
        "evidence_mode": "paper",
    }
    sys.stdout.write(json.dumps(envelope, separators=(",", ":"))+"\n")

if __name__ == "__main__":
    main()
