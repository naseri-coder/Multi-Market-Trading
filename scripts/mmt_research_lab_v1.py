"""Stage-11 OFFLINE Stage-9 research CLI: stdout only, no source writes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from naseri_markets.strategy_research_lab_v1 import (
    MAX_MANIFEST,
    ResearchLabRefused,
    evaluate_stage9_research,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, help='Existing offline Stage-9 SQLite database')
    parser.add_argument('--protocol', required=True, help='Frozen study manifest JSON file')
    parser.add_argument('--ack-offline-research', action='store_true')
    parser.add_argument('--wf-folds', type=int, default=None,
                        help='Opt-in expanding validation folds (2-12)')
    parser.add_argument('--wf-embargo-seconds', type=int, default=0,
                        help='Label embargo before each fold (requires --wf-folds)')
    args = parser.parse_args(argv)
    if not args.ack_offline_research:
        print('RESEARCH_REFUSED:EXPLICIT_OFFLINE_ACK_REQUIRED', file=sys.stderr)
        return 2
    try:
        protocol_file = Path(args.protocol)
        if protocol_file.is_symlink() or not protocol_file.is_file():
            raise ResearchLabRefused('REGULAR_STUDY_PROTOCOL_REQUIRED')
        with protocol_file.open('rb') as stream:
            blob = stream.read(MAX_MANIFEST + 1)
        result = evaluate_stage9_research(
            args.db, blob, walk_forward_folds=args.wf_folds,
            embargo_seconds=args.wf_embargo_seconds,
        )
    except (OSError, ValueError, ResearchLabRefused):
        print('RESEARCH_REFUSED:FAIL_CLOSED', file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
