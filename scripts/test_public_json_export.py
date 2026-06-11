from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "frontend" / "public" / "data"
FILES = {name: DATA_DIR / f"{name}.json" for name in ("business", "news", "meta")}
BANNED_TEXT = (
    "servicekey",
    "data_go_kr_service_key",
    "naver_client_secret",
    "naver_client_id",
    "rnd_announce",
    "rnd_outcome",
    '"source_type": "patent"',
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "export_public_json.py")], cwd=ROOT, check=True)
    for name, path in FILES.items():
        require(path.exists(), f"missing {name}.json")

    combined = "\n".join(path.read_text(encoding="utf-8") for path in FILES.values()).lower()
    for token in BANNED_TEXT:
        require(token.lower() not in combined, f"public JSON contains banned token: {token}")

    business = json.loads(FILES["business"].read_text(encoding="utf-8"))
    news = json.loads(FILES["news"].read_text(encoding="utf-8"))
    meta = json.loads(FILES["meta"].read_text(encoding="utf-8"))
    require(isinstance(business.get("items"), list), "business items must be a list")
    require(isinstance(news.get("items"), list), "news items must be a list")
    require(meta.get("business_count") == len(business["items"]), "business count mismatch")
    require(meta.get("news_count") == len(news["items"]), "news count mismatch")

    for item in business["items"]:
        require(item.get("title"), "business item title is missing")
        require(item.get("source"), "business item source is missing")
        require(isinstance(item.get("manual_check"), dict), "business manual_check is missing")
        require(item["source_type"] in {"bid", "procurement_plan"}, "unexpected business source_type")
    for item in news["items"]:
        require(item.get("original_url"), "news original_url is missing")
        require(item.get("source_type") is None, "news contract must not expose unrelated source_type")

    print(f"business items: {len(business['items'])}")
    print(f"news items: {len(news['items'])}")
    print("PUBLIC JSON EXPORT TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
