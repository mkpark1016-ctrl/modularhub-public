import { formatDate, labelValue } from "./components/company/companyDetailHelpers.js";
import { financialScopeLabel, reportSectionLabel, verificationStatusLabel } from "./companyReportInsights.js";

function sourceGroupLabel(type) {
  const labels = {
    dart: "공식·공시",
    company_official: "공식·공시",
    public_official: "공공기관",
    public_procurement: "공공기관",
    project: "프로젝트",
    patent: "특허",
    media_and_research: "언론",
    media: "언론",
    internal_verified: "내부 검증",
    other: "기타",
  };
  return labels[type] || labelValue(type, "기타");
}

const DOMAIN_CLAIMS = {
  identity: ["identity", "company_identity", "profile", "overview", "corporate"],
  financial: ["financial", "financials", "finance", "audit_report", "income_statement", "balance_sheet", "cash_flow"],
  production: ["production", "facility", "factory", "production_facility"],
  project: ["project", "projects", "delivery", "contract"],
  technology: ["technology", "patent", "patents", "ip"],
  recent_signal: ["recent_signal", "recent_signals", "news", "strategy", "market", "activity"],
};

function normalizeClaim(value) {
  return String(value || "").trim().toLowerCase();
}

function sourceMatchesDomain(source, domain) {
  const expected = new Set(DOMAIN_CLAIMS[domain] || [domain]);
  const claims = [
    ...(Array.isArray(source?.supportedClaims) ? source.supportedClaims : []),
    source?.groupType,
    source?.sourceType,
  ].map(normalizeClaim);
  return claims.some((claim) => expected.has(claim));
}

export function sourceHasPublicUrl(source) {
  const url = source?.url || source?.source_url || "";
  return /^https?:\/\//.test(String(url));
}

export function flattenCompanySources(company) {
  const groups = Array.isArray(company?.intelligence_v2?.source_groups)
    ? company.intelligence_v2.source_groups
    : [];
  const groupedRows = groups.flatMap((group) => (Array.isArray(group.sources) ? group.sources : []).map((source) => ({
      id: source.source_id,
      title: source.title || source.publisher || sourceGroupLabel(group.group_type),
      publisher: source.publisher || "기관 확인 중",
      sourceType: sourceGroupLabel(source.source_type || group.group_type),
      publishedAt: source.published_at || source.retrieved_at || source.accessed_at || "",
      documentId: source.document_id || "",
      url: source.url || source.source_url || "",
      groupType: group.group_type,
      supportedClaims: source.supported_claims || source.supportedClaims || [group.group_type],
    })));
  const rows = [...groupedRows];
  const seen = new Set(rows.map((row) => row.id).filter(Boolean));
  for (const source of Array.isArray(company?.sources) ? company.sources : []) {
    if (!source?.source_id || seen.has(source.source_id)) continue;
    rows.push({
      id: source.source_id,
      title: source.title || source.source_name || source.publisher || "출처 제목 확인 중",
      publisher: source.publisher || source.source_name || "기관 확인 중",
      sourceType: sourceGroupLabel(source.source_type),
      publishedAt: source.published_at || source.accessed_at || "",
      documentId: source.document_id || "",
      url: source.url || source.source_url || "",
      groupType: source.source_type || "other",
      note: source.verification_note || "",
      supportedClaims: source.supported_claims || [],
    });
  }
  return rows;
}

export function findCompanySources(company, sourceIds = []) {
  const ids = new Set((Array.isArray(sourceIds) ? sourceIds : []).filter(Boolean));
  if (!ids.size) return [];
  return flattenCompanySources(company).filter((source) => ids.has(source.id));
}

export function reportMetricSources(insight, metric) {
  const documents = new Map();
  for (const doc of insight?.source_summary?.primary_documents || []) {
    documents.set(doc.source_ref, doc);
  }
  const opinions = new Map();
  for (const opinion of insight?.source_summary?.audit_opinions || []) {
    opinions.set(opinion.source_ref, opinion);
  }
  return (metric?.source_locations || []).map((location) => {
    const doc = documents.get(location.source_ref) || {};
    const opinion = opinions.get(location.source_ref) || {};
    return {
      id: location.source_ref,
      title: doc.filename || "감사보고서",
      publisher: opinion.auditor || "감사인 확인 중",
      sourceType: "감사보고서",
      publishedAt: doc.report_date || opinion.auditor_report_date || "",
      pageRange: location.page_range || "",
      sectionLabel: reportSectionLabel(location.section),
      verificationStatus: verificationStatusLabel(location.verification_status),
      url: "",
    };
  });
}

export function buildReportMetricEvidence(insight, label, metric) {
  return {
    title: label,
    value: metric?.display_text || "확인되지 않음",
    note: `${financialScopeLabel(insight?.financial_scope || insight?.attribution?.financial_scope)} 기준`,
    sources: reportMetricSources(insight, metric),
  };
}

export function buildCompanyItemEvidence(company, title, value, sourceIds = [], note = "") {
  const sources = findCompanySources(company, sourceIds);
  const missingSourceNote = "이 항목과 직접 연결된 출처가 아직 정리되지 않았습니다.";
  const evidenceNote = sources.length ? note : [note, missingSourceNote].filter(Boolean).join(" ");
  return {
    title,
    value: value ?? "확인되지 않음",
    note: evidenceNote,
    evidenceStatus: sources.length ? "linked" : "source_pending",
    sources,
  };
}

export function buildSourceRows(company, reportInsight = null) {
  const rows = flattenCompanySources(company);
  if (reportInsight) {
    const seen = new Set(rows.map((row) => row.id));
    for (const doc of reportInsight.source_summary?.primary_documents || []) {
      if (seen.has(doc.source_ref)) continue;
      const opinion = (reportInsight.source_summary?.audit_opinions || []).find((item) => item.source_ref === doc.source_ref);
      rows.push({
        id: doc.source_ref,
        title: doc.filename || "감사보고서",
        publisher: opinion?.auditor || "감사인 확인 중",
        sourceType: "감사보고서",
        publishedAt: doc.report_date || opinion?.auditor_report_date || "",
        documentId: doc.source_role || "",
        url: "",
        groupType: "dart",
        supportedClaims: ["financial", "financials", "audit_report"],
      });
    }
  }
  return rows.sort((a, b) => String(b.publishedAt || "").localeCompare(String(a.publishedAt || "")));
}

export function sourcesForDomain(sourceRows, domain) {
  return (Array.isArray(sourceRows) ? sourceRows : []).filter((source) => sourceMatchesDomain(source, domain));
}

export function sourceTypeSummaryForDomain(sourceRows, domain) {
  const labels = [...new Set(sourcesForDomain(sourceRows, domain).map((row) => row.sourceType).filter(Boolean))];
  return labels.slice(0, 2).join(", ") || "영역별 연결 근거 확인 필요";
}

export function formatSourceDate(value) {
  return value ? formatDate(value) : "일자 확인 중";
}
