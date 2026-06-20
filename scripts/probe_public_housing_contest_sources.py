from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.collectors.public_housing_contests.base import load_sources, summarize_probe
from src.collectors.public_housing_contests.gh_probe import probe_gh
from src.collectors.public_housing_contests.ih_probe import probe_ih
from src.collectors.public_housing_contests.lh_probe import probe_lh
from src.collectors.public_housing_contests.sh_probe import probe_sh


PROBERS = {
    "LH_CONTEST": probe_lh,
    "GH_CONTEST": probe_gh,
    "IH_NOTICE": probe_ih,
    "SH_CONTEST": probe_sh,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe public housing contest source pages.")
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--source", default="", help="Optional source_code filter.")
    args = parser.parse_args()

    results = []
    for source in load_sources():
        if args.source and source["source_code"] != args.source:
            continue
        prober = PROBERS.get(source["source_code"])
        if not prober:
            continue
        print(f"[probe] {source['source_code']} {source['list_url']}")
        try:
            result = prober(source, max_pages=max(1, min(args.max_pages, 3)))
        except Exception as exc:  # noqa: BLE001 - probe must isolate source failures.
            result = {
                "source_code": source["source_code"],
                "source_name": source["source_name"],
                "list_url": source["list_url"],
                "list_status": None,
                "parser_mode_recommended": "manual_only",
                "list_item_count": 0,
                "pagination_detected": {"detected": False},
                "search_supported": {"supported": False},
                "rss_supported": False,
                "detail_link_detected": False,
                "attachment_detected": False,
                "known_record_status": {"success_count": 0, "attempts": []},
                "failure_reason": f"probe_exception: {type(exc).__name__}",
                "recommended_next_action": str(exc),
            }
        results.append(result)
        known = result.get("known_record_status") or {}
        print(
            f"  status={result.get('list_status')} items={result.get('list_item_count')} "
            f"known_success={known.get('success_count', 0)} parser={result.get('parser_mode_recommended')}"
        )

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    (logs_dir / "public_housing_contest_probe.json").write_text(
        json.dumps({"results": results}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (logs_dir / "public_housing_contest_probe.md").write_text(summarize_probe(results) + "\n", encoding="utf-8")
    print("wrote logs/public_housing_contest_probe.json")
    print("wrote logs/public_housing_contest_probe.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
