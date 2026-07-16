# Manually verified company baselines

These modules contain the structured company information that was reviewed with ChatGPT assistance and confirmed by a human reviewer on 2026-07-16.

## Scope

- General contractors: GS E&C, Hyundai Engineering, Samsung C&T Construction, DL E&C
- Modular manufacturers and integrators: YooChang E&C, Kumkang Kind, NRB, PLANM, Geogwang Enterprise, Sungji Steel
- Data domains: company profile, three-year financials, production facilities, project records, technology and strategy events

## Data handling rules

- The source PDF files are not stored in this repository.
- Confirmed contracts and completed projects receive project credit.
- MOU, Pre-Con, exhibitions, R&D and planned opportunities remain separate events and do not receive project credit.
- Production targets are stored with an explicit target basis rather than being represented as official realized capacity.
- Existing DART and public-source records remain available in the archived/reference fields when a manually verified display baseline replaces them.

Run `python scripts/import_verified_company_baseline.py` to regenerate the public V1 and V2 company JSON files.
