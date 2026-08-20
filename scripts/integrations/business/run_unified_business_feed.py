from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.integrations.business.unified import (
    build_unified_business_feed,
    load_canonical_records,
    write_unified_staging_outputs,
)


DEFAULT_OUTPUT_DIR = Path("artifacts/unified-business")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Combine existing LH/G2B fallback and D2B canonical artifacts into an offline staging feed."
    )
    parser.add_argument("--lh-records", type=Path, required=True, help="LH pilot canonical record artifact (includes any G2B fallback records).")
    parser.add_argument("--d2b-records", type=Path, required=True, help="D2B pilot canonical record artifact.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = [*load_canonical_records(args.lh_records), *load_canonical_records(args.d2b_records)]
    unified_records, summary = build_unified_business_feed(records)
    write_unified_staging_outputs(unified_records, summary, args.output_dir)
    print(
        "Unified business feed staging complete: "
        f"records_input={summary['records_input']} "
        f"records_output={summary['records_output']} "
        f"exact_duplicates_removed={summary['exact_duplicates_removed']} "
        f"identity_conflicts={summary['identity_conflict_count']} "
        f"cross_source_candidates={summary['cross_source_candidate_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
