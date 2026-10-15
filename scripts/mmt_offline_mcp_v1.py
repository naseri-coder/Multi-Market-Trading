"""Opt-in local stdio MCP research bridge, disabled unless explicitly acknowledged."""
from __future__ import annotations

import argparse
import sys

from naseri_markets.offline_research_mcp_v1 import run_stdio


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ack-offline-research", action="store_true")
    options = parser.parse_args(argv)
    if options.ack_offline_research is not True:
        print("OFFLINE_MCP_DISABLED:EXPLICIT_ACK_REQUIRED", file=sys.stderr)
        return 2
    return run_stdio(sys.stdin.buffer, sys.stdout.buffer, approved=True)


if __name__ == "__main__":
    raise SystemExit(main())
