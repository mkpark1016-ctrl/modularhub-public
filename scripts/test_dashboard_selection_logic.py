from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import get_selected_rows_from_dataframe_event, selected_item_id_from_display_df


def assert_equal(actual: object, expected: object, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected={expected!r}, actual={actual!r}")


def item_id_from_tab(df: pd.DataFrame, row_index: int) -> int | None:
    display_df = df.copy().reset_index(drop=True)
    display_df["_item_id"] = display_df["id"].astype(int)
    return selected_item_id_from_display_df(display_df, [row_index])


def main() -> None:
    df = pd.DataFrame(
        [
            {"id": 101, "source_type": "bid", "title": "중복 제목", "relevance_score": 5, "is_due_soon": True},
            {"id": 202, "source_type": "procurement_plan", "title": "조달계획", "relevance_score": 9, "is_due_soon": False},
            {"id": 303, "source_type": "news", "title": "중복 제목", "relevance_score": 10, "is_due_soon": False},
            {"id": 404, "source_type": "bid", "title": "고관련 입찰", "relevance_score": 12, "is_due_soon": False},
        ]
    )

    assert_equal(item_id_from_tab(df, 0), 101, "전체 탭 row index to item_id")
    assert_equal(item_id_from_tab(df[df["source_type"] == "bid"], 1), 404, "입찰·공고 탭 row index to item_id")
    assert_equal(item_id_from_tab(df[df["source_type"] == "procurement_plan"], 0), 202, "조달계획 탭 row index to item_id")
    assert_equal(item_id_from_tab(df[df["source_type"] == "news"], 0), 303, "뉴스 탭 row index to item_id")
    assert_equal(item_id_from_tab(df[df["is_due_soon"]], 0), 101, "마감임박 탭 row index to item_id")
    assert_equal(item_id_from_tab(df[df["relevance_score"] >= 8], 1), 303, "고관련도 탭 row index to item_id")

    event_object = SimpleNamespace(selection=SimpleNamespace(rows=[2]))
    assert_equal(get_selected_rows_from_dataframe_event(event_object), [2], "object event selection rows")
    event_dict = {"selection": {"rows": [1]}}
    assert_equal(get_selected_rows_from_dataframe_event(event_dict), [1], "dict event selection rows")
    assert_equal(get_selected_rows_from_dataframe_event(None), [], "none event selection rows")
    assert_equal(selected_item_id_from_display_df(df.assign(_item_id=df["id"]), []), None, "empty selection keeps previous state")

    duplicate_title_ids = df[df["title"] == "중복 제목"]["id"].tolist()
    assert_equal(duplicate_title_ids, [101, 303], "duplicate titles remain distinct by item_id")

    print("DASHBOARD SELECTION LOGIC TEST PASSED")


if __name__ == "__main__":
    main()
