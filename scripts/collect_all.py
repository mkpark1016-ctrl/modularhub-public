from __future__ import annotations

import sys
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collector_runner import run_collector
from src.collectors import (
    D2BBidCollector,
    D2BProcurementPlanCollector,
    G2BCollector,
    G2BProcurementPlanCollector,
    GdeltDocNewsCollector,
    LHCollector,
    MockCollector,
    NaverNewsCollector,
    OverseasRssNewsCollector,
)
from src.config import (
    DATA_GO_KR_SERVICE_KEY,
    D2B_LEGACY_API_ENABLED,
    GDELT_DOC_NEWS_ENABLED,
    G2B_BUSINESS_TYPES,
    G2B_MODULAR_LOOKBACK_DAYS,
    G2B_MODULAR_PAGE_SIZE,
    G2B_MODULAR_SCOPE_ENABLED,
    G2B_MODULAR_TITLE_KEYWORD,
    G2B_SERVICE_SUBTYPE,
    NAVER_API_HUB_CLIENT_ID,
    NAVER_API_HUB_CLIENT_SECRET,
    OVERSEAS_RSS_NEWS_ENABLED,
)

DIAGNOSTICS_DIR = Path("artifacts/news_collection_diagnostics")


def safe_collector_stats(collector: object) -> dict[str, Any]:
    stats = getattr(collector, "stats", {}) or {}
    if not isinstance(stats, dict):
        return {}
    blocked = {"raw", "raw_response", "request_headers", "headers", "authorization"}
    return {key: value for key, value in stats.items() if str(key).lower() not in blocked}


def write_news_collection_diagnostics(results: list[dict[str, Any]]) -> None:
    DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)
    source_counts = {
        row["collectorName"]: {
            "status": row["status"],
            "inserted": row["insertedCount"],
            "updated": row["updatedCount"],
            "skipped": row["skippedCount"],
            "returned": row["stats"].get("returned_count"),
            "fetched": row["stats"].get("fetched_item_count") or row["stats"].get("article_count"),
        }
        for row in results
        if row["sourceType"] == "news"
    }
    report = {
        "schemaVersion": "news-collection-diagnostics-v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "collectors": results,
        "sourceCounts": source_counts,
        "gdelt": next((row for row in results if row["collectorName"] == "GDELT 해외뉴스"), None),
        "overseasRss": next((row for row in results if row["collectorName"] == "해외 모듈러 RSS"), None),
    }
    (DIAGNOSTICS_DIR / "news-collection-diagnostics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# News Collection Diagnostics", ""]
    for row in results:
        lines.append(
            f"- `{row['collectorName']}`: status={row['status']}, inserted={row['insertedCount']}, "
            f"updated={row['updatedCount']}, skipped={row['skippedCount']}"
        )
        stats = row.get("stats") or {}
        if row["collectorName"] == "해외 모듈러 RSS":
            lines.append(
                f"  - feeds={stats.get('feed_count')}, success={stats.get('successful_feed_count')}, "
                f"failed={stats.get('failed_feed_count')}, fetched={stats.get('fetched_item_count')}, "
                f"published={stats.get('returned_count')}"
            )
        if row["collectorName"] == "GDELT 해외뉴스":
            lines.append(
                f"  - requests={stats.get('request_count')}, articles={stats.get('article_count')}, "
                f"published={stats.get('returned_count')}, relevance_excluded={stats.get('relevance_excluded_count')}, "
                f"duplicates={stats.get('duplicate_excluded_count')}"
            )
    (DIAGNOSTICS_DIR / "news-collection-diagnostics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


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

    if NAVER_API_HUB_CLIENT_ID and NAVER_API_HUB_CLIENT_SECRET:
        collectors.append(NaverNewsCollector())
    else:
        print("NAVER_API_HUB_CLIENT_ID 또는 NAVER_API_HUB_CLIENT_SECRET이 없어 NaverNewsCollector를 건너뜁니다.")

    if GDELT_DOC_NEWS_ENABLED:
        collectors.append(GdeltDocNewsCollector())
    else:
        print("GDELT_DOC_NEWS_ENABLED=false; skipping GdeltDocNewsCollector.")

    if OVERSEAS_RSS_NEWS_ENABLED:
        collectors.append(OverseasRssNewsCollector())
    else:
        print("OVERSEAS_RSS_NEWS_ENABLED=false; skipping OverseasRssNewsCollector.")

    exit_code = 0
    diagnostics: list[dict[str, Any]] = []
    for collector in collectors:
        result = run_collector(collector)
        diagnostics.append(
            {
                "collectorName": result.collector_name,
                "sourceType": result.source_type,
                "status": result.status,
                "insertedCount": result.inserted_count,
                "updatedCount": result.updated_count,
                "skippedCount": result.skipped_count,
                "safeErrorCategory": "none" if not result.error_message else result.error_message.split(":", 1)[0][:80],
                "stats": safe_collector_stats(collector),
            }
        )
        print(
            f"{result.collector_name}: status={result.status}, "
            f"inserted={result.inserted_count}, updated={result.updated_count}, "
            f"skipped={result.skipped_count}"
        )
        if result.error_message:
            print(f"error: {result.error_message}")
            exit_code = 1

    write_news_collection_diagnostics(diagnostics)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
