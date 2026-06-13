from __future__ import annotations

from src.collectors.base import BaseCollector


class D2BGWBidCollector(BaseCollector):
    """Reserved collector for the future D2B GW bid API migration."""

    def get_source_type(self) -> str:
        return "bid"

    def get_source_name(self) -> str:
        return "D2B"

    def collect(self) -> list[dict]:
        raise RuntimeError("D2B GW 입찰공고 API는 아직 공개 수집 파이프라인에 연결되지 않았습니다.")
