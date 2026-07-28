from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.public_data_policy import dedupe_all_public_news_items  # noqa: E402


def load_items(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError("news payload must be a list or contain items")
    return [item for item in items if isinstance(item, dict)]


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        return None


def is_overseas(item: dict[str, Any]) -> bool:
    return (
        item.get("collection_pipeline") == "rss_overseas_pipeline"
        or item.get("publisher_region") == "overseas"
        or item.get("source") == "해외 모듈러 RSS"
        or item.get("source_name") == "해외 모듈러 RSS"
        or item.get("source") == "GDELT 해외뉴스"
        or item.get("source_name") == "GDELT 해외뉴스"
    )


def source_name(item: dict[str, Any]) -> str:
    return str(item.get("source_portal_name") or item.get("media") or item.get("source_name") or item.get("source") or "unknown")


def country_code(item: dict[str, Any]) -> str:
    return str(item.get("publisher_country_code") or item.get("country_code") or item.get("region") or "unknown").upper()


def build_report(items: list[dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    deduped = dedupe_all_public_news_items(items)
    recent_7_cutoff = now - timedelta(days=7)
    recent_30_cutoff = now - timedelta(days=30)
    dated_items = [(item, parse_datetime(item.get("published_at") or item.get("posted_at"))) for item in items]
    recent_7 = [item for item, published in dated_items if published and published >= recent_7_cutoff]
    recent_30 = [item for item, published in dated_items if published and published >= recent_30_cutoff]
    overseas = [item for item in items if is_overseas(item)]
    domestic = [item for item in items if not is_overseas(item)]
    overseas_recent_30 = [item for item, published in dated_items if is_overseas(item) and published and published >= recent_30_cutoff]
    return {
        "schemaVersion": "overseas-news-baseline-v1",
        "generatedAt": now.isoformat(),
        "totalNewsCount": len(items),
        "recent7DayNewsCount": len(recent_7),
        "recent30DayNewsCount": len(recent_30),
        "domesticNewsCount": len(domestic),
        "overseasNewsCount": len(overseas),
        "recent30DayOverseasNewsCount": len(overseas_recent_30),
        "recent30DayOverseasShare": round(len(overseas_recent_30) / len(recent_30), 4) if recent_30 else 0.0,
        "overseasBySource": dict(sorted(Counter(source_name(item) for item in overseas).items())),
        "overseasByCountryOrRegion": dict(sorted(Counter(country_code(item) for item in overseas).items())),
        "dedupe": {
            "beforeCount": len(items),
            "afterCount": len(deduped),
            "removedCount": len(items) - len(deduped),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Overseas News Baseline",
        "",
        f"- Total news: `{report['totalNewsCount']}`",
        f"- Recent 7 day news: `{report['recent7DayNewsCount']}`",
        f"- Recent 30 day news: `{report['recent30DayNewsCount']}`",
        f"- Domestic news: `{report['domesticNewsCount']}`",
        f"- Overseas news: `{report['overseasNewsCount']}`",
        f"- Recent 30 day overseas news: `{report['recent30DayOverseasNewsCount']}`",
        f"- Recent 30 day overseas share: `{report['recent30DayOverseasShare']}`",
        f"- Dedupe before/after: `{report['dedupe']['beforeCount']}` -> `{report['dedupe']['afterCount']}`",
        "",
        "## Overseas By Source",
        "",
    ]
    for source, count in report["overseasBySource"].items():
        lines.append(f"- `{source}`: `{count}`")
    lines.extend(["", "## Overseas By Country Or Region", ""])
    for country, count in report["overseasByCountryOrRegion"].items():
        lines.append(f"- `{country}`: `{count}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build current public overseas-news baseline metrics.")
    parser.add_argument("--input", type=Path, default=ROOT / "frontend/public/data/news.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/overseas-news-baseline")
    args = parser.parse_args()

    report = build_report(load_items(args.input))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "baseline.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "baseline.md").write_text(render_markdown(report), encoding="utf-8")
    print(
        "overseas_news_baseline "
        f"total={report['totalNewsCount']} "
        f"overseas={report['overseasNewsCount']} "
        f"recent30_overseas={report['recent30DayOverseasNewsCount']} "
        f"share={report['recent30DayOverseasShare']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
