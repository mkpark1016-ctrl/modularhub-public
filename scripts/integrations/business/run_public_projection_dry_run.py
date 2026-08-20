from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.integrations.business.public_projection import (
    build_public_projection,
    projection_blockers,
    write_public_projection_outputs,
)
from scripts.integrations.business.unified import load_canonical_records


DEFAULT_OUTPUT_DIR = Path("artifacts/public-projection")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Project an accepted unified business artifact into the public contract without publishing it."
    )
    parser.add_argument("--unified-records", type=Path, required=True)
    parser.add_argument("--unified-summary", type=Path, required=True)
    parser.add_argument("--public-business", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    before_hash = _sha256(args.public_business)
    records = load_canonical_records(args.unified_records)
    unified_summary = _load_object(args.unified_summary)
    public_payload = json.loads(args.public_business.read_text(encoding="utf-8"))

    expected_count = unified_summary.get("records_output")
    if expected_count != len(records):
        raise ValueError(
            f"unified artifact count mismatch: summary={expected_count!r} records={len(records)}"
        )

    projected, candidate, report = build_public_projection(
        records,
        public_payload,
        unified_summary=unified_summary,
    )
    after_hash = _sha256(args.public_business)
    report["protected_public_business"] = {
        "sha256_before": before_hash,
        "sha256_after": after_hash,
        "changed": before_hash != after_hash,
    }
    write_public_projection_outputs(projected, candidate, report, args.output_dir)

    blockers = projection_blockers(report)
    if report["protected_public_business"]["changed"]:
        blockers.append("protected_public_business_changed")
    print(
        "Public business projection dry run complete: "
        f"unified_input={report['unified_input_count']} "
        f"publishable={report['publishable_count']} "
        f"filtered={report['filtered_count']} "
        f"net_new={report['net_new_count']} "
        f"candidate_total={report['candidate_public_count']} "
        f"blockers={len(blockers)}"
    )
    return 0 if not blockers else 4


def _load_object(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path.name}")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
