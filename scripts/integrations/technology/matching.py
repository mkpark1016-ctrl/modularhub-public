from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
import unicodedata
from typing import Any, Iterable

from scripts.integrations.business.base import clean_text
from scripts.integrations.technology.base import NormalizedTechnologyRecord


CORPORATE_FORMS = (
    "주식회사",
    "유한회사",
    "(주)",
    "㈜",
    "co.,ltd.",
    "co., ltd.",
    "co ltd",
    "corporation",
)


def normalize_company_name(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", clean_text(value) or "").casefold()
    for form in CORPORATE_FORMS:
        text = text.replace(form.casefold(), "")
    return re.sub(r"[^0-9a-z가-힣]", "", text)


@dataclass(frozen=True)
class CompanyIdentity:
    company_id: str
    canonical_names: tuple[str, ...]
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class CompanyMatch:
    outcome: str
    company_ids: tuple[str, ...] = ()
    matched_names: tuple[str, ...] = ()
    ambiguous_names: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "company_ids": list(self.company_ids),
            "matched_names": list(self.matched_names),
            "ambiguous_names": list(self.ambiguous_names),
        }


def company_identities(companies: Iterable[dict[str, Any]]) -> list[CompanyIdentity]:
    identities = []
    for company in companies:
        company_id = clean_text(company.get("company_id") or company.get("id"))
        if not company_id:
            continue
        canonical = tuple(
            dict.fromkeys(
                value
                for key in ("company_name", "legal_name", "display_name", "company_name_en", "english_name")
                if (value := clean_text(company.get(key)))
            )
        )
        aliases = tuple(dict.fromkeys(value for item in company.get("aliases", []) if (value := clean_text(item))))
        identities.append(CompanyIdentity(company_id, canonical, aliases))
    return sorted(identities, key=lambda item: item.company_id)


def match_companies(
    record: NormalizedTechnologyRecord,
    identities: Iterable[CompanyIdentity],
) -> CompanyMatch:
    canonical_exact: dict[str, set[str]] = defaultdict(set)
    normalized_lookup: dict[str, set[str]] = defaultdict(set)
    for identity in identities:
        for name in identity.canonical_names:
            canonical_exact[unicodedata.normalize("NFC", name).casefold()].add(identity.company_id)
            normalized_lookup[normalize_company_name(name)].add(identity.company_id)
        for alias in identity.aliases:
            normalized_lookup[normalize_company_name(alias)].add(identity.company_id)

    participants = tuple(dict.fromkeys((*record.applicants, *record.owners, *record.developers)))
    matched_ids: set[str] = set()
    matched_names: list[str] = []
    ambiguous_names: list[str] = []
    used_alias = False
    for participant in participants:
        exact_ids = canonical_exact.get(unicodedata.normalize("NFC", participant).casefold(), set())
        candidates = exact_ids or normalized_lookup.get(normalize_company_name(participant), set())
        if len(candidates) > 1:
            ambiguous_names.append(participant)
            continue
        if len(candidates) == 1:
            matched_ids.update(candidates)
            matched_names.append(participant)
            used_alias = used_alias or not bool(exact_ids)

    if ambiguous_names:
        return CompanyMatch("ambiguous", tuple(sorted(matched_ids)), tuple(matched_names), tuple(ambiguous_names))
    if not matched_ids:
        return CompanyMatch("unmatched")
    return CompanyMatch("normalized_alias" if used_alias else "exact", tuple(sorted(matched_ids)), tuple(matched_names))
