from pathlib import Path

path = Path("frontend/scripts/test-company-insights.mjs")
text = path.read_text(encoding="utf-8")

summary_old = '''assert.equal(summary.total, 11);\nassert.equal(summary.directCompetitors, 6);\nassert.equal(summary.coreVerified, 10);\n'''
summary_new = '''assert.equal(summary.total, 11);\nassert.equal(summary.generalContractors, 4);\nassert.equal(summary.modularSpecialists, 7);\nassert.equal(summary.directModularCompetitors, 7);\nassert.equal(summary.directCompetitors, 7);\nassert.equal(summary.coreVerified, 10);\n'''
if text.count(summary_old) != 1:
    raise SystemExit(f"expected one legacy summary assertion block, found {text.count(summary_old)}")
text = text.replace(summary_old, summary_new, 1)

filter_old = '''const direct = companies.filter((company) => companyMatchesFilters(company, { q: "", role: "all", relationship: "direct_competitor", tier: "all", status: "all" }));\nassert.equal(direct.length, 6);\n'''
filter_new = '''const direct = companies.filter((company) => companyMatchesFilters(company, { q: "", role: "all", relationship: "direct_competitor", tier: "all", status: "all" }));\nassert.equal(direct.length, 7);\n'''
if text.count(filter_old) != 1:
    raise SystemExit(f"expected one legacy direct competitor assertion block, found {text.count(filter_old)}")
text = text.replace(filter_old, filter_new, 1)

path.write_text(text, encoding="utf-8")
print("Updated existing company insight assertions for Phase 8C-1B.")
