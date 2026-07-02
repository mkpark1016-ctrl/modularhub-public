from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "modular_info.db"
SAMPLE_CSV_PATH = DATA_DIR / "sample_items.csv"


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int, *, min_value: int | None = None, max_value: int | None = None) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        value = default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def _env_float(name: str, default: float, *, min_value: float | None = None, max_value: float | None = None) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        value = default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def _env_feed_list(name: str, default: list[dict[str, str]]) -> list[dict[str, str]]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    feeds: list[dict[str, str]] = []
    for part in raw.split(";"):
        text = part.strip()
        if not text:
            continue
        if "|" in text:
            feed_name, feed_url = [value.strip() for value in text.split("|", 1)]
        else:
            feed_url = text
            feed_name = text
        if feed_name and feed_url:
            feeds.append({"name": feed_name, "url": feed_url})
    return feeds or default


GOOGLE_NEWS_MODULAR_QUERY = (
    '"modular construction" OR "modular housing" OR "volumetric modular" '
    'OR "offsite construction" OR "prefabricated building" when:7d'
)
DEFAULT_OVERSEAS_RSS_NEWS_FEEDS = [
    {"name": "Construction Dive News", "url": "https://www.constructiondive.com/feeds/news/"},
    {"name": "Construction Enquirer", "url": "https://www.constructionenquirer.com/feed/"},
    {"name": "The Construction Index", "url": "https://www.theconstructionindex.co.uk/feeds/news.xml"},
    {
        "name": "Google News modular construction",
        "url": (
            "https://news.google.com/rss/search?q="
            f"{quote_plus(GOOGLE_NEWS_MODULAR_QUERY)}&hl=en-US&gl=US&ceid=US:en"
        ),
    },
]

DATA_GO_KR_SERVICE_KEY = os.getenv("DATA_GO_KR_SERVICE_KEY", "")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
NAVER_NEWS_LOOKBACK_DAYS = int(os.getenv("NAVER_NEWS_LOOKBACK_DAYS", "14"))
NAVER_NEWS_DISPLAY = int(os.getenv("NAVER_NEWS_DISPLAY", "50"))
NAVER_NEWS_SORT = os.getenv("NAVER_NEWS_SORT", "date")
NAVER_NEWS_ENDPOINT = os.getenv(
    "NAVER_NEWS_ENDPOINT",
    "https://openapi.naver.com/v1/search/news.json",
)
GDELT_DOC_NEWS_ENABLED = _env_bool("GDELT_DOC_NEWS_ENABLED", False)
GDELT_DOC_NEWS_ENDPOINT = os.getenv(
    "GDELT_DOC_NEWS_ENDPOINT",
    "https://api.gdeltproject.org/api/v2/doc/doc",
)
GDELT_DOC_NEWS_TIMESPAN = os.getenv("GDELT_DOC_NEWS_TIMESPAN", "7d")
GDELT_DOC_NEWS_MAX_RECORDS = _env_int("GDELT_DOC_NEWS_MAX_RECORDS", 250, min_value=1, max_value=250)
GDELT_DOC_NEWS_TIMEOUT_SECONDS = _env_float("GDELT_DOC_NEWS_TIMEOUT_SECONDS", 30.0, min_value=1.0)
GDELT_DOC_NEWS_MIN_RELEVANCE_SCORE = _env_float(
    "GDELT_DOC_NEWS_MIN_RELEVANCE_SCORE",
    70.0,
    min_value=0.0,
    max_value=100.0,
)
GDELT_DOC_NEWS_LANGUAGE = os.getenv("GDELT_DOC_NEWS_LANGUAGE", "English")
OVERSEAS_RSS_NEWS_ENABLED = _env_bool("OVERSEAS_RSS_NEWS_ENABLED", True)
OVERSEAS_RSS_NEWS_TIMEOUT_SECONDS = _env_float("OVERSEAS_RSS_NEWS_TIMEOUT_SECONDS", 20.0, min_value=1.0)
OVERSEAS_RSS_NEWS_LOOKBACK_DAYS = _env_int("OVERSEAS_RSS_NEWS_LOOKBACK_DAYS", 14, min_value=1)
OVERSEAS_RSS_NEWS_MAX_ITEMS_PER_FEED = _env_int("OVERSEAS_RSS_NEWS_MAX_ITEMS_PER_FEED", 100, min_value=1)
OVERSEAS_RSS_NEWS_MIN_RELEVANCE_SCORE = _env_float(
    "OVERSEAS_RSS_NEWS_MIN_RELEVANCE_SCORE",
    70.0,
    min_value=0.0,
    max_value=100.0,
)
OVERSEAS_RSS_NEWS_FEEDS = _env_feed_list("OVERSEAS_RSS_NEWS_FEEDS", DEFAULT_OVERSEAS_RSS_NEWS_FEEDS)
KIPRIS_API_KEY = os.getenv("KIPRIS_API_KEY", "")
NTIS_API_KEY = os.getenv("NTIS_API_KEY", "")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")
G2B_LOOKBACK_DAYS = int(os.getenv("G2B_LOOKBACK_DAYS", "90"))
G2B_PAGE_SIZE = int(os.getenv("G2B_PAGE_SIZE", "100"))
G2B_CONSTRUCTION_ENDPOINT = os.getenv("G2B_CONSTRUCTION_ENDPOINT", "")
G2B_SERVICE_ENDPOINT = os.getenv("G2B_SERVICE_ENDPOINT", "")
G2B_GOODS_ENDPOINT = os.getenv("G2B_GOODS_ENDPOINT", "")
G2B_MODULAR_ITEM_ONLY = os.getenv("G2B_MODULAR_ITEM_ONLY", "true").lower() in {"1", "true", "yes", "y"}
G2B_MODULAR_TITLE_KEYWORD = os.getenv("G2B_MODULAR_TITLE_KEYWORD", "모듈러")
G2B_BUSINESS_TYPE = os.getenv("G2B_BUSINESS_TYPE", "물품")
G2B_MODULAR_SCOPE_ENABLED = os.getenv("G2B_MODULAR_SCOPE_ENABLED", "true").lower() in {"1", "true", "yes", "y"}
G2B_BUSINESS_TYPES = os.getenv("G2B_BUSINESS_TYPES", "물품,용역")
G2B_SERVICE_SUBTYPE = os.getenv("G2B_SERVICE_SUBTYPE", "일반용역")
G2B_MODULAR_LOOKBACK_DAYS = int(os.getenv("G2B_MODULAR_LOOKBACK_DAYS", os.getenv("G2B_ITEM_LOOKBACK_DAYS", "180")))
G2B_MODULAR_PAGE_SIZE = int(os.getenv("G2B_MODULAR_PAGE_SIZE", os.getenv("G2B_ITEM_PAGE_SIZE", "100")))
G2B_ITEM_LOOKBACK_DAYS = int(os.getenv("G2B_ITEM_LOOKBACK_DAYS", "90"))
G2B_ITEM_PAGE_SIZE = int(os.getenv("G2B_ITEM_PAGE_SIZE", "100"))
G2B_INCLUDE_CANCELLED = os.getenv("G2B_INCLUDE_CANCELLED", "true").lower() in {"1", "true", "yes", "y"}
G2B_INCLUDE_CORRECTION = os.getenv("G2B_INCLUDE_CORRECTION", "true").lower() in {"1", "true", "yes", "y"}
G2B_DETAIL_BASE_ENDPOINT = os.getenv(
    "G2B_DETAIL_BASE_ENDPOINT",
    "https://apis.data.go.kr/1230000/ad/BidPublicInfoService",
)
G2B_DETAIL_USE_API_LINK = os.getenv("G2B_DETAIL_USE_API_LINK", "true").lower() in {"1", "true", "yes", "y"}
G2B_PLAN_LOOKAHEAD_MONTHS = int(os.getenv("G2B_PLAN_LOOKAHEAD_MONTHS", "12"))
G2B_PLAN_PAGE_SIZE = int(os.getenv("G2B_PLAN_PAGE_SIZE", "100"))
G2B_PLAN_TITLE_KEYWORD = os.getenv("G2B_PLAN_TITLE_KEYWORD", "모듈러")
G2B_PLAN_BASE_ENDPOINT = os.getenv(
    "G2B_PLAN_BASE_ENDPOINT",
    "https://apis.data.go.kr/1230000/ao/OrderPlanSttusService",
)
G2B_PLAN_GOODS_ENDPOINT = os.getenv("G2B_PLAN_GOODS_ENDPOINT", "")
G2B_PLAN_SERVICE_ENDPOINT = os.getenv("G2B_PLAN_SERVICE_ENDPOINT", "")
G2B_PLAN_CONSTRUCTION_ENDPOINT = os.getenv("G2B_PLAN_CONSTRUCTION_ENDPOINT", "")
G2B_PLAN_FOREIGN_ENDPOINT = os.getenv("G2B_PLAN_FOREIGN_ENDPOINT", "")
LH_LOOKBACK_DAYS = int(os.getenv("LH_LOOKBACK_DAYS", "180"))
LH_PAGE_SIZE = int(os.getenv("LH_PAGE_SIZE", "100"))
LH_OPENBID_ENDPOINT = os.getenv(
    "LH_OPENBID_ENDPOINT",
    "https://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev",
)
LH_PORTAL_BASE_URL = os.getenv("LH_PORTAL_BASE_URL", "https://ebid.lh.or.kr")
LH_BID_LIST_URL = os.getenv(
    "LH_BID_LIST_URL",
    "https://ebid.lh.or.kr/ebid.et.tp.cmd.BidMasterListCmd.dev",
)
LH_DEEP_LINK_PROBE_ENABLED = os.getenv("LH_DEEP_LINK_PROBE_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
    "y",
}
D2B_LOOKAHEAD_MONTHS = int(os.getenv("D2B_LOOKAHEAD_MONTHS", "12"))
D2B_PAGE_SIZE = int(os.getenv("D2B_PAGE_SIZE", "50"))
D2B_PLAN_BASE_ENDPOINT = os.getenv(
    "D2B_PLAN_BASE_ENDPOINT",
    "https://openapi.d2b.go.kr/openapi/service/PrcurePlanInfoService",
)
D2B_PLAN_DOMESTIC_ENDPOINT = os.getenv(
    "D2B_PLAN_DOMESTIC_ENDPOINT",
    "http://openapi.d2b.go.kr/openapi/service/PrcurePlanInfoService/getDmstcPrcurePlanList",
)
D2B_PLAN_FACILITY_ENDPOINT = os.getenv("D2B_PLAN_FACILITY_ENDPOINT", "")
D2B_LEGACY_API_ENABLED = os.getenv("D2B_LEGACY_API_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
    "y",
}
D2B_BID_LOOKBACK_DAYS = int(os.getenv("D2B_BID_LOOKBACK_DAYS", "90"))
D2B_BID_PAGE_SIZE = int(os.getenv("D2B_BID_PAGE_SIZE", "50"))
D2B_BID_BASE_ENDPOINT = os.getenv(
    "D2B_BID_BASE_ENDPOINT",
    "https://openapi.d2b.go.kr/openapi/service/BidPblancInfoService",
)
D2B_BID_DOMESTIC_ENDPOINT = os.getenv("D2B_BID_DOMESTIC_ENDPOINT", "")
D2B_BID_FOREIGN_ENDPOINT = os.getenv("D2B_BID_FOREIGN_ENDPOINT", "")
D2B_BID_PUBLIC_PRIVATE_ENDPOINT = os.getenv("D2B_BID_PUBLIC_PRIVATE_ENDPOINT", "")
D2B_PORTAL_BASE_URL = os.getenv("D2B_PORTAL_BASE_URL", "https://www.d2b.go.kr")
D2B_DEEP_LINK_PROBE_ENABLED = os.getenv("D2B_DEEP_LINK_PROBE_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
    "y",
}
D2B_PLAN_DEEP_LINK_CANDIDATES = os.getenv("D2B_PLAN_DEEP_LINK_CANDIDATES", "")
D2B_BID_DEEP_LINK_CANDIDATES = os.getenv("D2B_BID_DEEP_LINK_CANDIDATES", "")
