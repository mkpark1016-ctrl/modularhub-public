from __future__ import annotations

import sys
import argparse
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collector_runner import run_collector
from src.collectors import (
    D2BBidCollector,
    D2BPlanCollector,
    G2BCollector,
    LHCollector,
    MockCollector,
    NaverNewsCollector,
)
from src.config import (
    DATA_GO_KR_SERVICE_KEY,
    G2B_BUSINESS_TYPES,
    G2B_MODULAR_LOOKBACK_DAYS,
    G2B_MODULAR_PAGE_SIZE,
    G2B_MODULAR_SCOPE_ENABLED,
    G2B_MODULAR_TITLE_KEYWORD,
    G2B_SERVICE_SUBTYPE,
    NAVER_CLIENT_ID,
    NAVER_CLIENT_SECRET,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run configured collectors.")
    parser.add_argument("--include-mock", action="store_true", help="Include development mock collector.")
    args = parser.parse_args()

    collectors = []
    if args.include_mock:
        collectors.append(MockCollector())
    if DATA_GO_KR_SERVICE_KEY:
        if G2B_MODULAR_SCOPE_ENABLED:
            collectors.append(
                G2BCollector(
                    lookback_days=G2B_MODULAR_LOOKBACK_DAYS,
                    page_size=G2B_MODULAR_PAGE_SIZE,
                    business_types=[value.strip() for value in G2B_BUSINESS_TYPES.split(",") if value.strip()],
                    title_keyword=G2B_MODULAR_TITLE_KEYWORD or "모듈러",
                    operating_scope="modular_goods_service",
                    service_subtype=G2B_SERVICE_SUBTYPE or "일반용역",
                )
            )
        else:
            collectors.append(G2BCollector())
        collectors.append(LHCollector())
        collectors.append(D2BPlanCollector())
        collectors.append(D2BBidCollector())
    else:
        print("DATA_GO_KR_SERVICE_KEY가 없어 공공데이터포털 기반 수집기를 건너뜁니다.")

    if NAVER_CLIENT_ID and NAVER_CLIENT_SECRET:
        collectors.append(NaverNewsCollector())
    else:
        print("NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET이 없어 NaverNewsCollector를 건너뜁니다.")

    exit_code = 0
    for collector in collectors:
        result = run_collector(collector)
        print(
            f"{result.collector_name}: status={result.status}, "
            f"inserted={result.inserted_count}, updated={result.updated_count}, "
            f"skipped={result.skipped_count}"
        )
        if result.error_message:
            print(f"error: {result.error_message}")
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
