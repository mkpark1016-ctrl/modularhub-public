from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import DB_PATH, LH_DEEP_LINK_PROBE_ENABLED
from src.lh_deep_link import build_lh_deep_link_candidates, build_lh_list_url
from src.link_validator import validate_candidate_url


def main() -> None:
    if not LH_DEEP_LINK_PROBE_ENABLED:
        print("LH_DEEP_LINK_PROBE_ENABLED is false. Set it to true to run LH deep-link probes.")
        return

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, title, source_record_id, source_record_no, source_search_url
            FROM items
            WHERE source_name = 'LH'
              AND COALESCE(data_quality, 'real') NOT IN ('mock', 'sample', 'test')
            ORDER BY posted_at DESC, id DESC
            LIMIT 10
            """
        ).fetchall()

    if not rows:
        print("No LH rows found in items. Run collect_lh.py first.")
        return

    for row in rows:
        item = dict(row)
        candidates = build_lh_deep_link_candidates(item)
        print("\n---")
        print(f"id={item['id']} bidNum={item.get('source_record_id') or '-'}")
        print(f"title={item.get('title') or '-'}")
        print(f"list_url_probe_only={build_lh_list_url(item)}")
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
