# Company report onboarding fixtures

`tests/test_company_report_onboarding.py` builds synthetic candidate and manifest fixtures in `tmp_path` from the existing validated audit-report schema. The generated fixtures cover:

- pass new company
- pass existing company update
- review required for pending page checks
- blocked scope/unit/source/required metric errors
- unsafe paths
- preview SHA mismatch
- atomic promotion success and rollback

Static PDFs, OCR output, real private reports, and secrets are intentionally not stored here.
