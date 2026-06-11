from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.collectors.base import BaseCollector
from src.config import DB_PATH
from src.database import init_db, insert_collect_log, upsert_item
from src.models import Item
from src.normalizer import normalize_item


@dataclass
class CollectorRunResult:
    collector_name: str
    source_type: str
    status: str
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    error_message: str | None = None


def run_collector(collector: BaseCollector) -> CollectorRunResult:
    init_db(DB_PATH)
    collector_name = collector.get_source_name()
    source_type = collector.get_source_type()
    started_at = datetime.now().isoformat(timespec="seconds")
    inserted_count = 0
    updated_count = 0
    skipped_count = 0

    try:
        raw_items = collector.collect()
        for raw_item in raw_items:
            raw_item.setdefault("source_type", source_type)
            raw_item.setdefault("source_name", collector_name)
            normalized = normalize_item(raw_item)
            item = Item(**normalized)
            status = upsert_item(item, DB_PATH)
            if status == "inserted":
                inserted_count += 1
            elif status == "updated":
                updated_count += 1
            else:
                skipped_count += 1

        finished_at = datetime.now().isoformat(timespec="seconds")
        insert_collect_log(
            collector_name=collector_name,
            source_type=source_type,
            started_at=started_at,
            finished_at=finished_at,
            status="success",
            inserted_count=inserted_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
        )
        return CollectorRunResult(
            collector_name=collector_name,
            source_type=source_type,
            status="success",
            inserted_count=inserted_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
        )
    except Exception as exc:
        finished_at = datetime.now().isoformat(timespec="seconds")
        error_message = str(exc)
        insert_collect_log(
            collector_name=collector_name,
            source_type=source_type,
            started_at=started_at,
            finished_at=finished_at,
            status="failed",
            inserted_count=inserted_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
            error_message=error_message,
        )
        return CollectorRunResult(
            collector_name=collector_name,
            source_type=source_type,
            status="failed",
            inserted_count=inserted_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
            error_message=error_message,
        )
