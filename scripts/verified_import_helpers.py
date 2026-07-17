from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

FIXED_GENERATED_AT = '2026-07-16T22:30:00+09:00'
STATUS_TO_EVENT = {
    'completed': 'completed', 'under_construction': 'in_progress',
    'contracted': 'contract_signed', 'awarded': 'award_confirmed',
    'preferred_bidder': 'preferred_bidder', 'planned': 'planned',
    'cancelled': 'cancelled', 'unconfirmed': 'unconfirmed', 'unknown': 'unconfirmed',
}
PROJECT_CREDIT_STATUSES = {'completed', 'under_construction', 'contracted', 'awarded'}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def dump(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def unique(values):
    result = []
    for value in values or []:
        if value not in result:
            result.append(copy.deepcopy(value))
    return result


def upsert(items: list[dict[str, Any]], key: str, value: dict[str, Any]) -> None:
    target = value.get(key)
    for index, item in enumerate(items):
        if item.get(key) == target:
            items[index] = copy.deepcopy(value)
            return
    items.append(copy.deepcopy(value))


def base_company(profile: dict[str, Any], company_id: str) -> dict[str, Any]:
    return {
        'schema_version': 'company-master-v1', 'company_id': company_id,
        'company_name': profile['company_name'], 'company_name_en': profile.get('company_name_en'),
        'aliases': unique(profile.get('aliases') or [profile['company_name']]), 'country_code': 'KR',
        'company_type': profile['company_type'], 'competitive_role': profile['competitive_role'],
        'analysis_tier': profile['analysis_tier'], 'business_status': 'active',
        'modular_methods': unique(profile.get('modular_methods', [])),
        'target_markets': unique(profile.get('target_markets', [])),
        'headquarters': profile.get('headquarters'), 'website_url': None,
        'listed_market': profile.get('listed_market'), 'ticker': profile.get('ticker'),
        'summary': profile['summary_ko'], 'last_verified_at': FIXED_GENERATED_AT,
        'data_confidence': 'high', 'review_status': 'verified',
        'company_profile': {'modular_business_started_year': None, 'business_status': 'active',
                            'scope': {'design': None, 'manufacturing': None, 'construction': None, 'integration': None}},
        'production': [], 'project_portfolio': [], 'bidding_performance': [],
        'technology': {'structural_systems': [], 'connection_technologies': [],
                       'fire_resistance_certifications': [], 'seismic_technologies': [],
                       'highrise_track_record': None, 'new_construction_technologies': [],
                       'patents': [], 'innovative_procurement_products': [], 'factory_completion_rate': None},
        'financials': [], 'recent_signals': [], 'sources': [], 'intelligence_v2': {},
    }


def ensure_v1_company(v1, curated):
    company_id = curated['company_id']
    for company in v1.setdefault('companies', []):
        if company.get('company_id') == company_id:
            return company
    company = base_company(curated['company'], company_id)
    v1['companies'].append(company)
    return company


def ensure_v2_company(v2, curated):
    profile = curated['company']
    upsert(v2.setdefault('companies', []), 'company_id', {
        'company_id': curated['company_id'], 'company_name': profile['company_name'],
        'company_type': profile['company_type'], 'competitive_role': profile['competitive_role'],
        'analysis_tier': profile['analysis_tier'], 'visibility': 'public',
    })


def source_record(curated):
    source = curated['source']
    return {
        'source_id': source['source_id'], 'source_type': source['source_type'],
        'source_name': source['title'], 'title': source['title'], 'source_url': None,
        'published_at': None, 'accessed_at': curated['reviewed_at'],
        'publisher': 'Manual verified competitor research', 'primary_source': False,
        'confidence': 'high', 'verification_note': source['note'],
        'supported_claims': [
            'identity', 'financials', 'production', 'projects', 'technology', 'strategy',
            'facility_name', 'location', 'ownership_type', 'operation_status',
            'site_area_m2', 'building_area_m2', 'site_area', 'building_area',
            'production_scope', 'production_processes', 'reported_capacity', 'capacity_value',
        ],
        'visibility': 'internal',
    }


def normalize_financial(financial, source_id):
    record = copy.deepcopy(financial)
    record.update(source_ids=[source_id], verified_at=FIXED_GENERATED_AT, confidence='high')
    for field in ('revenue', 'gross_profit', 'operating_profit', 'net_income',
                  'operating_cash_flow', 'modular_segment_revenue'):
        metric = record.get(field)
        if isinstance(metric, dict):
            metric.update(fiscal_year=record['year'], reporting_scope=record['scope'],
                          source_ids=[source_id], confidence='high', verification_status='cross_verified')
    return record


def archive_financials(company):
    if company.get('financial_reference_archive') is not None:
        return
    company['financial_reference_archive'] = [{
        'year': item.get('year'), 'scope': item.get('scope'),
        'source_ids': copy.deepcopy(item.get('source_ids', [])),
        'revenue_source_value': (item.get('revenue') or {}).get('source_value'),
        'gross_profit_source_value': (item.get('gross_profit') or {}).get('source_value'),
        'operating_profit_source_value': (item.get('operating_profit') or {}).get('source_value'),
    } for item in company.get('financials', []) or []]


def normalize_facility(facility, company_id, source_id):
    result = copy.deepcopy(facility)
    system_map = {
        'pc_ramen': 'pc_modular', 'pc_volumetric': 'pc_modular',
        'wood_volumetric': 'timber_modular', 'wood_panelized': 'timber_modular',
    }
    result['modular_system_type'] = system_map.get(
        result.get('modular_system_type'), result.get('modular_system_type')
    )
    result.update(company_id=company_id, source_ids=[source_id], source_count=1,
                  verified_at=FIXED_GENERATED_AT[:10], data_confidence='high', confidence='high',
                  verification_status='cross_verified', site_area=result.get('site_area_m2'),
                  site_area_unit='m2', verification_basis_label='ChatGPT 보조 검토 및 사람 직접 검증 기준')
    if result.get('reported_capacity') is not None:
        result['capacity_value'] = result['reported_capacity']
        result['capacity_scope'] = result.get('capacity_scope') or ', '.join(result.get('production_scope') or []) or 'facility_total'
        result['capacity_status'] = 'third_party_reported'
    else:
        result['capacity_status'] = result.get('capacity_status') or 'unavailable'
    return result


def normalize_project(project, company_id, source_id):
    result = copy.deepcopy(project)
    structure_map = {
        'pc_ramen': 'precast_concrete_modular', 'pc_volumetric': 'precast_concrete_modular',
        'steel_panelized': 'steel_frame_panelized',
        'wood_volumetric': 'timber_modular', 'wood_panelized': 'timber_modular',
    }
    structure_type = structure_map.get(result.get('modular_method'), result.get('modular_method') or 'unknown')
    result.update(company_id=company_id, aliases=unique(result.get('aliases', [])), country_code='KR',
                  sector=result.get('market_segment') or result.get('building_use') or 'other',
                  structure_type=structure_type, modular_type=structure_type, evidence_status='verified',
                  data_confidence='high', source_ids=[source_id], source_count=1, primary_source_count=0,
                  verified_at=FIXED_GENERATED_AT[:10], client_name=result.get('client'),
                  role_detail=result.get('summary'), project_summary=result.get('summary'),
                  research_wave='manual_verified_baseline', enrichment_status='manual_verified')
    result['project_credit'] = bool(result.get('project_credit')) and result.get('project_status') in PROJECT_CREDIT_STATUSES
    return result


def normalize_technology(item, source_id):
    result = copy.deepcopy(item)
    result.update(source_ids=[source_id], source_count=1, verified_at=FIXED_GENERATED_AT[:10],
                  verification_status='cross_verified', confidence='high')
    return result


def technology_bucket(record_type):
    if record_type == 'construction_new_technology':
        return 'new_construction_technologies'
    if record_type == 'structural_performance_certification':
        return 'seismic_technologies'
    return 'patents'


def source_groups(sources):
    groups = {}
    for source in sources:
        st = str(source.get('source_type') or '').lower()
        sid = str(source.get('source_id') or '').lower()
        if st == 'manual_verified_research': group = 'other'
        elif 'dart' in st or sid.startswith('dart-'): group = 'dart'
        elif source.get('primary_source'): group = 'company_official'
        elif st in {'media_article', 'research_report'}: group = 'media_and_research'
        else: group = 'other'
        groups.setdefault(group, []).append({
            'source_id': source.get('source_id'), 'publisher': source.get('publisher') or source.get('source_name'),
            'title': source.get('title') or source.get('source_name'), 'url': source.get('source_url'),
            'published_at': source.get('published_at'), 'retrieved_at': source.get('accessed_at'),
            'document_id': source.get('document_id'),
        })
    return [{'group_type': group, 'count': len(items), 'sources': items} for group, items in groups.items()]


def clean_old_manual_v2(v2, company_ids):
    def old_manual(item):
        return item.get('company_id') in company_ids and any(
            str(source).startswith(('internal-research-', 'manual-verified-')) for source in item.get('source_ids', []))
    v2['facts'] = [item for item in v2.get('facts', []) if item.get('company_id') not in company_ids]
    v2['events'] = [item for item in v2.get('events', []) if not old_manual(item)]
    v2['evidence'] = [item for item in v2.get('evidence', []) if not str(item.get('source_id', '')).startswith(('internal-research-', 'manual-verified-'))]


def v2_fact(company_id, domain, field, value, unit, period, source_id):
    suffix = str(period) if period is not None else 'current'
    return {'fact_id': f'fact-{company_id}-{domain}-{field}-{suffix}', 'company_id': company_id,
            'domain': domain, 'field': field, 'value': copy.deepcopy(value), 'unit': unit,
            'period': period, 'as_of': FIXED_GENERATED_AT, 'verification_status': 'cross_verified',
            'confidence': 'high', 'source_ids': [source_id], 'visibility': 'public',
            'updated_at': FIXED_GENERATED_AT}


def v2_project_event(project, company_id, source_id):
    project_credit = bool(project.get('project_credit')) and project.get('project_status') in PROJECT_CREDIT_STATUSES
    return {'event_id': f"event-{project['project_id']}", 'company_id': company_id,
            'event_type': 'project', 'event_status': STATUS_TO_EVENT.get(project.get('project_status'), 'unconfirmed'),
            'title': project['project_name'], 'counterparties': unique([project.get('client')] if project.get('client') else []),
            'client': project.get('client'), 'project_role': project.get('company_role'),
            'project_credit': project_credit, 'announced_at': project.get('announced_at'),
            'contracted_at': project.get('contract_date'), 'started_at': project.get('start_date'),
            'completed_at': project.get('completion_date'), 'amount': project.get('contract_amount'),
            'amount_unit': project.get('contract_amount_unit'), 'location': project.get('location'),
            'market_segment': project.get('market_segment'), 'method': project.get('modular_method'),
            'source_ids': [source_id], 'verification_status': 'cross_verified', 'visibility': 'public',
            'updated_at': FIXED_GENERATED_AT}


def v2_strategy_event(item, company_id, source_id):
    return {'event_id': item['event_id'], 'company_id': company_id, 'event_type': item['event_type'],
            'event_status': item['event_status'], 'title': item['title'],
            'counterparties': unique(item.get('counterparties', [])), 'client': item.get('client'),
            'project_role': item.get('project_role'), 'project_credit': bool(item.get('project_credit', False)),
            'announced_at': item.get('announced_at'), 'contracted_at': item.get('contracted_at'),
            'started_at': item.get('started_at'), 'completed_at': item.get('completed_at'),
            'amount': item.get('amount'), 'amount_unit': item.get('amount_unit'),
            'location': item.get('location'), 'market_segment': item.get('market_segment'),
            'method': item.get('method'), 'source_ids': [source_id],
            'verification_status': 'cross_verified', 'visibility': 'public', 'updated_at': FIXED_GENERATED_AT}
