from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DB_PATH
from src.database import init_db


def main() -> int:
    init_db(DB_PATH)
    print(f"SQLite DB created: {DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
