from __future__ import annotations

import math
import sys
from datetime import datetime, timedelta
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collectors.g2b import G2BCollector
from src.config import G2B_MODULAR_LOOKBACK_DAYS, G2B_MODULAR_TITLE_KEYWORD
from src.text_utils import contains_modular_keyword


def _sample_titles(items: list[dict], limit: int = 5) -> list[str]:
    titles = []
    for item in items[:limit]:
        titles.append(str(item.get("bidNtceNm") or item.get("ntceNm") or item.get("bidNtceName") or "-"))
    return titles


def _probe_endpoint(collector: G2BCollector, label: str, endpoint: str, server_side: bool) -> None:
    keyword = G2B_MODULAR_TITLE_KEYWORD or "모듈러"
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=min(G2B_MODULAR_LOOKBACK_DAYS, 30))
    begin = start_dt.strftime("%Y%m%d") + "0000"
    end = end_dt.strftime("%Y%m%d") + "2359"
    extra = {"bidNtceNm": keyword} if server_side else None
    mode = "server-side title keyword" if server_side else "fallback client-side filter"
    print(f"\n[{label}] {mode}")
    try:
        payload = collector._request(endpoint, 1, begin, end, extra_params=extra)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return

    body = payload.get("response", {}).get("body", {})
    total_count = int(body.get("totalCount") or 0)
    total_pages = max(1, math.ceil(total_count / max(collector.page_size, 1)))
    items = collector._extract_items(body)
    matched = [item for item in items if contains_modular_keyword(item.get("bidNtceNm") or item.get("ntceNm"))]
    print(f"totalCount={total_count}, pageCount={total_pages}, itemCount={len(items)}, modularTitleCount={len(matched)}")
    titles = _sample_titles(matched if not server_side else items)
    if titles:
        print("first titles:")
        for title in titles:
            print(f"- {title}")
    else:
        print("first titles: none")


def main() -> int:
    collector = G2BCollector(
        lookback_days=min(G2B_MODULAR_LOOKBACK_DAYS, 30),
        business_types=["물품", "용역"],
        title_keyword=G2B_MODULAR_TITLE_KEYWORD or "모듈러",
    )
    print("G2B modular scope probe: DATA_GO_KR_SERVICE_KEY is loaded but never printed")
    for label, endpoint in (("물품", collector.goods_endpoint), ("용역", collector.service_endpoint)):
        _probe_endpoint(collector, label, endpoint, server_side=True)
        _probe_endpoint(collector, label, endpoint, server_side=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
