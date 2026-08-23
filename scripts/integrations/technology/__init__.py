"""Offline company technology and patent integration contracts."""

from .adapters import KaiaNewTechnologyFixtureAdapter, KiprisFixtureAdapter, adapter_for_source
from .base import (
    KIPRIS_API_KEY_ENV,
    NormalizedTechnologyRecord,
    TECHNOLOGY_RECORD_TYPES,
    normalize_official_number,
    validate_public_source_url,
)
from .matching import CompanyIdentity, CompanyMatch, company_identities, match_companies
from .reconciliation import (
    NormalizationResult,
    baseline_identity_aliases,
    baseline_technology_records,
    normalize_fixture_records,
    reconcile_technology_records,
)
from .relevance import RelevanceDecision, assess_modular_relevance, classify_technology_area
from .source_contracts import KAIA_NEWTECH_CONTRACT, KIPRIS_PATENT_CONTRACT, OFFICIAL_SOURCE_CONTRACTS

__all__ = [
    "KIPRIS_API_KEY_ENV",
    "KAIA_NEWTECH_CONTRACT",
    "KIPRIS_PATENT_CONTRACT",
    "OFFICIAL_SOURCE_CONTRACTS",
    "TECHNOLOGY_RECORD_TYPES",
    "CompanyIdentity",
    "CompanyMatch",
    "KaiaNewTechnologyFixtureAdapter",
    "KiprisFixtureAdapter",
    "NormalizationResult",
    "NormalizedTechnologyRecord",
    "RelevanceDecision",
    "adapter_for_source",
    "assess_modular_relevance",
    "baseline_identity_aliases",
    "baseline_technology_records",
    "classify_technology_area",
    "company_identities",
    "match_companies",
    "normalize_fixture_records",
    "normalize_official_number",
    "reconcile_technology_records",
    "validate_public_source_url",
]
