from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "frontend" / "public" / "data"
FILES = {name: DATA_DIR / f"{name}.json" for name in ("business", "news", "meta")}
BANNED_TEXT = (
    "servicekey",
    "data_go_kr_service_key",
    "naver_client_secret",
    "naver_client_id",
    "rnd_announce",
    "rnd_outcome",
    '"source_type": "patent"',
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    for name, path in FILES.items():
        require(path.exists(), f"missing {name}.json")

    combined = "\n".join(path.read_text(encoding="utf-8") for path in FILES.values()).lower()
    for token in BANNED_TEXT:
        require(token.lower() not in combined, f"public JSON contains banned token: {token}")

    business = json.loads(FILES["business"].read_text(encoding="utf-8"))
    news = json.loads(FILES["news"].read_text(encoding="utf-8"))
    meta = json.loads(FILES["meta"].read_text(encoding="utf-8"))
    require(isinstance(business.get("items"), list), "business items must be a list")
    require(isinstance(news.get("items"), list), "news items must be a list")
    require(bool(business["items"]), "business items must not be empty")
    require(bool(news["items"]), "news items must not be empty")
    require(meta.get("business_count") == len(business["items"]), "business count mismatch")
    require(meta.get("news_count") == len(news["items"]), "news count mismatch")
    for field in (
        "g2b_order_plan_status",
        "g2b_order_plan_message",
        "d2b_status",
        "d2b_message",
        "workflow_last_run_status",
        "warnings",
        "previous_business_count",
        "current_business_count",
        "merged_business_count",
        "previous_news_count",
        "current_news_count",
        "merged_news_count",
        "public_data_guard_status",
        "public_data_guard_message",
        "d2b_legacy_status",
        "d2b_gw_migration_required",
        "lh_contest_status",
        "lh_contest_message",
        "lh_contest_public_count",
        "lh_contest_exact_link_count",
        "data_policy",
    ):
        require(field in meta, f"meta status field is missing: {field}")
    require(isinstance(meta.get("warnings"), list), "meta warnings must be a list")
    require(meta.get("data_policy") == "cumulative_verified", "unexpected public data policy")
    require(meta.get("merged_business_count") == len(business["items"]), "merged business count mismatch")
    require(meta.get("merged_news_count") == len(news["items"]), "merged news count mismatch")
    require(meta.get("public_data_guard_status") in {"passed", "warning", "override"}, "public data guard did not pass")

    for item in business["items"]:
        require(item.get("title"), "business item title is missing")
        require(item.get("source"), "business item source is missing")
        require(item.get("source_name") == item.get("source"), "business source/source_name mismatch")
        require(isinstance(item.get("manual_check"), dict), "business manual_check is missing")
        require(
            item["source_type"] in {"bid", "procurement_plan", "public_agency_contest"},
            "unexpected business source_type",
        )
        require(item.get("type") in {"입찰공고", "발주계획", "민간사업자 공모"}, "business type label is missing")
        if item["source_type"] == "procurement_plan":
            require(item.get("type") == "발주계획", "procurement plan label mismatch")
            require("plan_no" in item, "procurement plan number field is missing")
        if item["source_type"] == "public_agency_contest":
            require(item.get("type") == "민간사업자 공모", "public contest label mismatch")
            require(item.get("source") == "LH", "10.8-B only exports LH public agency contests")
            require(item.get("source_record_id") or item.get("bid_no"), "LH contest source record id is missing")
    for item in news["items"]:
        require(item.get("original_url"), "news original_url is missing")
        require(item.get("source_type") is None, "news contract must not expose unrelated source_type")

    print(f"business items: {len(business['items'])}")
    print(f"news items: {len(news['items'])}")
    print("PUBLIC JSON EXPORT TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
