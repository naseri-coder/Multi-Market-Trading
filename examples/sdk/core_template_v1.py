"""Example *inert* third-party worker for the Stage-4 isolated JSON ABI.

Demonstrates reading CoreInput data without choosing provider/symbol/account.
This template intentionally produces NO_SETUP. Not a trading strategy.
Only run it in a reviewed, disposable gVisor worker; never in the host bot.
"""
import json
import sys

request = json.load(sys.stdin)
event = request["event"]
reply = {
    "abi_major": request["abi_major"],
    "abi_minor": request["abi_minor"],
    "core_id": event["core_id"],
    "core_version": event["core_version"],
    "instance_id": event["binding"]["instance_id"],
    "binding_id": event["binding"]["binding_id"],
    "observed_at": event["observed_at"],
    "input_digest": request["input_digest"],
    "decisions": [{
        "decision_id": "no_setup_for_sample", "kind": "no_setup",
    }],
}
print(json.dumps(reply, sort_keys=True))
