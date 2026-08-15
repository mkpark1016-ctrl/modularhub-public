from __future__ import annotations

from typing import Any

from .base import ExternalBusinessSourceAdapter, NormalizedBusinessRecord, clean_text, parse_amount, parse_date


class MappingBusinessAdapter(ExternalBusinessSourceAdapter):
    """Small fixture-safe mapper for future API-specific adapters."""

    field_map: dict[str, str] = {}
    default_record_type = "bid_notice"

    def collect_raw_records(self) -> list[dict[str, Any]]:
        raise NotImplementedError("Live API collection is not enabled in Phase 10A")

    def value(self, raw: dict[str, Any], canonical_key: str) -> Any:
        source_key = self.field_map.get(canonical_key, canonical_key)
        return raw.get(source_key)

    def normalize_raw_record(self, raw: dict[str, Any]) -> NormalizedBusinessRecord:
        record_type = clean_text(self.value(raw, "source_record_type")) or self.default_record_type
        return NormalizedBusinessRecord(
            source=self.source,
            source_record_type=record_type,
            external_id=clean_text(self.value(raw, "external_id")) or "",
            title=clean_text(self.value(raw, "title")) or "",
            issuing_organization=clean_text(self.value(raw, "issuing_organization")),
            category=clean_text(self.value(raw, "category")),
            region=clean_text(self.value(raw, "region")),
            estimated_amount=parse_amount(self.value(raw, "estimated_amount")),
            currency=clean_text(self.value(raw, "currency")) or "KRW",
            published_at=parse_date(self.value(raw, "published_at")),
            deadline_at=parse_date(self.value(raw, "deadline_at")),
            status=clean_text(self.value(raw, "status")),
            contract_method=clean_text(self.value(raw, "contract_method")),
            source_url=clean_text(self.value(raw, "source_url")),
            collected_at=parse_date(self.value(raw, "collected_at")) or self.collected_now(),
            source_updated_at=parse_date(self.value(raw, "source_updated_at")),
        )


class LHBusinessAdapter(MappingBusinessAdapter):
    source = "LH"
    api_key_env = "LH_SERVICE_KEY"
    endpoint_env = "LH_OPENBID_ENDPOINT"
    field_map = {
        "external_id": "bidNum",
        "title": "bidName",
        "issuing_organization": "orderOrgName",
        "category": "bidType",
        "region": "regionName",
        "estimated_amount": "budgetAmount",
        "published_at": "bidStartDate",
        "deadline_at": "bidCloseDate",
        "status": "bidStatus",
        "contract_method": "contractMethod",
        "source_url": "detailUrl",
        "source_updated_at": "updatedAt",
    }


class D2BBusinessAdapter(MappingBusinessAdapter):
    source = "D2B"
    api_key_env = "D2B_SERVICE_KEY"
    endpoint_env = "D2B_GW_BASE_ENDPOINT"
    field_map = {
        "source_record_type": "recordType",
        "external_id": "noticeNo",
        "title": "noticeName",
        "issuing_organization": "agencyName",
        "category": "businessType",
        "region": "region",
        "estimated_amount": "estimatedPrice",
        "published_at": "noticeDate",
        "deadline_at": "closeDate",
        "status": "noticeStatus",
        "contract_method": "contractType",
        "source_url": "detailUrl",
        "source_updated_at": "updatedAt",
    }


class KepcoBusinessAdapter(MappingBusinessAdapter):
    source = "KEPCO"
    api_key_env = "KEPCO_API_KEY"
    endpoint_env = "KEPCO_BID_ENDPOINT"
    field_map = {
        "source_record_type": "record_type",
        "external_id": "bid_no",
        "title": "bid_title",
        "issuing_organization": "department",
        "category": "category",
        "region": "region",
        "estimated_amount": "estimated_amount",
        "currency": "currency",
        "published_at": "published_at",
        "deadline_at": "deadline_at",
        "status": "status",
        "contract_method": "contract_method",
        "source_url": "source_url",
        "source_updated_at": "source_updated_at",
    }
