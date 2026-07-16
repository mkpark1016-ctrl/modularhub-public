#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from verified_company_apply import apply_company
from verified_company_source import load_verified_companies
from verified_import_helpers import FIXED_GENERATED_AT, clean_old_manual_v2, dump, load

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_V1 = ROOT / 'frontend/public/data/companies/companies.json'
DEFAULT_V2 = ROOT / 'frontend/public/data/companies/company_intelligence_v2.json'
EXPECTED = {
    'gs-ec': (3, 3, 3), 'hyundai-engineering': (0, 3, 14),
    'samsung-ct-construction': (1, 1, 7), 'dl-enc': (0, 2, 21),
    'yuchang-enc': (4, 10, 7), 'kumkang-kind': (3, 10, 4),
    'nrb': (2, 7, 16), 'planm': (1, 17, 10),
    'geogwang-enterprise': (1, 1, 0), 'sungji-steel': (3, 1, 2),
}


def validate(v1, v2, targets):
    company_ids = [item.get('company_id') for item in v1.get('companies', [])]
    v2_ids = [item.get('company_id') for item in v2.get('companies', [])]
    summary_ids = [item.get('company_id') for item in v2.get('materialized_summaries', [])]
    for label, values in [('V1', company_ids), ('V2', v2_ids), ('summaries', summary_ids)]:
        if len(values) != 18 or len(set(values)) != 18:
            raise RuntimeError(f'{label} must contain 18 unique companies')
    target_ids = {item['company_id'] for item in targets}
    if set(EXPECTED) != target_ids or 'dl-enc' not in company_ids:
        raise RuntimeError('Verified company target set mismatch')
    by_id = {item['company_id']: item for item in v1['companies']}
    for company_id, (facility_count, project_count, technology_count) in EXPECTED.items():
        company = by_id[company_id]
        if company.get('review_status') != 'verified' or company.get('data_confidence') != 'high':
            raise RuntimeError(f'{company_id}: verification lifecycle mismatch')
        if len(company.get('financials', [])) != 3:
            raise RuntimeError(f'{company_id}: three financial years required')
        if len(company.get('production', [])) != facility_count:
            raise RuntimeError(f'{company_id}: facility count mismatch')
        if len(company.get('project_portfolio', [])) != project_count:
            raise RuntimeError(f'{company_id}: project count mismatch')
        actual_technology = sum(len(value) for value in (company.get('technology') or {}).values() if isinstance(value, list))
        if actual_technology < technology_count:
            raise RuntimeError(f'{company_id}: technology count mismatch')
        if company.get('intelligence_v2', {}).get('overall_data_status') != 'core_verified':
            raise RuntimeError(f'{company_id}: core_verified required')
    for collection, key in ((v2.get('facts', []), 'fact_id'), (v2.get('events', []), 'event_id'), (v2.get('evidence', []), 'source_id')):
        values = [item.get(key) for item in collection]
        if len(values) != len(set(values)):
            raise RuntimeError(f'Duplicate {key}')
    legacy = next(item for item in v2['events'] if item['event_id'] == 'event-yuchang-enc-samsung-ai-modular-home')
    if legacy.get('event_type') != 'partnership' or legacy.get('project_credit'):
        raise RuntimeError('YooChang-Samsung legacy item must remain a non-project partnership')
    if any(str(item.get('source_id', '')).lower().endswith('.pdf') for item in v2.get('evidence', [])):
        raise RuntimeError('Raw PDF reference must not be committed')
    return {
        'company_count': 18, 'verified_targets': len(targets),
        'facts': len(v2.get('facts', [])), 'events': len(v2.get('events', [])),
        'evidence': len(v2.get('evidence', [])),
    }


def patch_contract_files():
    replacements = {
        ROOT / 'scripts/validate_company_universe.py': [
            ('"tier_2": 5,', '"tier_2": 6,'),
            ('"strategic_benchmark": 4,', '"strategic_benchmark": 5,'),
            ('if len(rows) != 17:', 'if len(rows) != 18:'),
            ('expected 17 companies', 'expected 18 companies'),
        ],
        ROOT / 'scripts/test_company_universe.py': [
            ('len(companies) == 17', 'len(companies) == 18'),
            ('contain 17 companies', 'contain 18 companies'),
            ('get("tier_2") == 5', 'get("tier_2") == 6'),
        ],
    }
    for path, pairs in replacements.items():
        text = path.read_text(encoding='utf-8')
        for old, new in pairs:
            if old not in text and new not in text:
                raise RuntimeError(f'Expected contract text missing in {path}: {old}')
            text = text.replace(old, new)
        path.write_text(text, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--v1', type=Path, default=DEFAULT_V1)
    parser.add_argument('--v2', type=Path, default=DEFAULT_V2)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    targets = load_verified_companies()
    v1, v2 = load(args.v1), load(args.v2)
    clean_old_manual_v2(v2, {item['company_id'] for item in targets})
    for curated in targets:
        apply_company(v1, v2, curated)
    v1['generated_at'] = FIXED_GENERATED_AT
    v2['generated_at'] = FIXED_GENERATED_AT
    v2.setdefault('audit_metadata', {})['manual_verified_baseline'] = {
        'reviewed_at': FIXED_GENERATED_AT, 'company_count': 10, 'raw_pdf_committed': False,
    }
    result = validate(v1, v2, targets)
    if not args.check:
        dump(args.v1, v1)
        dump(args.v2, v2)
        patch_contract_files()
    result['mode'] = 'check' if args.check else 'write'
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
