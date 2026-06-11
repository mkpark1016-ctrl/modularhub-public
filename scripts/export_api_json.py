from __future__ import annotations

import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api_contract import (
    get_api_manifest,
    get_bids,
    get_favorites,
    get_health,
    get_news,
    get_patents,
    get_rnd_announces,
    get_rnd_outcomes,
    get_trends,
)


EXPORT_DIR = Path("exports/api")


def write_json(name: str, payload: object) -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {path}")


def main() -> int:
    write_json("manifest.json", get_api_manifest())
    write_json("health.json", get_health())
    write_json("bids.json", get_bids(limit=1000))
    write_json("news.json", get_news(limit=1000))
    write_json("rnd-announces.json", get_rnd_announces(limit=1000))
    write_json("rnd-outcomes.json", get_rnd_outcomes(limit=1000))
    write_json("patents.json", get_patents(limit=1000))
    write_json("trends.json", get_trends())
    write_json("favorites.json", get_favorites(limit=1000))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
