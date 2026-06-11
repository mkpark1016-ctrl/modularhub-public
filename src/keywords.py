DEFAULT_KEYWORDS = [
    "모듈러",
    "OSC",
    "공업화주택",
    "프리패브",
    "프리팹",
    "조립식",
    "이동식",
    "이동식 주택",
    "임시",
    "숙소",
    "스마트건설",
    "DfMA",
    "PC 모듈러",
    "스틸 모듈러",
    "군간부숙소",
    "병영생활관",
    "간부숙소",
    "독신자숙소",
    "생활관",
    "막사",
    "관사",
    "기숙사",
    "학교",
    "학교 모듈러",
    "임시교사",
    "시설공사",
    "시설",
    "행복주택",
    "매입임대",
    "공공임대",
    "모듈러교실",
    "임시교사",
    "가설교실",
    "임시교실",
    "이동식교실",
    "모듈러 교실",
    "제작·설치",
    "제작 설치",
    "임차용역",
    "임대용역",
    "임대형",
    "학교 모듈러",
    "교육청 모듈러",
]

KNOWN_BID_TEST_KEYWORDS = [
    "성의여자고등학교",
    "월성초등학교",
]

EXCLUDE_KEYWORDS = [
    "장난감",
    "완구",
    "가구 부품",
    "소형 박스",
    "소형부품",
    "모형",
    "부품상자",
]

IMPORTANT_ORGANIZATION_KEYWORDS = [
    "LH",
    "한국토지주택공사",
    "국방부",
    "교육청",
]

DIRECT_RELEVANCE_KEYWORDS = [
    "모듈러",
    "공업화주택",
    "OSC",
]

D2B_DIRECT_KEYWORDS = [
    "모듈러",
    "공업화주택",
    "OSC",
]

D2B_FACILITY_KEYWORDS = [
    "병영생활관",
    "군간부숙소",
    "간부숙소",
    "숙소",
    "관사",
    "막사",
]

D2B_ACTIVE_STATUS_KEYWORDS = [
    "공고중",
    "공고의뢰중",
    "계약대기중",
]

D2B_DEFENSE_ORGANIZATION_KEYWORDS = [
    "국방시설본부",
    "육군",
    "해군",
    "공군",
    "국방부",
]

NAVER_NEWS_CORE_KEYWORDS = [
    "모듈러 건축",
    "모듈러 주택",
    "OSC 건설",
    "공업화주택",
    "프리패브 건축",
    "프리팹 건축",
    "스마트건설 모듈러",
]

NAVER_NEWS_POLICY_KEYWORDS = [
    "LH 모듈러",
    "GH 모듈러",
    "SH 모듈러",
    "국방부 병영생활관",
    "군간부숙소 모듈러",
    "학교 모듈러",
    "임시교사 모듈러",
    "공공임대 모듈러",
]

NAVER_NEWS_COMPETITOR_KEYWORDS = [
    "유창이앤씨 모듈러",
    "플랜엠 모듈러",
    "금강공업 모듈러",
    "엠쓰리시스템즈 모듈러",
    "희림 모듈러",
    "자이가이스트 모듈러",
    "삼성물산 모듈러",
    "현대건설 모듈러",
    "DL이앤씨 모듈러",
]

NAVER_NEWS_KEYWORD_GROUPS = {
    "핵심 모듈러": NAVER_NEWS_CORE_KEYWORDS,
    "공공·정책": NAVER_NEWS_POLICY_KEYWORDS,
    "경쟁사·시장": NAVER_NEWS_COMPETITOR_KEYWORDS,
}

NAVER_NEWS_EXCLUDE_KEYWORDS = [
    "게임",
    "완구",
    "장난감",
    "자동차 모듈",
    "전자부품 모듈",
    "소프트웨어 모듈",
    "파이썬 모듈",
    "교육 모듈",
]

NAVER_NEWS_PUBLIC_KEYWORDS = [
    "LH",
    "GH",
    "SH",
    "국방부",
    "교육청",
    "병영생활관",
    "군간부숙소",
]
