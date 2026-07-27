export const SOURCE_STATUS_LABELS = {
  success: "정상",
  success_no_matches: "정상 · 현재 대상 없음",
  not_collected: "미수집",
  disabled_stopped: "중지",
  warning: "확인 필요",
  failed: "오류",
  unknown: "확인 필요",
};

export const SOURCE_SEVERITY_LABELS = {
  success: "정상",
  limited: "일부 제한",
  notice: "미수집",
  warning: "확인 필요",
  error: "오류",
};

function normalizeStatus(status) {
  const normalized = String(status || "").toLowerCase();
  if (!normalized) return "unknown";
  if (normalized === "success") return "success";
  if (normalized === "success_no_matches" || normalized === "success_no_public_match") return "success_no_matches";
  if (normalized === "not_collected") return "not_collected";
  if (normalized.includes("disabled") || normalized.includes("stopped")) return "disabled_stopped";
  if (normalized.includes("failed") || normalized.includes("error")) return "failed";
  if (normalized.includes("warning")) return "warning";
  return "unknown";
}

export function mapSourceStatus(status, { description = "" } = {}) {
  const normalized = normalizeStatus(status);
  if (normalized === "success") {
    return { status: normalized, label: SOURCE_STATUS_LABELS.success, severity: "success", description };
  }
  if (normalized === "success_no_matches") {
    return { status: normalized, label: SOURCE_STATUS_LABELS.success_no_matches, severity: "success", description };
  }
  if (normalized === "not_collected") {
    return { status: normalized, label: SOURCE_STATUS_LABELS.not_collected, severity: "notice", description: description || "수집 기록 없음" };
  }
  if (normalized === "disabled_stopped") {
    return { status: normalized, label: SOURCE_STATUS_LABELS.disabled_stopped, severity: "limited", description: description || "의도적으로 중지된 수집원" };
  }
  if (normalized === "failed") {
    return { status: normalized, label: SOURCE_STATUS_LABELS.failed, severity: "error", description };
  }
  return { status: normalized, label: SOURCE_STATUS_LABELS.warning, severity: "warning", description };
}

function newsSourceDescription(source = {}) {
  const parts = [];
  if (source.latest_item_published_at) parts.push(`최신 기사 ${source.latest_item_published_at}`);
  if (Number.isFinite(Number(source.fetched_count))) parts.push(`수집 ${Number(source.fetched_count).toLocaleString("ko-KR")}건`);
  if (Number.isFinite(Number(source.accepted_count))) parts.push(`공개 반영 ${Number(source.accepted_count).toLocaleString("ko-KR")}건`);
  if (Number(source.duplicate_count || 0) > 0) parts.push(`중복 ${Number(source.duplicate_count).toLocaleString("ko-KR")}건`);
  if (source.http_status) parts.push(`HTTP ${source.http_status}`);
  if (source.safe_error_category && source.safe_error_category !== "none") parts.push(source.safe_error_category);
  return parts.join(" · ");
}

function dynamicNewsSources(meta = {}) {
  if (!Array.isArray(meta.news_source_statuses)) return [];
  return meta.news_source_statuses.map((source) => ({
    id: source.id || source.source_name,
    name: source.name || source.source_name || "뉴스 수집원",
    ...mapSourceStatus(source.state, {
      description: newsSourceDescription(source),
    }),
    latestItemPublishedAt: source.latest_item_published_at || "",
    fetchedCount: Number(source.fetched_count || 0),
    acceptedCount: Number(source.accepted_count || 0),
    duplicateCount: Number(source.duplicate_count || 0),
  }));
}

function normalizeCompanyChangeStatus(state) {
  const normalized = String(state || "").toLowerCase();
  if (normalized === "success_empty_valid" || normalized === "success_empty") return "success_no_matches";
  if (normalized === "success_with_candidates" || normalized === "healthy") return "success";
  if (normalized.includes("missing") || normalized.includes("warning")) return "warning";
  if (normalized.includes("failed") || normalized.includes("error") || normalized.includes("not_configured")) return "failed";
  return normalized || "unknown";
}

function companyChangeSourceDescription(source = {}) {
  const parts = [];
  if (source.source_type) parts.push(source.source_type);
  if (source.last_run_at) parts.push(`마지막 실행 ${source.last_run_at}`);
  if (Number.isFinite(Number(source.accepted_count))) parts.push(`반영 ${Number(source.accepted_count).toLocaleString("ko-KR")}건`);
  if (Number.isFinite(Number(source.filtered_count))) parts.push(`검토 제외 ${Number(source.filtered_count).toLocaleString("ko-KR")}건`);
  if (source.simple_status) parts.push(source.simple_status);
  return parts.join(" · ");
}

function dynamicCompanyChangeSources(meta = {}) {
  if (!Array.isArray(meta.company_change_source_statuses)) return [];
  return meta.company_change_source_statuses.map((source) => ({
    id: `company-change-${source.id || source.source_id || source.name}`,
    name: source.name || source.collector_name || source.source_id || "기업 변화 감지",
    ...mapSourceStatus(normalizeCompanyChangeStatus(source.state), {
      description: companyChangeSourceDescription(source),
    }),
    latestItemPublishedAt: source.latest_item_published_at || source.last_run_at || "",
    fetchedCount: Number(source.fetched_count || 0),
    acceptedCount: Number(source.accepted_count || 0),
    duplicateCount: Number(source.duplicate_count || 0),
  }));
}

function activeCollectorFailed(meta = {}) {
  const statuses = [
    meta.g2b_order_plan_status,
    meta.procurement_plan_collection_status,
    meta.lh_contest_status,
    meta.gh_contest_status,
    meta.ih_contest_status,
    meta.sh_contest_status,
    meta.public_data_guard_status,
  ].map(normalizeStatus);
  return statuses.some((status) => status === "failed" || status === "warning");
}

function workflowStatus(meta = {}) {
  const normalized = normalizeStatus(meta.workflow_last_run_status || "success");
  const d2bStopped = normalizeStatus(meta.d2b_status || meta.d2b_legacy_status) === "disabled_stopped" || meta.d2b_gw_migration_required === true;
  if (normalized === "warning" && d2bStopped && !activeCollectorFailed(meta)) {
    return {
      status: "warning",
      label: "일부 제한",
      severity: "limited",
      description: "주요 수집원은 정상이며 D2B 기존 API만 중지 상태",
    };
  }
  return mapSourceStatus(normalized, {
    description: meta.public_data_guard_message || `마지막 갱신 ${meta.last_updated_at || meta.generated_at || "-"}`,
  });
}

export function getSourceHealth(meta = {}) {
  const newsSources = dynamicNewsSources(meta);
  const companyChangeSources = dynamicCompanyChangeSources(meta);
  const d2b = mapSourceStatus(meta.d2b_status || meta.d2b_legacy_status || "disabled_stopped", {
    description: meta.d2b_gw_migration_required ? "GW API 전환 필요" : (meta.d2b_message || "비활성화"),
  });
  const sh = mapSourceStatus(meta.sh_contest_status, {
    description: meta.sh_contest_message || (meta.sh_contest_status === "not_collected" ? "수집 기록 없음" : ""),
  });
  const workflow = workflowStatus(meta);
  return [
    {
      id: "g2b",
      name: "나라장터",
      ...mapSourceStatus(meta.g2b_order_plan_status || meta.procurement_plan_collection_status, {
        description: meta.g2b_order_plan_message || "입찰·발주계획 수집 상태",
      }),
    },
    { id: "d2b", name: "D2B", ...d2b },
    { id: "lh", name: "LH", ...mapSourceStatus(meta.lh_contest_status, { description: meta.lh_contest_message || "" }) },
    { id: "gh", name: "GH", ...mapSourceStatus(meta.gh_contest_status, { description: meta.gh_contest_message || "" }) },
    { id: "ih", name: "iH", ...mapSourceStatus(meta.ih_contest_status, { description: meta.ih_contest_message || "" }) },
    { id: "sh", name: "SH", ...sh },
    ...(newsSources.length
      ? newsSources
      : [{
        id: "rss",
        name: "해외 RSS",
        ...mapSourceStatus("success", { description: "해외 모듈러 RSS 수집 정상" }),
      }]),
    ...companyChangeSources,
    {
      id: "workflow",
      name: "전체 Workflow",
      ...workflow,
      description: workflow.description || `마지막 갱신 ${meta.last_updated_at || meta.generated_at || "-"}`,
    },
  ];
}

export function getSourceHealthSummary(sources = [], meta = {}) {
  const collectors = sources.filter((source) => source.id !== "workflow");
  return {
    successCount: collectors.filter((source) => source.severity === "success").length,
    limitedCount: collectors.filter((source) => source.severity === "limited").length,
    notCollectedCount: collectors.filter((source) => source.severity === "notice").length,
    issueCount: collectors.filter((source) => source.severity === "warning" || source.severity === "error").length,
    lastUpdatedAt: meta.last_updated_at || meta.generated_at || "",
    workflow: sources.find((source) => source.id === "workflow") || null,
  };
}
