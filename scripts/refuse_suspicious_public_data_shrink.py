from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.public_data_policy import load_removal_allowlist  # noqa: E402

DATA_DIR = ROOT / "frontend" / "public" / "data"


def load(name: str) -> dict[str, Any]:
    payload = json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{name}.json must be an object with items")
    return payload


def load_git_head(name: str) -> dict[str, Any] | None:
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:frontend/public/data/{name}.json"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        payload = json.loads(result.stdout)
    except Exception:
        return None
    if isinstance(payload, list):
        return {"items": payload}
    return payload if isinstance(payload, dict) else {"items": []}


def load_git_history(name: str, *, limit: int = 25) -> list[dict[str, Any]]:
    rel_path = f"frontend/public/data/{name}.json"
    try:
        history = subprocess.run(
            ["git", "log", f"--format=%H", f"-n{limit}", "--", rel_path],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except Exception:
        return []
    payloads: list[dict[str, Any]] = []
    for sha in [line.strip() for line in history.stdout.splitlines() if line.strip()]:
        try:
            result = subprocess.run(
                ["git", "show", f"{sha}:{rel_path}"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            payload = json.loads(result.stdout)
        except Exception:
            continue
        if isinstance(payload, list):
            payloads.append({"items": payload})
        elif isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw_items = payload.get("items", [])
    return [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []


def largest_items(name: str, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [items(payload) for payload in load_git_history(name)] + [fallback]
    return max(candidates, key=len)


def integer(meta: dict[str, Any], name: str, fallback: int) -> int:
    try:
        return int(meta.get(name, fallback))
    except (TypeError, ValueError):
        return fallback


def id_map(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for item in items:
        item_id = str(item.get("id") or "").strip()
        if item_id:
            mapped[item_id] = item
    return mapped


def count_by(items: list[dict[str, Any]], key: str) -> Counter[str]:
    return Counter(str(item.get(key) or "unknown") for item in items)


def main() -> int:
    business = load("business").get("items", [])
    news = load("news").get("items", [])
    meta = load("meta")
    head_business = (load_git_head("business") or {}).get("items", [])
    head_news = (load_git_head("news") or {}).get("items", [])
    baseline_business = largest_items("business", head_business)
    if not business or not news:
        print(f"Public data shrink detected. business={len(business)}, news={len(news)}. Refusing commit.")
        return 1
    allowlist = load_removal_allowlist()
    current_business_by_id = id_map(business)
    head_business_by_id = id_map(baseline_business)
    unapproved_removed = [
        item_id
        for item_id in sorted(set(head_business_by_id) - set(current_business_by_id))
        if item_id not in allowlist
    ]
    if unapproved_removed:
        print(
            "Public data removal detected without approval. "
            f"removed_count={len(unapproved_removed)}, removed_ids={', '.join(unapproved_removed[:30])}. "
            "Add approved removals to config/public_data_removal_allowlist.json before committing."
        )
        return 1

    previous_business = max(
        len(head_business),
        len(baseline_business),
        integer(meta, "previous_business_count", len(business)),
        int(os.getenv("PUBLIC_DATA_BASELINE_BUSINESS_COUNT", "107")),
    )
    previous_news = max(
        len(head_news),
        integer(meta, "previous_news_count", len(news)),
        int(os.getenv("PUBLIC_DATA_BASELINE_NEWS_COUNT", "425")),
    )
    merged_business = integer(meta, "merged_business_count", len(business))
    merged_news = integer(meta, "merged_news_count", len(news))
    allow = os.getenv("ALLOW_PUBLIC_DATA_SHRINK", "false").lower() in {"1", "true", "yes", "y"}

    if merged_business != len(business) or merged_news != len(news):
        print(
            "Public data metadata mismatch. "
            f"business meta/file={merged_business}/{len(business)}, news meta/file={merged_news}/{len(news)}."
        )
        return 1

    business_limit = int(previous_business * 0.80)
    news_limit = int(previous_news * 0.70)
    suspicious = merged_business < business_limit or merged_news < news_limit
    if suspicious and not allow:
        print(
            "Public data shrink detected. "
            f"business {previous_business} -> {merged_business}, news {previous_news} -> {merged_news}. Refusing commit."
        )
        return 1
    previous_source_types = count_by(baseline_business, "source_type")
    current_source_types = count_by(business, "source_type")
    for source_type in ("public_agency_contest", "procurement_plan"):
        if current_source_types[source_type] < previous_source_types[source_type]:
            print(
                "Public data source_type shrink detected. "
                f"{source_type} {previous_source_types[source_type]} -> {current_source_types[source_type]}. "
                "Refusing commit without an approved removal list."
            )
            return 1
    previous_sources = count_by(baseline_business, "source")
    current_sources = count_by(business, "source")
    vanished_sources = [
        source
        for source, previous_count in previous_sources.items()
        if previous_count > 0 and current_sources[source] == 0
    ]
    if vanished_sources:
        print(f"Public data source vanished: {', '.join(sorted(vanished_sources))}. Refusing commit.")
        return 1
    status = "success" if merged_business >= previous_business and merged_news >= previous_news else "warning"
    print(f"PUBLIC DATA GUARD PASSED: business {previous_business} -> {merged_business}, news {previous_news} -> {merged_news}, status={status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
