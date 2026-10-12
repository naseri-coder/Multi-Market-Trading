"""Manual Stage34 runner. Never opens a listening socket or modifies a host.

Requires explicitly designated disposable nonproduction host and explicit ACK.
Writes only canonical, sanitized JSON to stdout. No persistent files.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .designated_host_readonly_probe_stage34_v1 import (
    Stage34Refused, probe_designated_local_host,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-alias", required=True)
    parser.add_argument("--expected-nodename", required=True)
    parser.add_argument("--tls-hostname", required=True)
    parser.add_argument("--certificate-ca-file", required=True)
    parser.add_argument("--certificate-der-sha256", required=True)
    parser.add_argument("--ack-disposable-readonly-probe", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = probe_designated_local_host(
            host_alias=args.host_alias,
            expected_nodename=args.expected_nodename,
            tls_hostname=args.tls_hostname,
            tls_port=443, ca_file=Path(args.certificate_ca_file),
            expected_certificate_sha256=args.certificate_der_sha256,
            operator_ack=args.ack_disposable_readonly_probe)
    except (Stage34Refused, OSError, ValueError):
        print("STAGE34_DESIGNATED_HOST_PROBE_BLOCKED", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(receipt.evidence_json() + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
