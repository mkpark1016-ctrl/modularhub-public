from __future__ import annotations

from pathlib import Path

from src.collectors.public_housing_contests.agency import AgencyCollectStats, collect_agency_public_housing_contests
from src.config import DB_PATH


SOURCE_CODE = "GH_CONTEST"


def collect_gh_public_housing_contests(
    *,
    dry_run: bool = True,
    max_pages: int | None = None,
    lookback_days: int | None = None,
    limit: int | None = None,
    known_record_only: bool = False,
    db_path: Path = DB_PATH,
) -> AgencyCollectStats:
    return collect_agency_public_housing_contests(
        SOURCE_CODE,
        dry_run=dry_run,
        max_pages=max_pages,
        lookback_days=lookback_days,
        limit=limit,
        known_record_only=known_record_only,
        db_path=db_path,
    )
