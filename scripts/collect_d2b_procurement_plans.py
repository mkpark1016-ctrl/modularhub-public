from __future__ import annotations

import sys
import traceback
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collector_runner import run_collector
from src.collectors import D2BProcurementPlanCollector
from src.config import DATA_GO_KR_SERVICE_KEY, D2B_LEGACY_API_ENABLED


def main() -> int:
    if not D2B_LEGACY_API_ENABLED:
        print(
            "WARNING: 방위사업청 기존 군수품조달정보 API가 중지 상태입니다. "
            "D2B 조달계획 수집을 건너뛰며 추후 GW API 전환이 필요합니다."
        )
        return 0
    if not DATA_GO_KR_SERVICE_KEY:
        print(".env에 DATA_GO_KR_SERVICE_KEY를 설정하세요.")
    result = run_collector(D2BProcurementPlanCollector())
    print(
        f"{result.collector_name} procurement plan: status={result.status}, "
        f"inserted={result.inserted_count}, updated={result.updated_count}, skipped={result.skipped_count}"
    )
    if result.error_message:
        print(f"error: {result.error_message}")
        traceback.print_exception(RuntimeError(result.error_message))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
