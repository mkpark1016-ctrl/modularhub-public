from __future__ import annotations

import sys
from pathlib import Path

import requests


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collectors.naver_news import clean_html  # noqa: E402
from src.config import (  # noqa: E402
    NAVER_API_HUB_CLIENT_ID,
    NAVER_API_HUB_CLIENT_SECRET,
    NAVER_API_HUB_NEWS_ENDPOINT,
)


def main() -> int:
    print(f"NAVER_API_HUB_CLIENT_ID configured: {bool(NAVER_API_HUB_CLIENT_ID)}")
    print(f"NAVER_API_HUB_CLIENT_SECRET configured: {bool(NAVER_API_HUB_CLIENT_SECRET)}")
    if not NAVER_API_HUB_CLIENT_ID or not NAVER_API_HUB_CLIENT_SECRET:
        print("ERROR: configure NAVER_API_HUB_CLIENT_ID and NAVER_API_HUB_CLIENT_SECRET.")
        return 1

    headers = {
        "X-NCP-APIGW-API-KEY-ID": NAVER_API_HUB_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": NAVER_API_HUB_CLIENT_SECRET,
    }
    params = {
        "query": "모듈러 건축",
        "display": 5,
        "start": 1,
        "sort": "date",
    }
    response = requests.get(NAVER_API_HUB_NEWS_ENDPOINT, headers=headers, params=params, timeout=20)
    print(f"HTTP status code: {response.status_code}")
    if response.status_code in (401, 403):
        print("NAVER API HUB authentication or subscription status requires attention.")
        return 1
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items", [])
    print(f"item count: {len(items)}")
    if items:
        first = items[0]
        print(f"first title: {clean_html(first.get('title'))}")
        print(f"first pubDate: {first.get('pubDate')}")
        print(f"first link: {first.get('originallink') or first.get('link')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
