from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collector_runner import run_collector
from src.collectors.g2b import G2BCollector
from src.config import (
    G2B_BUSINESS_TYPE,
    G2B_ITEM_LOOKBACK_DAYS,
    G2B_ITEM_PAGE_SIZE,
    G2B_MODULAR_TITLE_KEYWORD,
)


def main() -> int:
    business_type = G2B_BUSINESS_TYPE or "물품"
    collector = G2BCollector(
        lookback_days=G2B_ITEM_LOOKBACK_DAYS,
        page_size=G2B_ITEM_PAGE_SIZE,
        business_types=[business_type],
        title_keyword=G2B_MODULAR_TITLE_KEYWORD or "모듈러",
        debug_keyword=G2B_MODULAR_TITLE_KEYWORD or "모듈러",
    )
    result = run_collector(collector)
    print(
        f"{result.collector_name} modular items: status={result.status}, "
        f"business_type={business_type}, title_keyword={G2B_MODULAR_TITLE_KEYWORD}, "
        f"inserted={result.inserted_count}, updated={result.updated_count}, skipped={result.skipped_count}"
    )
    if result.error_message:
        print(f"error: {result.error_message}")
        traceback.print_exception(RuntimeError(result.error_message))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
