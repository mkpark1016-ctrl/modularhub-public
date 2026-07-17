#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / 'frontend/public/data/companies/companies.json'
V2 = ROOT / 'frontend/public/data/companies/company_intelligence_v2.json'
TARGETS = {
    'gs-ec', 'hyundai-engineering', 'samsung-ct-construction', 'dl-enc',
    'yuchang-enc', 'kumkang-kind', 'nrb', 'planm',
    'geogwang-enterprise', 'sungji-steel',
}
EXPECTED = {
    'gs-ec': (3, 3, 3),
    'hyundai-engineering': (0, 3, 14),
    'samsung-ct-construction': (1, 1, 7),
    'dl-enc': (0, 2, 21),
    'yuchang-enc': (4, 10, 7),
    'kumkang-kind': (3, 10, 4),
    'nrb': (2, 7, 16),
    'planm': (1, 17, 10),
    'geogwang-enterprise': (1, 1, 0),
    'sungji-steel': (3, 1, 2),
}


def load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def by_id(data, company_id):
    return next(item for item in data['companies'] if item['company_id'] == company_id)


def main() -> int:
    v1 = load(V1)
    v2 = load(V2)

    assert len(v1['companies']) == 10
    assert len(v2['companies']) == 10
    assert len(v2['materialized_summaries']) == 10
    assert len({item['company_id'] for item in v1['companies']}) == 10
    assert TARGETS == {item['company_id'] for item in v1['companies']}

    for company_id, (facility_count, project_count, technology_minimum) in EXPECTED.items():
        company = by_id(v1, company_id)
        assert company['review_status'] == 'verified'
        assert company['data_confidence'] == 'high'
        assert company['intelligence_v2']['overall_data_status'] == 'core_verified'
        assert len(company['financials']) == 3
        assert [item['year'] for item in company['financials']] == [2025, 2024, 2023]
        assert all(
            item['source_ids'] and item['scope'] in {'separate', 'consolidated', 'modular_segment'}
            for item in company['financials']
        )
        assert len(company.get('production', [])) == facility_count
        assert len(company.get('project_portfolio', [])) == project_count
        technology_count = sum(
            len(value)
            for value in company.get('technology', {}).values()
            if isinstance(value, list)
        )
        assert technology_count >= technology_minimum
        assert any(source.get('source_type') == 'manual_verified_research' for source in company.get('sources', []))
        assert company.get('research_gaps', []) == []

    assert by_id(v1, 'kumkang-kind')['financials'][0]['revenue']['source_value'] == 802_100_000_000
    assert by_id(v1, 'gs-ec')['financials'][0]['revenue']['source_value'] == 12_450_000_000_000
    assert by_id(v1, 'yuchang-enc')['financials'][0]['operating_profit']['source_value'] == 14_800_000_000
    assert by_id(v1, 'nrb')['financials'][0]['revenue']['source_value'] == 59_500_000_000
    assert by_id(v1, 'planm')['financials'][0]['revenue']['source_value'] == 59_200_000_000
    assert by_id(v1, 'sungji-steel')['financials'][0]['revenue']['source_value'] == 124_900_000_000

    assert next(
        item for item in by_id(v1, 'kumkang-kind')['production']
        if item['facility_id'] == 'kumkang-jincheon'
    )['capacity_basis'] == 'target_manual_verified'
    assert next(
        item for item in by_id(v1, 'yuchang-enc')['production']
        if item['facility_id'] == 'yuchang-dangjin-seokmun1'
    )['reported_capacity'] == 60
    assert next(
        item for item in by_id(v1, 'sungji-steel')['production']
        if item['facility_id'] == 'sungji-yeongdong10'
    )['capacity_unit'] == 'ton'

    events = {item['event_id']: item for item in v2['events']}
    assert events['event-yuchang-enc-samsung-ai-modular-home']['event_type'] == 'partnership'
    assert events['event-yuchang-enc-samsung-ai-modular-home']['project_credit'] is False
    assert events['event-planm-jindo-baseball-precon']['project_credit'] is False
    assert events['event-planm-indiana-l7-precon']['project_credit'] is False
    assert events['event-nrb-hanam-gyosan-a1']['event_type'] == 'mou'
    assert events['event-dl-buyeo-dongnam-1']['event_status'] == 'cancelled'

    for collection, key in (
        (v2['facts'], 'fact_id'),
        (v2['events'], 'event_id'),
        (v2['evidence'], 'source_id'),
    ):
        values = [item[key] for item in collection]
        assert len(values) == len(set(values))

    manual_evidence = [item for item in v2['evidence'] if item['source_type'] == 'manual_verified_research']
    assert len(manual_evidence) == 10
    assert all(item['url'] is None and item['source_tier'] == 'B' and item['supports'] for item in manual_evidence)
    assert not any(str(item.get('title', '')).lower().endswith('.pdf') for item in manual_evidence)

    print('VERIFIED COMPANY BASELINE TESTS PASSED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
