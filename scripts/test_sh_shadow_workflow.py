from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "monitor-sh-public-housing-contests.yml"


def main() -> int:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "name: Monitor SH public housing contests" in text
    assert "workflow_dispatch:" in text
    assert "schedule:" in text
    assert "37 17 * * *" in text
    assert "python scripts/verify_sh_public_housing_contests_live.py" in text
    assert "--output-dir artifacts/sh_shadow" in text
    assert "scripts/test_sh_live_verifier_contract.py" in text
    assert "artifacts/sh_shadow/report.json" in text
    assert "artifacts/sh_shadow/report.md" in text
    assert "artifacts/sh_shadow/candidates.json" in text
    assert "sh-shadow-${{ github.run_id }}" in text
    assert "retention-days: 14" in text
    assert "success_no_matches" in text
    assert "public_json_unchanged" in text
    assert "db_unchanged" in text
    assert "env_unchanged" in text
    assert "continue-on-error" not in text
    assert "|| true" not in text
    print("SH shadow workflow tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
