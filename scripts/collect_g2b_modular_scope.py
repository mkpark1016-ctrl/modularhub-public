from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collector_runner import run_collector
from src.collectors.g2b import G2BCollector
from src.config import (
    G2B_BUSINESS_TYPES,
    G2B_MODULAR_LOOKBACK_DAYS,
    G2B_MODULAR_PAGE_SIZE,
    G2B_MODULAR_TITLE_KEYWORD,
    G2B_SERVICE_SUBTYPE,
)


def _business_types() -> list[str]:
    values = [value.strip() for value in (G2B_BUSINESS_TYPES or "물품,용역").split(",")]
    return [value for value in values if value]


def main() -> int:
    collector = G2BCollector(
        lookback_days=G2B_MODULAR_LOOKBACK_DAYS,
        page_size=G2B_MODULAR_PAGE_SIZE,
        business_types=_business_types(),
        title_keyword=G2B_MODULAR_TITLE_KEYWORD or "모듈러",
        operating_scope="modular_goods_service",
        service_subtype=G2B_SERVICE_SUBTYPE or "일반용역",
    )
    result = run_collector(collector)
    print(
        f"{result.collector_name} modular scope: status={result.status}, "
        f"inserted={result.inserted_count}, updated={result.updated_count}, skipped={result.skipped_count}"
    )
    if result.error_message:
        print(f"error={result.error_message}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
