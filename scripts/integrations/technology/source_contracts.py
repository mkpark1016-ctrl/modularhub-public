from __future__ import annotations

from dataclasses import dataclass

from scripts.integrations.technology.base import KAIA_API_KEY_ENV, KIPRIS_API_KEY_ENV


@dataclass(frozen=True)
class OfficialTechnologySourceContract:
    source: str
    service_name: str
    documentation_url: str
    response_format: str
    official_fields: tuple[str, ...]
    credential_parameter: str
    secret_env: str | None
    network_enabled: bool = False


KIPRIS_PATENT_CONTRACT = OfficialTechnologySourceContract(
    source="kipris",
    service_name="Patent and utility model publication and registration gazette",
    documentation_url="https://plus.kipris.or.kr/portal/search/clasList/List.do",
    response_format="XML",
    official_fields=(
        "ApplicationNumber",
        "RegistrationNumber",
        "InventionName",
        "RegistrationStatus",
        "Applicant",
        "ApplicationDate",
        "RegistrationDate",
        "Abstract",
        "InternationalpatentclassificationNumber",
    ),
    credential_parameter="accessKey",
    secret_env=KIPRIS_API_KEY_ENV,
    network_enabled=True,
)

KAIA_NEWTECH_CONTRACT = OfficialTechnologySourceContract(
    source="kaia_newtech",
    service_name="KAIA construction new technology Open API",
    documentation_url="https://www.kaia.re.kr/portal/bbs/view/B0000007/3494.do?menuNo=200026",
    response_format="XML",
    official_fields=(
        "newtecId",
        "apntNo",
        "newtecNm",
        "notDt",
        "newtecCts",
        "prtDt",
        "dvlprNm",
        "keyword",
        "tecDvs",
    ),
    credential_parameter="apiKey",
    secret_env=KAIA_API_KEY_ENV,
    network_enabled=True,
)

OFFICIAL_SOURCE_CONTRACTS = (KIPRIS_PATENT_CONTRACT, KAIA_NEWTECH_CONTRACT)
