"""Manual Stage38 read-only self-process kernel posture probe.

Only on a separately authorized disposable, credential-free, non-root host.
Emits sanitized JSON stdout; does not create files, listeners or processes.
"""
from __future__ import annotations

import argparse
import sys

from .passive_kernel_posture_stage38_v1 import (
    Stage38Refused, observe_authorized_process_kernel_posture,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-alias", required=True)
    parser.add_argument("--expected-nodename", required=True)
    parser.add_argument("--expected-gid", type=int, required=True)
    parser.add_argument("--ack-disposable-readonly-process-probe",
                        action="store_true")
    args = parser.parse_args(argv)
    try:
        result = observe_authorized_process_kernel_posture(
            host_alias=args.host_alias,
            expected_nodename=args.expected_nodename,
            expected_gid=args.expected_gid,
            operator_ack=args.ack_disposable_readonly_process_probe,
        )
    except (Stage38Refused, ValueError, OSError):
        print("STAGE38_PASSIVE_PROCESS_PROBE_BLOCKED", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(result.sanitized_json() + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
