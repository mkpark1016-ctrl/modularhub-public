from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.integrations.business.public_pipeline import (
    integrate_optional_unified_business,
    write_public_pipeline_integration_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exercise the opt-in unified public integration without writing production public JSON."
    )
    parser.add_argument("--unified-records", type=Path, required=True)
    parser.add_argument("--unified-summary", type=Path, required=True)
    parser.add_argument("--public-business", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/public-pipeline-integration"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    before_hash = _sha256(args.public_business)
    public_payload = json.loads(args.public_business.read_text(encoding="utf-8"))
    existing_items = public_payload.get("items", []) if isinstance(public_payload, dict) else []
    merged_items, report = integrate_optional_unified_business(
        existing_items,
        unified_records_path=args.unified_records,
        unified_summary_path=args.unified_summary,
    )
    after_hash = _sha256(args.public_business)
    report["protected_public_business"] = {
        "sha256_before": before_hash,
        "sha256_after": after_hash,
        "changed": before_hash != after_hash,
    }
    if report["protected_public_business"]["changed"]:
        raise RuntimeError("PROTECTED_PUBLIC_BUSINESS_CHANGED")

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_payload = deepcopy(public_payload) if isinstance(public_payload, dict) else {}
    candidate_payload["items"] = merged_items
    candidate_payload["business_total"] = len(merged_items)
    candidate_payload["merged_business_count"] = len(merged_items)
    (output_dir / "candidate_business.json").write_text(
        json.dumps(candidate_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_public_pipeline_integration_report(
        report,
        output_dir / "public_pipeline_integration_report.json",
    )
    print(
        "Public pipeline integration staging complete: "
        f"baseline={report['baseline_public_count']} "
        f"unified_input={report['unified_input_count']} "
        f"publishable={report['publishable_count']} "
        f"net_new={report['net_new_count']} "
        f"candidate={report['candidate_public_count']}"
    )
    return 0


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
