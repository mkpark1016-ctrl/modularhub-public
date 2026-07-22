from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def latest(items: list[dict[str, Any]], *, source: str | None = None, relevance: str | None = None) -> str:
    latest_dt: datetime | None = None
    for item in items:
        if source and item.get("source") != source:
            continue
        if relevance and item.get("relevance_level") != relevance:
            continue
        parsed = parse_dt(item.get("published_at"))
        if parsed and (latest_dt is None or parsed > latest_dt):
            latest_dt = parsed
    return latest_dt.isoformat() if latest_dt else ""


def home_visible_items(items: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    seen: set[str] = set()

    def key(item: dict[str, Any]) -> str:
        return "".join(ch.lower() for ch in str(item.get("title") or "") if ch.isalnum() or ch.isspace()).strip()

    def unique(item: dict[str, Any]) -> bool:
        title_key = key(item)
        if not title_key:
            return True
        if title_key in seen:
            return False
        seen.add(title_key)
        return True

    def sort_key(item: dict[str, Any]) -> tuple[float, str]:
        parsed = parse_dt(item.get("published_at"))
        return (parsed.timestamp() if parsed else 0, str(item.get("title") or ""))

    direct = [item for item in items if item.get("relevance_level") == "direct"]
    adjacent = [item for item in items if item.get("relevance_level") == "adjacent"]
    direct = [item for item in sorted(direct, key=sort_key, reverse=True) if unique(item)]
    adjacent = [item for item in sorted(adjacent, key=sort_key, reverse=True) if unique(item)]
    return (direct + adjacent)[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit public news freshness without network access.")
    parser.add_argument("--news", type=Path, default=Path("frontend/public/data/news.json"))
    parser.add_argument("--meta", type=Path, default=Path("frontend/public/data/meta.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/public_news_freshness"))
    args = parser.parse_args()

    news_payload = json.loads(args.news.read_text(encoding="utf-8"))
    meta_payload = json.loads(args.meta.read_text(encoding="utf-8")) if args.meta.exists() else {}
    items = news_payload.get("items") if isinstance(news_payload, dict) else news_payload
    if not isinstance(items, list):
        raise SystemExit("news payload items must be a list")

    home_items = home_visible_items(items)
    summary = {
        "news_count": len(items),
        "generated_at": news_payload.get("generated_at") if isinstance(news_payload, dict) else "",
        "meta_generated_at": meta_payload.get("generated_at") if isinstance(meta_payload, dict) else "",
        "latest_public_news_at": latest(items),
        "latest_naver_news_at": latest(items, source="네이버뉴스"),
        "latest_direct_news_at": latest(items, relevance="direct"),
        "latest_adjacent_news_at": latest(items, relevance="adjacent"),
        "latest_homepage_visible_at": latest(home_items),
        "homepage_visible_titles": [item.get("title") for item in home_items],
        "news_source_statuses": meta_payload.get("news_source_statuses", []) if isinstance(meta_payload, dict) else [],
        "public_news_freshness_state": (
            news_payload.get("public_news_freshness_state")
            if isinstance(news_payload, dict)
            else meta_payload.get("public_news_freshness_state")
        ),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "public_news_freshness.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "## Public News Freshness",
        "",
        f"- news_count: `{summary['news_count']}`",
        f"- latest_public_news_at: `{summary['latest_public_news_at'] or '-'}`",
        f"- latest_naver_news_at: `{summary['latest_naver_news_at'] or '-'}`",
        f"- latest_direct_news_at: `{summary['latest_direct_news_at'] or '-'}`",
        f"- latest_adjacent_news_at: `{summary['latest_adjacent_news_at'] or '-'}`",
        f"- latest_homepage_visible_at: `{summary['latest_homepage_visible_at'] or '-'}`",
        f"- freshness_state: `{summary['public_news_freshness_state'] or '-'}`",
    ]
    for source in summary["news_source_statuses"]:
        lines.append(
            f"- {source.get('name') or source.get('source_name')}: state=`{source.get('state')}`, "
            f"fetched=`{source.get('fetched_count')}`, accepted=`{source.get('accepted_count')}`, "
            f"latest=`{source.get('latest_item_published_at') or '-'}`"
        )
    (args.output_dir / "public_news_freshness.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {args.output_dir / 'public_news_freshness.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
