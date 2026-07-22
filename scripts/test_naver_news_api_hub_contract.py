from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collectors.naver_news import (
    DEFAULT_NAVER_API_HUB_NEWS_ENDPOINT,
    NAVER_API_HUB_ID_HEADER,
    NAVER_API_HUB_SECRET_HEADER,
    NaverNewsCollector,
)


class FakeResponse:
    status_code = 200
    text = "{}"

    def json(self) -> dict:
        return {
            "lastBuildDate": "Wed, 22 Jul 2026 10:00:00 +0900",
            "total": 1,
            "start": 1,
            "display": 1,
            "items": [
                {
                    "title": "<b>Modular construction</b> project contract",
                    "originallink": "https://example.com/original",
                    "link": "https://n.news.naver.com/article/001/0000000000",
                    "description": "Factory-built housing uses <b>modular construction</b> units.",
                    "pubDate": "Wed, 22 Jul 2026 10:00:00 +0900",
                }
            ],
        }

    def raise_for_status(self) -> None:
        return None


def main() -> int:
    calls: list[dict] = []

    def fake_get(url: str, *, headers: dict, params: dict, timeout: int) -> FakeResponse:
        parsed = urlparse(url)
        assert parsed.netloc == "naverapihub.apigw.ntruss.com"
        assert parsed.path == "/search/v1/news"
        assert NAVER_API_HUB_ID_HEADER in headers
        assert NAVER_API_HUB_SECRET_HEADER in headers
        assert "X-Naver-Client-Id" not in headers
        assert "X-Naver-Client-Secret" not in headers
        assert "query" in params
        assert params["sort"] == "date"
        assert timeout == 20
        calls.append({"host": parsed.netloc, "path": parsed.path, "sort": params["sort"]})
        return FakeResponse()

    collector = NaverNewsCollector(
        client_id="configured-client-id",
        client_secret="configured-client-secret",
        endpoint=DEFAULT_NAVER_API_HUB_NEWS_ENDPOINT,
        request_get=fake_get,
    )
    items = collector.collect()
    assert calls, "collector must issue at least one API HUB request"
    assert len(items) == 1, "duplicate URLs across queries should be collapsed"
    item = items[0]
    assert item["title"] == "Modular construction project contract"
    assert item["summary"] == "Factory-built housing uses modular construction units."
    assert item["url"] == "https://example.com/original"
    assert item["naver_link"] == "https://n.news.naver.com/article/001/0000000000"
    assert item["published_at" if "published_at" in item else "posted_at"] == "2026-07-22"
    print("NAVER API HUB CONTRACT TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
