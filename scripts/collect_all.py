from __future__ import annotations

import sys
import argparse
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collector_runner import run_collector
from src.collectors import (
    D2BBidCollector,
    D2BProcurementPlanCollector,
    G2BCollector,
    G2BProcurementPlanCollector,
    LHCollector,
    MockCollector,
    NaverNewsCollector,
)
from src.config import (
    DATA_GO_KR_SERVICE_KEY,
    D2B_LEGACY_API_ENABLED,
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
    parser.add_argument(
        "--skip-procurement-plans",
        action="store_true",
        help="Skip G2B and D2B procurement plans when they are run as separate workflow steps.",
    )
    parser.add_argument("--skip-lh", action="store_true", help="Skip LH for the public G2B/D2B data workflow.")
    parser.add_argument("--skip-d2b", action="store_true", help="Skip stopped legacy D2B APIs.")
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
        if not args.skip_procurement_plans:
            collectors.append(G2BProcurementPlanCollector())
        if D2B_LEGACY_API_ENABLED and not args.skip_d2b:
            collectors.append(D2BBidCollector())
            if not args.skip_procurement_plans:
                collectors.append(D2BProcurementPlanCollector())
        else:
            print(
                "WARNING: 방위사업청 기존 군수품조달정보 API가 중지 상태입니다. "
                "D2B 수집을 건너뛰며 추후 GW API 전환이 필요합니다."
            )
        if not args.skip_lh:
            collectors.append(LHCollector())
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
