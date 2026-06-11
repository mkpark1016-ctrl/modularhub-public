from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"
DB_PATH = PROJECT_ROOT / "data" / "modular_info.db"


def fail(message: str) -> int:
    print(f"SMOKE TEST FAILED: {message}")
    return 1


def main() -> int:
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")

    if not APP_PATH.exists():
        return fail(f"app.py not found: {APP_PATH}")
    print(f"app.py found: {APP_PATH}")

    if not DB_PATH.exists():
        return fail(f"database not found: {DB_PATH}")
    print(f"database found: {DB_PATH}")

    with sqlite3.connect(DB_PATH) as conn:
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='items'"
        ).fetchone()
        if not table_exists:
            return fail("items table not found")

        count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        if count == 0:
            return fail("items table is empty")

    print("items table found")
    print(f"items count: {count}")
    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
