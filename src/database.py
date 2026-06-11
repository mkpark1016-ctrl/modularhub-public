from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

import pandas as pd

from src.config import DB_PATH
from src.models import Item


CREATE_ITEMS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    title TEXT NOT NULL,
    organization TEXT,
    posted_at TEXT,
    due_at TEXT,
    amount INTEGER,
    region TEXT,
    keywords TEXT,
    summary TEXT,
    url TEXT,
    relevance_score REAL DEFAULT 0,
    unique_hash TEXT NOT NULL UNIQUE,
    is_mock INTEGER DEFAULT 0,
    data_quality TEXT DEFAULT 'real',
    original_url TEXT,
    source_search_url TEXT,
    link_type TEXT DEFAULT 'unknown',
    link_status TEXT DEFAULT 'unknown',
    link_checked_at TEXT,
    source_record_id TEXT,
    source_record_no TEXT,
    bid_no TEXT,
    bid_order TEXT,
    notice_status TEXT,
    business_type TEXT,
    business_subtype TEXT,
    operating_scope TEXT,
    is_operating_scope INTEGER DEFAULT 0,
    is_known_important INTEGER DEFAULT 0,
    contract_method TEXT,
    bid_method TEXT,
    demand_org TEXT,
    notice_org TEXT,
    exact_url_candidate TEXT,
    exact_url_verified INTEGER DEFAULT 0,
    exact_url_verified_at TEXT,
    exact_url_validation_reason TEXT,
    source_detail_api_url TEXT,
    source_portal_name TEXT,
    api_detail_verified INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_COLLECT_LOGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS collect_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collector_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    inserted_count INTEGER NOT NULL DEFAULT 0,
    updated_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);
"""

CREATE_SOURCE_DETAILS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS source_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_record_id TEXT,
    source_record_no TEXT,
    detail_api_url TEXT,
    detail_payload_json TEXT,
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL,
    error_message TEXT,
    UNIQUE(item_id, detail_api_url)
);
"""

CREATE_FAVORITES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

UpsertStatus = Literal["inserted", "updated", "skipped"]

ITEMS_OPTIONAL_COLUMNS = {
    "is_mock": "INTEGER DEFAULT 0",
    "data_quality": "TEXT DEFAULT 'real'",
    "original_url": "TEXT",
    "source_search_url": "TEXT",
    "link_type": "TEXT DEFAULT 'unknown'",
    "link_status": "TEXT DEFAULT 'unknown'",
    "link_checked_at": "TEXT",
    "source_record_id": "TEXT",
    "source_record_no": "TEXT",
    "bid_no": "TEXT",
    "bid_order": "TEXT",
    "notice_status": "TEXT",
    "business_type": "TEXT",
    "business_subtype": "TEXT",
    "operating_scope": "TEXT",
    "is_operating_scope": "INTEGER DEFAULT 0",
    "is_known_important": "INTEGER DEFAULT 0",
    "contract_method": "TEXT",
    "bid_method": "TEXT",
    "demand_org": "TEXT",
    "notice_org": "TEXT",
    "exact_url_candidate": "TEXT",
    "exact_url_verified": "INTEGER DEFAULT 0",
    "exact_url_verified_at": "TEXT",
    "exact_url_validation_reason": "TEXT",
    "source_detail_api_url": "TEXT",
    "source_portal_name": "TEXT",
    "api_detail_verified": "INTEGER DEFAULT 0",
}


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(CREATE_ITEMS_TABLE_SQL)
        conn.execute(CREATE_COLLECT_LOGS_TABLE_SQL)
        conn.execute(CREATE_SOURCE_DETAILS_TABLE_SQL)
        conn.execute(CREATE_FAVORITES_TABLE_SQL)
        _ensure_items_columns(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_source_type ON items(source_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_due_at ON items(due_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_posted_at ON items(posted_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_data_quality ON items(data_quality)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_link_type ON items(link_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_source_details_item_id ON source_details(item_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_source_details_source ON source_details(source_name, source_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_favorites_item_id ON favorites(item_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_collect_logs_started_at ON collect_logs(started_at)")


def _ensure_items_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(items)").fetchall()}
    for column, definition in ITEMS_OPTIONAL_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE items ADD COLUMN {column} {definition}")


def upsert_item(item: Item, db_path: Path = DB_PATH) -> UpsertStatus:
    data = item.model_dump(mode="json")
    with get_connection(db_path) as conn:
        existing = conn.execute(
            """
            SELECT source_type, source_name, title, organization, posted_at, due_at,
                   amount, region, keywords, summary, url, relevance_score,
                   is_mock, data_quality, original_url, source_search_url, link_type,
                   link_status, link_checked_at, source_record_id, source_record_no,
                   bid_no, bid_order, notice_status, business_type, business_subtype,
                   operating_scope, is_operating_scope, is_known_important, contract_method,
                   bid_method, demand_org, notice_org,
                   exact_url_candidate, exact_url_verified, exact_url_verified_at,
                   exact_url_validation_reason, source_detail_api_url, source_portal_name,
                   api_detail_verified,
                   unique_hash
            FROM items
            WHERE unique_hash = ?
            """,
            (data["unique_hash"],),
        ).fetchone()

        if existing is None and data["source_type"] == "news":
            if data.get("url"):
                existing = conn.execute(
                    """
                    SELECT source_type, source_name, title, organization, posted_at, due_at,
                           amount, region, keywords, summary, url, relevance_score,
                           is_mock, data_quality, original_url, source_search_url, link_type,
                           link_status, link_checked_at, source_record_id, source_record_no,
                           bid_no, bid_order, notice_status, business_type, business_subtype,
                           operating_scope, is_operating_scope, is_known_important, contract_method,
                           bid_method, demand_org, notice_org,
                           exact_url_candidate, exact_url_verified, exact_url_verified_at,
                           exact_url_validation_reason, source_detail_api_url, source_portal_name,
                           api_detail_verified,
                           unique_hash
                    FROM items
                    WHERE source_type = ? AND source_name = ? AND url = ?
                    """,
                    (data["source_type"], data["source_name"], data["url"]),
                ).fetchone()
            if existing is None and data.get("title"):
                existing = conn.execute(
                    """
                    SELECT source_type, source_name, title, organization, posted_at, due_at,
                           amount, region, keywords, summary, url, relevance_score,
                           is_mock, data_quality, original_url, source_search_url, link_type,
                           link_status, link_checked_at, source_record_id, source_record_no,
                           bid_no, bid_order, notice_status, business_type, business_subtype,
                           operating_scope, is_operating_scope, is_known_important, contract_method,
                           bid_method, demand_org, notice_org,
                           exact_url_candidate, exact_url_verified, exact_url_verified_at,
                           exact_url_validation_reason, source_detail_api_url, source_portal_name,
                           api_detail_verified,
                           unique_hash
                    FROM items
                    WHERE source_type = ? AND source_name = ? AND title = ? AND posted_at IS ?
                    """,
                    (data["source_type"], data["source_name"], data["title"], data["posted_at"]),
                ).fetchone()
            if existing is not None:
                data["unique_hash"] = existing["unique_hash"]

        if existing is None and data["source_name"] in {"나라장터", "G2B", "조달청"} and data.get("source_record_id"):
            existing = conn.execute(
                """
                SELECT source_type, source_name, title, organization, posted_at, due_at,
                       amount, region, keywords, summary, url, relevance_score,
                       is_mock, data_quality, original_url, source_search_url, link_type,
                       link_status, link_checked_at, source_record_id, source_record_no,
                       bid_no, bid_order, notice_status, business_type, business_subtype,
                       operating_scope, is_operating_scope, is_known_important, contract_method,
                       bid_method, demand_org, notice_org,
                       exact_url_candidate, exact_url_verified, exact_url_verified_at,
                       exact_url_validation_reason, source_detail_api_url, source_portal_name,
                       api_detail_verified,
                       unique_hash
                FROM items
                WHERE source_type = ?
                  AND source_name IN ('나라장터', 'G2B', '조달청')
                  AND source_record_id = ?
                  AND COALESCE(source_record_no, '') = COALESCE(?, '')
                  AND COALESCE(business_type, '') = COALESCE(?, '')
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    data["source_type"],
                    data["source_record_id"],
                    data.get("source_record_no"),
                    data.get("business_type"),
                ),
            ).fetchone()
            if existing is not None:
                data["unique_hash"] = existing["unique_hash"]

        if existing is None:
            conn.execute(
                """
                INSERT INTO items (
                    source_type, source_name, title, organization, posted_at, due_at,
                    amount, region, keywords, summary, url, relevance_score, unique_hash,
                    is_mock, data_quality, original_url, source_search_url, link_type,
                    link_status, link_checked_at, source_record_id, source_record_no,
                    bid_no, bid_order, notice_status, business_type, business_subtype,
                    operating_scope, is_operating_scope, is_known_important, contract_method,
                    bid_method, demand_org, notice_org,
                    exact_url_candidate, exact_url_verified, exact_url_verified_at,
                    exact_url_validation_reason, source_detail_api_url, source_portal_name,
                    api_detail_verified
                ) VALUES (
                    :source_type, :source_name, :title, :organization, :posted_at, :due_at,
                    :amount, :region, :keywords, :summary, :url, :relevance_score, :unique_hash,
                    :is_mock, :data_quality, :original_url, :source_search_url, :link_type,
                    :link_status, :link_checked_at, :source_record_id, :source_record_no,
                    :bid_no, :bid_order, :notice_status, :business_type, :business_subtype,
                    :operating_scope, :is_operating_scope, :is_known_important, :contract_method,
                    :bid_method, :demand_org, :notice_org,
                    :exact_url_candidate, :exact_url_verified, :exact_url_verified_at,
                    :exact_url_validation_reason, :source_detail_api_url, :source_portal_name,
                    :api_detail_verified
                )
                """,
                data,
            )
            return "inserted"

        comparable_fields = [
            "source_type",
            "source_name",
            "title",
            "organization",
            "posted_at",
            "due_at",
            "amount",
            "region",
            "keywords",
            "summary",
            "url",
            "relevance_score",
            "is_mock",
            "data_quality",
            "original_url",
            "source_search_url",
            "link_type",
            "link_status",
            "link_checked_at",
            "source_record_id",
            "source_record_no",
            "bid_no",
            "bid_order",
            "notice_status",
            "business_type",
            "business_subtype",
            "operating_scope",
            "is_operating_scope",
            "is_known_important",
            "contract_method",
            "bid_method",
            "demand_org",
            "notice_org",
            "exact_url_candidate",
            "exact_url_verified",
            "exact_url_verified_at",
            "exact_url_validation_reason",
            "source_detail_api_url",
            "source_portal_name",
            "api_detail_verified",
        ]
        if all(existing[field] == data[field] for field in comparable_fields):
            return "skipped"

        conn.execute(
            """
            UPDATE items SET
                source_type=:source_type,
                source_name=:source_name,
                title=:title,
                organization=:organization,
                posted_at=:posted_at,
                due_at=:due_at,
                amount=:amount,
                region=:region,
                keywords=:keywords,
                summary=:summary,
                url=:url,
                relevance_score=:relevance_score,
                is_mock=:is_mock,
                data_quality=:data_quality,
                original_url=:original_url,
                source_search_url=:source_search_url,
                link_type=:link_type,
                link_status=:link_status,
                link_checked_at=:link_checked_at,
                source_record_id=:source_record_id,
                source_record_no=:source_record_no,
                bid_no=:bid_no,
                bid_order=:bid_order,
                notice_status=:notice_status,
                business_type=:business_type,
                business_subtype=:business_subtype,
                operating_scope=:operating_scope,
                is_operating_scope=:is_operating_scope,
                is_known_important=:is_known_important,
                contract_method=:contract_method,
                bid_method=:bid_method,
                demand_org=:demand_org,
                notice_org=:notice_org,
                exact_url_candidate=:exact_url_candidate,
                exact_url_verified=:exact_url_verified,
                exact_url_verified_at=:exact_url_verified_at,
                exact_url_validation_reason=:exact_url_validation_reason,
                source_detail_api_url=:source_detail_api_url,
                source_portal_name=:source_portal_name,
                api_detail_verified=:api_detail_verified,
                updated_at=CURRENT_TIMESTAMP
            WHERE unique_hash=:unique_hash
            """,
            data,
        )
        return "updated"


def insert_collect_log(
    *,
    collector_name: str,
    source_type: str,
    started_at: str,
    finished_at: str | None,
    status: str,
    inserted_count: int,
    updated_count: int,
    skipped_count: int,
    error_message: str | None = None,
    db_path: Path = DB_PATH,
) -> None:
    init_db(db_path)
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO collect_logs (
                collector_name, source_type, started_at, finished_at, status,
                inserted_count, updated_count, skipped_count, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                collector_name,
                source_type,
                started_at,
                finished_at,
                status,
                inserted_count,
                updated_count,
                skipped_count,
                error_message,
            ),
        )


def load_items_dataframe(db_path: Path = DB_PATH) -> pd.DataFrame:
    init_db(db_path)
    with get_connection(db_path) as conn:
        df = pd.read_sql_query(
            """
            SELECT id, source_type, source_name, title, organization, posted_at, due_at,
                   amount, region, keywords, summary, url, relevance_score,
                   unique_hash, is_mock, data_quality, original_url, source_search_url,
                   link_type, link_status, link_checked_at, source_record_id, source_record_no,
                   bid_no, bid_order, notice_status, business_type, business_subtype,
                   operating_scope, is_operating_scope, is_known_important, contract_method,
                   bid_method, demand_org, notice_org,
                   exact_url_candidate, exact_url_verified, exact_url_verified_at,
                   exact_url_validation_reason, source_detail_api_url, source_portal_name,
                   api_detail_verified,
                   created_at, updated_at
            FROM items
            ORDER BY COALESCE(posted_at, created_at) DESC, id DESC
            """,
            conn,
        )

    if df.empty:
        return df

    df["posted_at"] = pd.to_datetime(df["posted_at"], errors="coerce").dt.date
    df["due_at"] = pd.to_datetime(df["due_at"], errors="coerce").dt.date
    return df


def load_collect_logs_dataframe(db_path: Path = DB_PATH, limit: int = 10) -> pd.DataFrame:
    init_db(db_path)
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT collector_name, source_type, started_at, finished_at, status,
                   inserted_count, updated_count, skipped_count, error_message
            FROM collect_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            conn,
            params=(limit,),
        )


def upsert_source_detail(
    *,
    item_id: int,
    source_name: str,
    source_type: str,
    source_record_id: str | None,
    source_record_no: str | None,
    detail_api_url: str | None,
    detail_payload_json: str | None,
    status: str,
    error_message: str | None = None,
    db_path: Path = DB_PATH,
) -> None:
    init_db(db_path)
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO source_details (
                item_id, source_name, source_type, source_record_id, source_record_no,
                detail_api_url, detail_payload_json, fetched_at, status, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
            ON CONFLICT(item_id, detail_api_url) DO UPDATE SET
                source_name=excluded.source_name,
                source_type=excluded.source_type,
                source_record_id=excluded.source_record_id,
                source_record_no=excluded.source_record_no,
                detail_payload_json=excluded.detail_payload_json,
                fetched_at=CURRENT_TIMESTAMP,
                status=excluded.status,
                error_message=excluded.error_message
            """,
            (
                item_id,
                source_name,
                source_type,
                source_record_id,
                source_record_no,
                detail_api_url,
                detail_payload_json,
                status,
                error_message,
            ),
        )


def load_source_detail(item_id: int, db_path: Path = DB_PATH) -> dict | None:
    init_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM source_details
            WHERE item_id = ?
            ORDER BY fetched_at DESC, id DESC
            LIMIT 1
            """,
            (item_id,),
        ).fetchone()
        return dict(row) if row else None


def load_favorite_item_ids(db_path: Path = DB_PATH) -> set[int]:
    init_db(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT item_id FROM favorites").fetchall()
        return {int(row["item_id"]) for row in rows}


def add_favorite(item_id: int, db_path: Path = DB_PATH) -> None:
    init_db(db_path)
    with get_connection(db_path) as conn:
        conn.execute("INSERT OR IGNORE INTO favorites (item_id) VALUES (?)", (int(item_id),))


def remove_favorite(item_id: int, db_path: Path = DB_PATH) -> None:
    init_db(db_path)
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM favorites WHERE item_id = ?", (int(item_id),))


def add_favorites(item_ids: list[int], db_path: Path = DB_PATH) -> int:
    init_db(db_path)
    clean_ids = [int(item_id) for item_id in item_ids if item_id is not None]
    if not clean_ids:
        return 0
    with get_connection(db_path) as conn:
        before = conn.total_changes
        conn.executemany("INSERT OR IGNORE INTO favorites (item_id) VALUES (?)", [(item_id,) for item_id in clean_ids])
        return conn.total_changes - before
