from __future__ import annotations

import re
from typing import Any, Iterable

from scripts.integrations.business.base import clean_text
from scripts.integrations.technology.base import NormalizedTechnologyRecord, validate_raw_payload_keys


KIPRIS_SOURCE = "kipris"
KAIA_NEWTECH_SOURCE = "kaia_newtech"


def _pick(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _names(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        values: Iterable[Any] = value
    else:
        values = re.split(r"[;|]", str(value or ""))
    return tuple(dict.fromkeys(name for item in values if (name := clean_text(item))))


def _keywords(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        values: Iterable[Any] = value
    else:
        values = re.split(r"[,;|]", str(value or ""))
    return tuple(dict.fromkeys(keyword for item in values if (keyword := clean_text(item))))


class KiprisFixtureAdapter:
    """Normalize saved KIPRISPlus fixture rows without performing network I/O."""

    source = KIPRIS_SOURCE

    def normalize_raw_record(self, raw: dict[str, Any]) -> NormalizedTechnologyRecord:
        validate_raw_payload_keys(raw)
        application_number = _pick(raw, "applicationNumber", "application_number")
        registration_number = _pick(raw, "registrationNumber", "registration_number")
        patent_number = _pick(raw, "patentNumber", "patent_number")
        external_id = _pick(raw, "externalId", "external_id", "publicationNumber")
        if not external_id:
            external_id = application_number or registration_number or patent_number
        applicants = _names(_pick(raw, "applicantName", "applicant", "applicants"))
        owners = _names(_pick(raw, "rightHolder", "owner", "owners"))
        return NormalizedTechnologyRecord(
            source=self.source,
            external_id=str(external_id or ""),
            title=str(_pick(raw, "inventionTitle", "title") or ""),
            record_type="patent",
            applicants=applicants,
            owners=owners,
            application_number=application_number,
            registration_number=registration_number,
            patent_number=patent_number,
            status=_pick(raw, "registrationStatus", "legalStatus", "status"),
            application_date=_pick(raw, "applicationDate", "application_date"),
            registration_date=_pick(raw, "registrationDate", "registration_date"),
            expiration_date=_pick(raw, "expirationDate", "expiration_date"),
            abstract=_pick(raw, "astrtCont", "abstract"),
            keywords=_keywords(_pick(raw, "keywords", "keyword")),
            technology_area=_pick(raw, "technologyArea", "technology_area"),
            source_url=_pick(raw, "sourceUrl", "source_url"),
            collected_at=_pick(raw, "collectedAt", "collected_at"),
            source_updated_at=_pick(raw, "sourceUpdatedAt", "source_updated_at"),
        )


class KaiaNewTechnologyFixtureAdapter:
    """Normalize saved KAIA construction-new-technology rows without network I/O."""

    source = KAIA_NEWTECH_SOURCE

    def normalize_raw_record(self, raw: dict[str, Any]) -> NormalizedTechnologyRecord:
        validate_raw_payload_keys(raw)
        newtech_number = _pick(raw, "apntNo", "newtechNumber", "newtech_number")
        external_id = _pick(raw, "newtecId", "externalId", "external_id") or newtech_number
        return NormalizedTechnologyRecord(
            source=self.source,
            external_id=str(external_id or ""),
            title=str(_pick(raw, "newtecNm", "title") or ""),
            record_type="construction_new_technology",
            developers=_names(_pick(raw, "dvlprNm", "developers")),
            registration_number=(f"건설신기술 제{newtech_number}호" if str(newtech_number or "").isdigit() else newtech_number),
            newtech_number=newtech_number,
            status=_pick(raw, "status") or "registered",
            designation_date=_pick(raw, "notDt", "designationDate", "designation_date"),
            expiration_date=_pick(raw, "prtDt", "expirationDate", "expiration_date"),
            abstract=_pick(raw, "newtecCts", "newtecScope", "abstract"),
            keywords=_keywords(_pick(raw, "keyword", "keywords")),
            technology_area=_pick(raw, "tecDvs", "technologyArea", "technology_area"),
            source_url=_pick(raw, "sourceUrl", "source_url"),
            collected_at=_pick(raw, "collectedAt", "collected_at"),
            source_updated_at=_pick(raw, "sourceUpdatedAt", "source_updated_at"),
        )


def adapter_for_source(source: str):
    normalized = str(source or "").strip().lower()
    if normalized == KIPRIS_SOURCE:
        return KiprisFixtureAdapter()
    if normalized == KAIA_NEWTECH_SOURCE:
        return KaiaNewTechnologyFixtureAdapter()
    raise ValueError(f"unsupported technology source={source!r}")
