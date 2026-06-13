from __future__ import annotations

import sys
import traceback
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collector_runner import run_collector
from src.collectors import G2BProcurementPlanCollector
from src.config import DATA_GO_KR_SERVICE_KEY


def main() -> int:
    if not DATA_GO_KR_SERVICE_KEY:
        print(".env에 DATA_GO_KR_SERVICE_KEY를 설정하세요.")
        return 1
    result = run_collector(G2BProcurementPlanCollector())
    print(
        f"{result.collector_name} procurement plan: status={result.status}, "
        f"inserted={result.inserted_count}, updated={result.updated_count}, skipped={result.skipped_count}"
    )
    if result.error_message:
        print(f"error: {result.error_message}")
        traceback.print_exception(RuntimeError(result.error_message))
        return 1
    if result.inserted_count + result.updated_count + result.skipped_count == 0:
        print("status: 정상 호출, 조회기간 내 모듈러 발주계획 0건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
