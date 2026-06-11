from __future__ import annotations

import sys
import traceback
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collector_runner import run_collector
from src.collectors import NaverNewsCollector
from src.config import NAVER_CLIENT_ID, NAVER_CLIENT_SECRET


def main() -> int:
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print(".env에 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET을 설정하세요.")
    result = run_collector(NaverNewsCollector())
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
