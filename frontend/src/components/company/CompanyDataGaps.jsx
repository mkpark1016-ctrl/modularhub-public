import { formatNumber } from "./companyDetailHelpers";
import { companyDataGapRows } from "../../companyDataGaps";

export default function CompanyDataGaps({ company, reportInsight = null }) {
  const rows = companyDataGapRows(company, reportInsight);
  if (!rows.length) return null;
  return (
    <div className="company-subsection">
      <div className="company-subsection-heading">
        <h3>데이터 공백</h3>
        <span>보완 필요 {formatNumber(rows.length, "건")}</span>
      </div>
      <div className="company-data-gap-list">
        {rows.slice(0, 6).map((row) => (
          <article key={row.key}>
            <strong>{row.title}</strong>
            <p>{row.description}</p>
          </article>
        ))}
      </div>
    </div>
  );
}
