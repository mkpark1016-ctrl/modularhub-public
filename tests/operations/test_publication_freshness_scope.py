import json
import sys

import pytest

from scripts import audit_public_data_freshness as audit

def rows():
    return [
        {"dataset": "news", "state": "healthy", "recordCount": 1},
        {"dataset": "business", "state": "healthy", "recordCount": 1},
        {"dataset": "companies", "state": "critical", "recordCount": 11},
    ]


def test_company_staleness_is_reported_without_blocking_other_publications():
    datasets = rows()
    assert audit.strict_audit_state(datasets, [], ["news", "business"]) == "healthy"
    assert audit.strict_audit_state(datasets, []) == "critical"
    assert datasets[2]["state"] == "critical"


@pytest.mark.parametrize("dataset", ["news", "business"])
def test_published_dataset_staleness_still_blocks(dataset):
    assert audit.strict_audit_state(
        [{"dataset": dataset, "state": "critical"}], [], ["news", "business"]
    ) == "critical"


@pytest.mark.parametrize("dataset", ["news", "business", "companies"])
def test_every_count_guard_remains_enforced(dataset):
    assert audit.strict_audit_state(
        rows(), [{"dataset": dataset, "state": "critical"}], ["news", "business"]
    ) == "critical"


@pytest.mark.parametrize("scoped,secret,expected", [(True, False, 0), (False, False, 1), (True, True, 2)])
def test_cli_scope_preserves_global_warning_and_secret_block(monkeypatch, tmp_path, scoped, secret, expected):
    datasets = [
        {**row, "warningThreshold": 1, "criticalThreshold": 2, "reason": "fixture"}
        for row in rows()
    ]
    monkeypatch.setattr(audit, "audit_datasets", lambda **kwargs: datasets)
    monkeypatch.setattr(audit, "load_optional", lambda path: {"items": [{"id": "fixture"}]})
    monkeypatch.setattr(audit, "source_health_from_payloads", lambda *args: [])
    monkeypatch.setattr(audit, "contains_secret_indicator", lambda *args: secret)
    args = ["audit", "--strict-critical", "--output-dir", str(tmp_path)]
    if scoped:
        args += ["--strict-datasets", "news", "business"]
    monkeypatch.setattr(sys, "argv", args)
    assert audit.main() == expected
    summary = json.loads((tmp_path / "freshness-summary.json").read_text(encoding="utf-8"))
    assert summary["overallState"] == "critical"
    assert summary["strictState"] == ("healthy" if scoped else "critical")
    assert any(row["dataset"] == "companies" for row in summary["alerts"])
