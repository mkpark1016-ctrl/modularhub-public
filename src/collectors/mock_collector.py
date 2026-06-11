from __future__ import annotations

from src.collectors.base import BaseCollector


class MockCollector(BaseCollector):
    def get_source_type(self) -> str:
        return "mock"

    def get_source_name(self) -> str:
        return "mock_collector"

    def collect(self) -> list[dict]:
        items = [
            {
                "source_type": "입찰/조달",
                "source_name": "나라장터 입찰공고",
                "title": "서울 모듈러 교실 임대형 설치 공사",
                "organization": "서울특별시교육청",
                "posted_at": "2026-05-16",
                "due_at": "2026-05-25",
                "amount": 1850000000,
                "region": "서울",
                "keywords": "모듈러;학교;임대형;교실",
                "summary": "노후 교실 대체를 위한 모듈러 교실 제작·운송·설치 입찰 공고입니다.",
                "url": "https://www.g2b.go.kr/",
                "relevance_score": 95,
            },
            {
                "source_type": "입찰/조달",
                "source_name": "LH 입찰공고",
                "title": "LH 공업화주택 모듈러 실증사업 감리 용역",
                "organization": "한국토지주택공사",
                "posted_at": "2026-05-18",
                "due_at": "2026-06-03",
                "amount": 580000000,
                "region": "세종",
                "keywords": ["LH", "공업화주택", "모듈러", "감리"],
                "summary": "공업화주택 모듈러 실증사업의 품질관리와 감리 용역 mock 데이터입니다.",
                "url": "https://www.lh.or.kr/mock-modular-supervision",
            },
            {
                "source_type": "입찰/조달",
                "source_name": "D2B 조달계획",
                "title": "병영생활관 스틸 모듈러 시설 조달계획",
                "organization": "국방부",
                "posted_at": "2026-05-18",
                "due_at": "2026-06-10",
                "amount": 1450000000,
                "region": "경기",
                "keywords": ["D2B", "병영생활관", "스틸 모듈러"],
                "summary": "군 병영생활관 개선을 위한 스틸 모듈러 시설 조달계획 mock 데이터입니다.",
                "url": "https://www.d2b.go.kr/mock-steel-modular",
            },
            {
                "source_type": "뉴스",
                "source_name": "건설경제",
                "title": "모듈러·OSC 기반 학교 시설 시장 확대",
                "organization": "건설경제신문",
                "posted_at": "2026-05-18",
                "due_at": "",
                "amount": "",
                "region": "전국",
                "keywords": ["모듈러", "OSC", "학교 모듈러"],
                "summary": "학교 시설 개선 사업에서 모듈러와 OSC 적용이 확대되고 있다는 mock 뉴스입니다.",
                "url": "https://www.cnews.co.kr/mock-school-modular",
            },
            {
                "source_type": "R&D/특허",
                "source_name": "특허",
                "title": "PC 모듈러 유닛의 내화 접합 구조",
                "organization": "특허정보검색서비스",
                "posted_at": "2026-05-18",
                "due_at": "",
                "amount": "",
                "region": "전국",
                "keywords": ["특허", "PC 모듈러", "접합"],
                "summary": "PC 모듈러 유닛 접합부의 내화 성능 개선 특허 mock 데이터입니다.",
                "url": "https://www.kipris.or.kr/mock-pc-modular",
            },
        ]
        for item in items:
            item["is_mock"] = 1
            item["data_quality"] = "mock"
            item["link_type"] = "mock"
            item["link_status"] = "unchecked"
        return items
