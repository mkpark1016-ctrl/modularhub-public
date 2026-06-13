from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "modular_info.db"
BUSINESS_PATH = ROOT / "frontend" / "public" / "data" / "business.json"
FRONTEND_PATH = ROOT / "frontend" / "src" / "App.jsx"


def contains_modular(row: sqlite3.Row | dict) -> bool:
    text = " ".join(str(row[key] or "") for key in ("title", "summary", "keywords"))
    return "모듈러" in text


def main() -> int:
    db_rows: list[sqlite3.Row] = []
    plan_logs: list[sqlite3.Row] = []
    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            db_rows = conn.execute(
                "SELECT * FROM items WHERE source_type = 'procurement_plan' ORDER BY id DESC"
            ).fetchall()
            plan_logs = conn.execute(
                "SELECT * FROM collect_logs WHERE source_type = 'procurement_plan' ORDER BY id DESC"
            ).fetchall()

    json_payload: dict = {}
    if BUSINESS_PATH.exists():
        loaded = json.loads(BUSINESS_PATH.read_text(encoding="utf-8"))
        json_payload = loaded if isinstance(loaded, dict) else {"items": loaded}
    json_items = json_payload.get("items", [])
    json_plans = [item for item in json_items if item.get("source_type") == "procurement_plan"]
    db_modular = [row for row in db_rows if contains_modular(row)]
    json_modular = [item for item in json_plans if contains_modular(item)]
    db_sources = Counter(str(row["source_name"] or "(missing)") for row in db_rows)
    json_sources = Counter(str(item.get("source") or "(missing)") for item in json_plans)
    frontend = FRONTEND_PATH.read_text(encoding="utf-8") if FRONTEND_PATH.exists() else ""
    frontend_matches = "item.source_type === selectedSourceType" in frontend
    latest_status: dict[str, str] = {}
    for row in plan_logs:
        source_name = str(row["collector_name"] or "")
        latest_status.setdefault(source_name, str(row["status"] or "unknown"))

    print(f"DB procurement_plan: {len(db_rows)}")
    print(f"DB source counts: {dict(db_sources)}")
    print(f"DB modular procurement plans: {len(db_modular)}")
    print(f"business.json procurement_plan: {len(json_plans)}")
    print(f"business.json source counts: {dict(json_sources)}")
    print(f"business.json modular procurement plans: {len(json_modular)}")
    print(f"frontend source_type mapping: {'OK' if frontend_matches else 'MISMATCH'}")
    print(f"procurement plan collect logs: {len(plan_logs)}")
    print(f"latest collector status: {latest_status}")

    expected_sources = {"나라장터", "D2B"}
    missing_sources = sorted(expected_sources - set(latest_status))
    failed_sources = sorted(source for source, status in latest_status.items() if status != "success")
    if missing_sources:
        diagnosis = f"A. 수집기 미실행: {', '.join(missing_sources)}"
    elif failed_sources:
        diagnosis = f"A. 최근 수집 실패: {', '.join(failed_sources)}"
    elif db_modular and not json_plans:
        diagnosis = "B. 수집은 되었으나 export 누락"
    elif json_plans and not frontend_matches:
        diagnosis = "C. export는 되었으나 프론트 필터 오류"
    elif not db_modular and plan_logs and str(plan_logs[0]["status"]) == "success":
        diagnosis = "D. 실제 조회기간 내 0건"
    elif not db_modular and plan_logs:
        diagnosis = "A. 발주계획 수집 실행 기록은 있으나 최근 실행이 실패했거나 저장되지 않음"
    else:
        diagnosis = "OK. 수집·export·프론트 필터가 연결됨"

    print(f"diagnosis: {diagnosis}")
    if plan_logs:
        latest = plan_logs[0]
        print(
            "latest plan log: "
            f"collector={latest['collector_name']} status={latest['status']} "
            f"finished_at={latest['finished_at']} error={latest['error_message'] or '-'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
