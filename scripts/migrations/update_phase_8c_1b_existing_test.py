from pathlib import Path

path = Path("frontend/scripts/test-company-insights.mjs")
text = path.read_text(encoding="utf-8")
old = '''assert.equal(summary.total, 11);\nassert.equal(summary.directCompetitors, 6);\nassert.equal(summary.coreVerified, 10);\n'''
new = '''assert.equal(summary.total, 11);\nassert.equal(summary.generalContractors, 4);\nassert.equal(summary.modularSpecialists, 7);\nassert.equal(summary.directModularCompetitors, 7);\nassert.equal(summary.directCompetitors, 7);\nassert.equal(summary.coreVerified, 10);\n'''
if text.count(old) != 1:
    raise SystemExit(f"expected one legacy summary assertion block, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Updated existing company insight assertions for Phase 8C-1B.")
