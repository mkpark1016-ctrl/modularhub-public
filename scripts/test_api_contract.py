from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api_contract import get_api_manifest, get_bids, get_health, get_trends


def main() -> int:
    manifest = get_api_manifest()
    health = get_health()
    bids = get_bids(limit=5)
    trends = get_trends()

    assert "GET /api/health" in manifest["endpoints"]
    assert health["server"] == "online"
    assert "database" in health
    assert isinstance(bids, list)
    if bids:
        required = {"id", "source_type", "source_name", "title", "manual_check_site"}
        missing = required - set(bids[0])
        assert not missing, f"missing fields: {missing}"
    assert "total_items" in trends
    print("API CONTRACT TEST PASSED")
    print(f"health={health}")
    print(f"sample_bids={len(bids)} trends_total={trends['total_items']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
