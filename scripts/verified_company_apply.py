from __future__ import annotations

import copy

from verified_import_helpers import *


def apply_company(v1, v2, curated):
    company_id = curated['company_id']
    profile = curated['company']
    source_id = curated['source']['source_id']
    company = ensure_v1_company(v1, curated)
    ensure_v2_company(v2, curated)

    company.update({
        'company_name': profile['company_name'], 'company_name_en': profile.get('company_name_en'),
        'aliases': unique(profile.get('aliases') or [profile['company_name']]),
        'company_type': profile['company_type'], 'competitive_role': profile['competitive_role'],
        'analysis_tier': profile['analysis_tier'], 'business_status': 'active',
        'modular_methods': unique(profile.get('modular_methods', [])),
        'target_markets': unique(profile.get('target_markets', [])),
        'headquarters': profile.get('headquarters'),
        'listed_market': profile.get('listed_market') or company.get('listed_market'),
        'ticker': profile.get('ticker') or company.get('ticker'), 'summary': profile['summary_ko'],
        'last_verified_at': FIXED_GENERATED_AT, 'data_confidence': 'high', 'review_status': 'verified',
    })
    company.setdefault('company_profile', {}).update({
        'established_at': profile.get('established_at'), 'listed_at': profile.get('listed_at'),
        'representative': profile.get('representative'),
        'employee_count': profile.get('employee_count_research_value'),
        'employee_count_as_of': profile.get('employee_count_as_of'),
        'major_businesses': copy.deepcopy(profile.get('major_businesses', [])),
        'modular_business_model': profile.get('modular_business_model'),
        'offices': copy.deepcopy(profile.get('offices', [])), 'business_status': 'active',
    })

    archive_financials(company)
    company['financials'] = [normalize_financial(item, source_id) for item in sorted(
        curated.get('financials', []), key=lambda item: item['year'], reverse=True)]
    modular_available = any(item.get('modular_segment_available') for item in company['financials'])
    company['financial_summary'] = {
        'financial_area_status': 'verified', 'years_available': [item['year'] for item in company['financials']],
        'modular_segment_available': modular_available,
        'modular_segment_name': '모듈러 매출' if modular_available else None,
        'modular_segment_revenue': None, 'modular_segment_operating_profit': None,
        'modular_segment_basis': '수동 검증 기준자료' if modular_available else '별도 모듈러 부문 수치 없음',
        'source_ids': [source_id], 'verified_at': FIXED_GENERATED_AT,
    }

    company['production'] = [normalize_facility(item, company_id, source_id) for item in curated.get('production', [])]
    active = [item for item in company['production'] if item.get('operation_status') not in {'planned', 'under_construction'}]
    manufacturing_model = 'own_manufacturing' if active else 'outsourced_manufacturing'
    own_status = 'confirmed_own_facility' if active else 'not_publicly_confirmed'
    if any(item.get('own_facility_status') == 'confirmed_partner_manufacturing' for item in active):
        manufacturing_model = 'partner_manufacturing'
    company['production_summary'] = {
        'summary': f"수동 검증 생산시설 {len(company['production'])}개소 반영" if company['production'] else '자체 생산시설 없음 또는 외부 제작사 협력형',
        'manufacturing_model': manufacturing_model, 'own_facility_status': own_status,
        'verification_status': 'cross_verified' if company['production'] else 'not_applicable',
        'confirmed_facility_count': len(active),
        'reported_capacity_available': any(item.get('reported_capacity') is not None for item in company['production']),
        'source_ids': [source_id], 'data_confidence': 'high', 'verified_at': FIXED_GENERATED_AT[:10],
    }

    company['project_portfolio'] = [normalize_project(item, company_id, source_id) for item in curated.get('projects', [])]
    company['project_candidates'] = []
    company['project_research_status'] = {
        'research_status': 'manual_verified_baseline', 'research_wave': 'verified_20260716',
        'verified_project_count': sum(1 for item in company['project_portfolio'] if item.get('project_credit')),
        'candidate_project_count': sum(1 for item in company['project_portfolio'] if not item.get('project_credit')),
        'raw_candidate_article_count': 0, 'rejected_candidate_count': 0, 'official_source_count': 0,
        'research_gap_count': 0, 'verified_at': FIXED_GENERATED_AT[:10],
    }

    technology = company.get('technology') if isinstance(company.get('technology'), dict) else {}
    for bucket, value in list(technology.items()):
        if isinstance(value, list):
            technology[bucket] = []
    for bucket in ('patents', 'new_construction_technologies', 'seismic_technologies'):
        technology.setdefault(bucket, [])
    for item in curated.get('technology', []):
        technology[technology_bucket(item.get('record_type', 'patent'))].append(normalize_technology(item, source_id))
    company['technology'] = technology

    company['recent_signals'] = [{
        'signal_id': item['event_id'], 'signal_type': item['event_type'], 'title': item['title'],
        'occurred_at': item.get('announced_at') or item.get('contracted_at'), 'summary': item.get('summary'),
        'significance': item.get('summary'), 'source_ids': [source_id], 'source_count': 1,
        'verified_at': FIXED_GENERATED_AT[:10], 'confidence': 'high',
    } for item in curated.get('strategy_events', [])]
    company['sources'] = [source_record(curated)]
    company['research_gaps'] = []
    for collection_name in ('financials', 'production', 'project_portfolio', 'recent_signals'):
        for item in company.get(collection_name, []) or []:
            if isinstance(item, dict):
                item['source_ids'] = [source_id]
    technology_values = company.get('technology') if isinstance(company.get('technology'), dict) else {}
    for values in technology_values.values():
        if isinstance(values, list):
            for item in values:
                if isinstance(item, dict):
                    item['source_ids'] = [source_id]

    facts = []
    identity_fields = [
        ('identity', 'company_name', profile.get('company_name'), None, None),
        ('organization', 'established_at', profile.get('established_at'), None, None),
        ('organization', 'listed_at', profile.get('listed_at'), None, None),
        ('organization', 'representative', profile.get('representative'), None, None),
        ('organization', 'employee_count', profile.get('employee_count_research_value'), 'person', profile.get('employee_count_as_of')),
        ('identity', 'headquarters', profile.get('headquarters'), None, None),
        ('organization', 'major_businesses', profile.get('major_businesses'), None, None),
        ('strategy', 'modular_business_model', profile.get('modular_business_model'), None, None),
    ]
    for domain, field, value, unit, period in identity_fields:
        if value not in (None, [], {}):
            facts.append(v2_fact(company_id, domain, field, value, unit, period, source_id))
    for financial in company['financials']:
        for field in ('revenue', 'gross_profit', 'operating_profit', 'modular_segment_revenue'):
            metric = financial.get(field)
            if isinstance(metric, dict):
                facts.append(v2_fact(company_id, 'financial', field, metric['source_value'], 'KRW', financial['year'], source_id))
    for facility in company['production']:
        facts.append(v2_fact(company_id, 'production', f"facility_{facility['facility_id']}", {
            'facility_name': facility.get('facility_name'), 'site_area_m2': facility.get('site_area_m2'),
            'capacity_value': facility.get('reported_capacity'), 'capacity_unit': facility.get('capacity_unit'),
            'capacity_period': facility.get('capacity_period'), 'capacity_basis': facility.get('capacity_basis'),
            'operation_status': facility.get('operation_status'),
        }, None, None, source_id))
    for item in curated.get('technology', []):
        facts.append(v2_fact(company_id, 'technology', item['technology_id'], {
            'name': item.get('name'), 'registration_number': item.get('registration_number'),
            'record_type': item.get('record_type'), 'registration_date': item.get('registration_date'),
        }, None, None, source_id))
    for fact in facts:
        upsert(v2.setdefault('facts', []), 'fact_id', fact)

    events = [v2_project_event(item, company_id, source_id) for item in curated.get('projects', [])]
    events.extend(v2_strategy_event(item, company_id, source_id) for item in curated.get('strategy_events', []))
    for event in events:
        upsert(v2.setdefault('events', []), 'event_id', event)

    upsert(v2.setdefault('evidence', []), 'source_id', {
        'source_id': source_id, 'source_type': 'manual_verified_research', 'source_tier': 'B',
        'publisher': 'Manual verified competitor research', 'title': curated['source']['title'],
        'url': None, 'published_at': None, 'retrieved_at': FIXED_GENERATED_AT,
        'document_id': None, 'document_hash': None, 'excerpt': curated['source']['note'],
        'supports': unique([item['fact_id'] for item in facts] + [item['event_id'] for item in events]),
        'contradicts': [], 'visibility': 'public', 'stale_after': None, 'status': 'active',
    })

    company_events = [item for item in v2.get('events', []) if item.get('company_id') == company_id]
    event_counts = {
        'verified_projects': sum(1 for item in company_events if item.get('event_type') == 'project' and item.get('project_credit')),
        'project_candidates': sum(1 for item in company_events if item.get('event_type') == 'project' and not item.get('project_credit')),
        'partnerships_mou': sum(1 for item in company_events if item.get('event_type') in {'partnership', 'mou'}),
        'r_and_d_exhibition': sum(1 for item in company_events if item.get('event_type') in {'r_and_d', 'exhibition'}),
        'other_events': sum(1 for item in company_events if item.get('event_type') not in {'project', 'partnership', 'mou', 'r_and_d', 'exhibition'}),
    }
    domains = {
        'identity_status': 'cross_verified', 'financial_status': 'cross_verified',
        'production_status': 'cross_verified' if company['production'] else 'unavailable',
        'project_status': 'cross_verified',
        'technology_status': 'cross_verified' if curated.get('technology') else 'unavailable',
        'recent_signal_status': 'cross_verified' if curated.get('strategy_events') else 'unavailable',
    }
    intelligence = {
        'summary_ko': profile['summary_ko'], 'overall_data_status': 'core_verified',
        'domain_statuses': domains, 'events': copy.deepcopy(company_events), 'event_counts': event_counts,
        'article_evidence_count': 0, 'source_groups': source_groups(company.get('sources', [])),
        'updated_at': FIXED_GENERATED_AT,
    }
    company['intelligence_v2'] = intelligence
    upsert(v2.setdefault('materialized_summaries', []), 'company_id', {
        'company_id': company_id, 'overall_data_status': 'core_verified', 'domain_statuses': domains,
        'event_counts': event_counts, 'article_evidence_count': 0,
        'source_group_counts': {item['group_type']: item['count'] for item in intelligence['source_groups']},
        'updated_at': FIXED_GENERATED_AT,
    })
