from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.verify_sh_public_housing_contests_live import exit_code_for_status  # noqa: E402


def main() -> int:
    assert exit_code_for_status("success") == 0
    assert exit_code_for_status("success_no_matches") == 0
    assert exit_code_for_status("parser_mismatch") == 2
    assert exit_code_for_status("wrong_page_type") == 2
    assert exit_code_for_status("network_error") == 3
    assert exit_code_for_status("blocked") == 4
    assert exit_code_for_status("http_error") == 5
    assert exit_code_for_status("failed", "mutation_detected") == 1
    print("SH live verifier contract tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
