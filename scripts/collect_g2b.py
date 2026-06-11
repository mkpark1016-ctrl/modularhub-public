from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collector_runner import run_collector
from src.collectors import G2BCollector


def print_debug_samples(collector: G2BCollector, limit: int = 10) -> None:
    start_dt = datetime.now() - timedelta(days=collector.lookback_days)
    end_dt = datetime.now()
    begin = start_dt.strftime("%Y%m%d") + "0000"
    end = end_dt.strftime("%Y%m%d") + "2359"
    printed = 0

    for category, endpoint in (
        ("construction", collector.construction_endpoint),
        ("service", collector.service_endpoint),
        ("goods", collector.goods_endpoint),
    ):
        if printed >= limit:
            break
        payload = collector._request(endpoint, 1, begin, end)  # debug-only structural probe
        body = payload.get("response", {}).get("body", {})
        items = collector._extract_items(body)
        print(f"\n[{category}] totalCount={body.get('totalCount')} sample_count={len(items[:limit])}")
        for item in items[: max(0, limit - printed)]:
            print(
                {
                    "bidNtceNo": item.get("bidNtceNo"),
                    "bidNtceOrd": item.get("bidNtceOrd"),
                    "bidNtceNm": item.get("bidNtceNm"),
                    "ntceInsttNm": item.get("ntceInsttNm"),
                    "dminsttNm": item.get("dminsttNm"),
                    "bidNtceDt": item.get("bidNtceDt"),
                    "bidClseDt": item.get("bidClseDt"),
                }
            )
            printed += 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect G2B notices.")
    parser.add_argument("--debug-no-keyword-filter", action="store_true")
    parser.add_argument("--debug-limit", type=int, default=10)
    parser.add_argument("--lookback-days", type=int)
    parser.add_argument("--include-cancelled", action="store_true", help="취소/정정공고도 수집 단계에서 제외하지 않습니다.")
    parser.add_argument("--debug-keyword")
    parser.add_argument("--debug-bid-no")
    parser.add_argument("--save-raw-debug", action="store_true")
    args = parser.parse_args()

    collector = G2BCollector(
        lookback_days=args.lookback_days,
        debug_keyword=args.debug_keyword,
        debug_bid_no=args.debug_bid_no,
        save_raw_debug=args.save_raw_debug,
    )
    if args.debug_no_keyword_filter:
        print_debug_samples(collector, args.debug_limit)
        return 0

    result = run_collector(collector)
    print(
        f"{result.collector_name}: status={result.status}, "
        f"inserted={result.inserted_count}, updated={result.updated_count}, "
        f"skipped={result.skipped_count}"
    )
    if result.error_message:
        print(f"error: {result.error_message}")
        traceback.print_exception(RuntimeError(result.error_message))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
