from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DB_PATH
from src.sample_loader import load_sample_data


def main() -> int:
    count = load_sample_data()
    print(f"Loaded {count} sample items into {DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
