from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from typing import Any

from verified_import_helpers import FIXED_GENERATED_AT

ROOT = Path(__file__).resolve().parents[1]
MODULE_DIR = ROOT / 'scripts/verified_companies'
MODULES = [
    'gs_ec.py', 'hyundai_engineering.py', 'samsung_ct_construction.py', 'dl_enc.py',
    'yuchang_enc.py', 'kumkang_kind.py', 'nrb.py', 'planm.py',
    'geogwang_enterprise.py', 'sungji_steel.py',
]


def load_compact(path: Path) -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return copy.deepcopy(module.COMPANY)


def metric(value: int | float | None, name: str):
    if value is None:
        return None
    return {
        'source_value': value, 'source_unit': 'KRW', 'normalized_value': value * 1e-6,
        'normalized_unit': 'KRW_MILLION', 'normalization_factor': 1e-6,
        'account_name': name, 'extraction_method': 'manual_verified_baseline',
        'verification_status': 'cross_verified', 'confidence': 'high',
    }


def compact_to_curated(compact: dict[str, Any]) -> dict[str, Any]:
    company_id = compact['id']
    source_id = f'manual-verified-{company_id}-20260716'
    source = {
        'source_id': source_id, 'source_type': 'manual_verified_research', 'source_tier': 'B',
        'verification_status': 'cross_verified', 'confidence': 'high', 'visibility': 'internal',
        'title': f"{compact['name']} 수동 검증 기업정보 기준선",
        'note': 'ChatGPT 보조 검토와 사람의 직접 검증으로 확정한 구조화 기준자료입니다. PDF 원본은 저장소에 포함하지 않습니다.',
    }
    profile = {
        'company_name': compact['name'], 'company_name_en': compact.get('en'),
        'aliases': compact.get('aliases', []), 'company_type': compact['type'],
        'competitive_role': compact['role'], 'analysis_tier': compact['tier'],
        'business_status': 'active', 'modular_methods': compact.get('methods', []),
        'target_markets': compact.get('markets', []), 'summary_ko': compact['summary'],
        'established_at': compact.get('est'), 'listed_at': compact.get('listed'),
        'listed_market': compact.get('listed_market'), 'ticker': compact.get('ticker'),
        'representative': compact.get('rep'), 'employee_count_research_value': compact.get('employees'),
        'employee_count_as_of': compact.get('emp_asof'), 'headquarters': compact.get('hq'),
        'major_businesses': compact.get('businesses', []),
        'modular_business_model': compact.get('model'), 'offices': compact.get('offices', []),
    }
    financials = []
    for year, scope, revenue, gross_profit, operating_profit, modular_revenue in compact.get('financials', []):
        financials.append({
            'year': year, 'scope': scope, 'reporting_scope': scope,
            'accounting_standard': 'K-IFRS' if scope == 'consolidated' else 'general_korean_gaap',
            'currency': 'KRW', 'basis': 'manual_verified_competitor_baseline',
            'verified_at': FIXED_GENERATED_AT, 'confidence': 'high',
            'revenue': metric(revenue, '매출액'), 'gross_profit': metric(gross_profit, '매출총이익'),
            'operating_profit': metric(operating_profit, '영업이익'),
            'net_income': None, 'operating_cash_flow': None,
            'modular_segment_available': modular_revenue is not None,
            'modular_segment_revenue': metric(modular_revenue, '모듈러 매출'),
        })
    production = []
    for row in compact.get('facilities', []):
        (facility_id, name, method, own_status, ownership, operation, country, address,
         site_area, capacity, unit, period, basis, capacity_status, notes, scope) = row
        production.append({
            'facility_id': facility_id, 'facility_name': name, 'facility_aliases': [],
            'facility_type': 'modular_factory', 'modular_system_type': method,
            'own_facility_status': own_status, 'ownership_type': ownership,
            'operator_name': None, 'operation_status': operation, 'country': country,
            'region': address, 'city': None, 'address': address, 'site_area_m2': site_area,
            'building_area_m2': None, 'production_scope': scope, 'structural_systems': [method],
            'production_processes': [], 'reported_capacity': capacity, 'capacity_unit': unit,
            'capacity_period': period, 'capacity_basis': basis, 'capacity_status': capacity_status,
            'verification_status': 'cross_verified', 'confidence': 'high', 'notes': notes,
        })
    projects = []
    for row in compact.get('projects', []):
        (project_id, name, client, location, use, method, role, status, announced,
         contracted, started, completed, project_credit, summary) = row
        projects.append({
            'project_id': project_id, 'project_name': name, 'client': client,
            'ordering_agency': client, 'location': location, 'building_use': use,
            'market_segment': use, 'modular_method': method, 'company_role': role,
            'project_status': status, 'announced_at': announced, 'contract_date': contracted,
            'start_date': started, 'completion_date': completed,
            'project_credit': bool(project_credit), 'contract_amount': None,
            'contract_amount_unit': None, 'verification_status': 'cross_verified',
            'confidence': 'high', 'summary': summary,
        })
    technology = []
    for technology_id, name, number, summary, filed, registered, record_type, status in compact.get('technology', []):
        technology.append({
            'technology_id': technology_id, 'name': name, 'registration_number': number,
            'summary': summary, 'filed_at': filed, 'registered_at': registered,
            'registration_date': registered, 'record_type': record_type, 'status': status,
            'verification_status': 'cross_verified', 'confidence': 'high',
        })
    strategy_events = []
    for event_id, event_type, event_status, title, date, location, method, project_credit, summary in compact.get('strategy', []):
        strategy_events.append({
            'event_id': event_id, 'event_type': event_type, 'event_status': event_status,
            'title': title, 'counterparties': [], 'client': None, 'project_role': None,
            'project_credit': bool(project_credit), 'announced_at': date,
            'contracted_at': None, 'started_at': None, 'completed_at': None,
            'amount': None, 'amount_unit': None, 'location': location,
            'market_segment': None, 'method': method, 'summary': summary,
        })
    return {
        'company_id': company_id, 'reviewed_at': FIXED_GENERATED_AT, 'source': source,
        'company': profile, 'financials': financials, 'production': production,
        'projects': projects, 'technology': technology, 'strategy_events': strategy_events,
    }


def load_verified_companies() -> list[dict[str, Any]]:
    targets = [compact_to_curated(load_compact(MODULE_DIR / name)) for name in MODULES]
    if len({item['company_id'] for item in targets}) != 10:
        raise RuntimeError('Expected 10 unique verified companies')
    return targets
