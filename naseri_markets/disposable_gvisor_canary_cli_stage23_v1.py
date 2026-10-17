"""Opt-in Stage23 canary CLI for a dedicated disposable rootless+runsc host.

DO NOT run on any production, personal, account-bearing or shared server.
This never runs third-party source and cannot grant public plug-in install.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict

from .disposable_gvisor_canary_stage23_v1 import (
    HostCanaryRefused, run_manual_disposable_host_canary,
)
from .secure_plugin_runtime_v1 import SecurePluginPolicy, SecurePluginRefused


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--image", required=True,
                   help="Already-installed, operator-verified OCI image@sha256 digest")
    p.add_argument("--docker-binary", default="/usr/bin/docker")
    p.add_argument("--ack-disposable-host-canary", action="store_true")
    opts = p.parse_args(argv)
    try:
        # Refuse early before constructing any command.
        if (opts.ack_disposable_host_canary is not True
                or os.environ.get("MMT_NONPRODUCTION") != "1"
                or os.environ.get("MMT_DISPOSABLE_SANDBOX_HOST") != "1"
                or "MMT_PRODUCTION" in os.environ
                or os.geteuid() == 0):
            raise HostCanaryRefused("EXPLICIT_DISPOSABLE_NONPRODUCTION_HOST_REQUIRED")
        host = SecurePluginPolicy(
            enabled=True, image=opts.image,
            docker_binary=opts.docker_binary,
            docker_socket=f"unix:///run/user/{os.geteuid()}/docker.sock")
        receipt = run_manual_disposable_host_canary(
            host, operator_ack=True)
    except (HostCanaryRefused, SecurePluginRefused, OSError, ValueError):
        print("STAGE23_DISPOSABLE_CANARY_REFUSED", file=sys.stderr)
        return 2
    print(json.dumps(asdict(receipt), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
