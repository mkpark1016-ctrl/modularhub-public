from __future__ import annotations

import pandas as pd

from src.config import DB_PATH, SAMPLE_CSV_PATH
from src.database import init_db, upsert_item
from src.models import Item
from src.utils import generate_unique_hash, parse_optional_date, parse_optional_int


def load_sample_data() -> int:
    init_db(DB_PATH)
    df = pd.read_csv(SAMPLE_CSV_PATH).fillna("")
    count = 0

    for _, row in df.iterrows():
        unique_hash = generate_unique_hash(
            row["source_type"],
            row["source_name"],
            row["title"],
            row["organization"],
            row["posted_at"],
            row["url"],
        )
        item = Item(
            source_type=row["source_type"],
            source_name=row["source_name"],
            title=row["title"],
            organization=row["organization"] or None,
            posted_at=parse_optional_date(row["posted_at"]),
            due_at=parse_optional_date(row["due_at"]),
            amount=parse_optional_int(row["amount"]),
            region=row["region"] or None,
            keywords=row["keywords"] or None,
            summary=row["summary"] or None,
            url=row["url"] or None,
            relevance_score=float(row["relevance_score"] or 0),
            unique_hash=unique_hash,
            is_mock=1,
            data_quality="sample",
            link_type="sample",
            link_status="unchecked",
        )
        upsert_item(item, DB_PATH)
        count += 1

    return count
