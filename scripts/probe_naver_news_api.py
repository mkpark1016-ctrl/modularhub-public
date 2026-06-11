from __future__ import annotations

import sys
from pathlib import Path

import requests


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collectors.naver_news import clean_html
from src.config import NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, NAVER_NEWS_ENDPOINT


def mask_key(value: str) -> str:
    if not value:
        return "missing"
    return f"{value[:4]}*** (length={len(value)})"


def main() -> int:
    print(f"NAVER_CLIENT_ID: {mask_key(NAVER_CLIENT_ID)}")
    print(f"NAVER_CLIENT_SECRET: {mask_key(NAVER_CLIENT_SECRET)}")
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("ERROR: .env에 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET을 설정하세요.")
        return 1

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {
        "query": "모듈러 건축",
        "display": 5,
        "start": 1,
        "sort": "date",
    }
    response = requests.get(NAVER_NEWS_ENDPOINT, headers=headers, params=params, timeout=20)
    print(f"HTTP status code: {response.status_code}")
    if response.status_code in (401, 403):
        print("네이버 뉴스 API 인증 오류입니다. Client ID/Secret과 검색 API 사용 설정을 확인하세요.")
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
