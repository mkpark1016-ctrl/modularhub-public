from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import D2B_DEEP_LINK_PROBE_ENABLED, DB_PATH
from src.d2b_deep_link import build_d2b_deep_link_candidates
from src.link_validator import validate_candidate_url


def _load_rows(source_type: str, limit: int) -> list[sqlite3.Row]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT *
            FROM items
            WHERE source_name = 'D2B'
              AND source_type = ?
              AND COALESCE(data_quality, 'real') NOT IN ('mock', 'sample', 'test')
            ORDER BY posted_at DESC, id DESC
            LIMIT ?
            """,
            (source_type, limit),
        ).fetchall()


def main() -> None:
    if not D2B_DEEP_LINK_PROBE_ENABLED:
        print("D2B_DEEP_LINK_PROBE_ENABLED is false. Set it to true to run D2B probes.")
        return

    rows = list(_load_rows("procurement_plan", 5)) + list(_load_rows("bid", 5))
    if not rows:
        print("No D2B rows found in items. Run D2B collectors first.")
        return

    for row in rows:
        item = dict(row)
        candidates = build_d2b_deep_link_candidates(item)
        print("\n---")
        print(
            f"id={item['id']} type={item.get('source_type')} "
            f"record={item.get('source_record_id') or '-'} no={item.get('source_record_no') or '-'}"
        )
        print(f"title={item.get('title') or '-'}")
        if not candidates:
            print("candidate_count=0")
            continue

        for idx, candidate in enumerate(candidates, start=1):
            result = validate_candidate_url(
                candidate,
                title=item.get("title"),
                source_record_id=item.get("source_record_id"),
                timeout=10,
            )
            print(
                f"[{idx}] status={result['status_code']} valid={result['is_valid']} "
                f"reason={result['reason']} url={candidate}"
            )


if __name__ == "__main__":
    main()
