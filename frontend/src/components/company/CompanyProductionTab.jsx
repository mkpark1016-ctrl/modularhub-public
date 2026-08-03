import { useCallback, useState } from "react";
import {
  detailModel,
  fallbackProductionCapacityLabel,
  formatDate,
  formatNumber,
  labelValue,
  productionModelLabel,
} from "./companyDetailHelpers";
import { buildCompanyItemEvidence } from "../../companyEvidence";
import CompanyEntityDrawer from "./CompanyEntityDrawer";

function formatArea(value, unit = "m2") {
  if (value === null || value === undefined || value === "") return "확인되지 않음";
  return `${formatNumber(value)} ${unit || "m2"}`;
}

function productionTargets(facility) {
  return (facility.production_scope || []).map((item) => labelValue(item, item)).join(", ") || "확인되지 않음";
}

function FacilityDetail({ company, facility, productionSummary, onShowEvidence }) {
  const capacity = fallbackProductionCapacityLabel(facility);
  const confirmedItems = [
    ["상세 주소", facility.address],
    ["부지면적", formatArea(facility.site_area ?? facility.site_area_m2, facility.site_area_unit || "m2")],
    ["건축면적", formatArea(facility.building_area ?? facility.building_area_m2, facility.building_area_unit || "m2")],
    ["생산능력", capacity],
    ["생산 대상", productionTargets(facility)],
    ["주요 공정", (facility.production_processes || []).map((item) => labelValue(item, item)).join(", ")],
    ["근거 기준", facility.verification_basis_label || labelValue(facility.capacity_basis)],
    ["기준일", formatDate(facility.verified_at || productionSummary.verified_at)],
    ["신뢰도", labelValue(facility.data_confidence || facility.confidence || productionSummary.data_confidence)],
  ].filter(([, value]) => value && value !== "확인되지 않음" && value !== "세부정보 보완 필요");
  const missingItems = [
    !facility.address && "상세 주소",
    !facility.site_area && !facility.site_area_m2 && "부지면적",
    !facility.building_area && !facility.building_area_m2 && "건축면적",
    !(facility.production_processes || []).length && "주요 공정",
    !facility.notes && "비고",
  ].filter(Boolean);
  return (
    <>
    <dl className="detail-grid compact-detail-grid facility-detail-grid">
      {confirmedItems.map(([label, value]) => (
        <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
      ))}
      {facility.notes && <div><dt>비고</dt><dd>{facility.notes}</dd></div>}
      {onShowEvidence && (
        <div>
          <dt>근거</dt>
          <dd>
            <button
              type="button"
              className="text-button evidence-inline-button"
              onClick={() => onShowEvidence(buildCompanyItemEvidence(company, facility.display_name || facility.facility_name || "생산시설", capacity, facility.source_ids, facility.verification_basis_label))}
            >
              근거보기
            </button>
          </dd>
        </div>
      )}
    </dl>
    {missingItems.length > 0 && (
      <div className="company-empty-state compact-gap-state">
        <strong>추가 확인 필요</strong>
        <p>{missingItems.join(", ")} 정보는 공개자료에서 확인되지 않았습니다.</p>
      </div>
    )}
    </>
  );
}

export default function CompanyProductionTab({ company, onShowEvidence }) {
  const model = detailModel(company);
  const { production, productionSummary } = model;
  const [selectedFacility, setSelectedFacility] = useState(null);
  const openEvidence = useCallback((facility, value) => {
    if (!onShowEvidence) return;
    const evidence = buildCompanyItemEvidence(
      company,
      facility.display_name || facility.facility_name || "생산시설",
      value,
      facility.source_ids,
      facility.verification_basis_label,
    );
    setSelectedFacility(null);
    window.setTimeout(() => onShowEvidence(evidence), 0);
  }, [company, onShowEvidence, setSelectedFacility]);

  return (
    <section className="summary company-tab-panel" id="company-tab-panel-production" role="tabpanel" aria-labelledby="company-tab-production">
      <h2>생산시설</h2>
      <p className="finance-note">
        생산 운영 방식: {productionModelLabel(company)}
        {" · "}
        검증 상태: {labelValue(productionSummary.verification_status)}
      </p>
      {production.length ? (
        <>
        <div className="company-table-wrap responsive-table-wrap">
          <table className="company-financial-table company-production-table">
            <thead>
              <tr>
                <th>시설명</th>
                <th>지역</th>
                <th>운영 상태</th>
                <th>소유 관계</th>
                <th>규모 또는 생산능력</th>
                <th>생산 대상</th>
                <th>상세</th>
              </tr>
            </thead>
            <tbody>
              {production.map((facility) => {
                const capacity = fallbackProductionCapacityLabel(facility);
                const isTargetCapacity = facility.capacity_status === "derived" || facility.operation_status === "planned";
                return (
                  <tr key={facility.facility_id || facility.facility_name}>
                    <th>{facility.display_name || facility.facility_name || "시설명 확인 중"}</th>
                    <td>{facility.region || facility.city || facility.location || "확인되지 않음"}</td>
                    <td>{labelValue(facility.operation_status)}</td>
                    <td>{labelValue(facility.ownership_type)}</td>
                    <td>{isTargetCapacity ? <><span className="mini-status-badge">목표</span> {capacity}</> : capacity}</td>
                    <td>{productionTargets(facility)}</td>
                    <td>
                      <button type="button" className="text-button entity-detail-button" onClick={() => setSelectedFacility(facility)}>
                        상세보기
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="responsive-card-list facility-card-list">
          {production.map((facility) => {
            const capacity = fallbackProductionCapacityLabel(facility);
            const isTargetCapacity = facility.capacity_status === "derived" || facility.operation_status === "planned";
            return (
              <article className="responsive-data-card" key={`card-${facility.facility_id || facility.facility_name}`}>
                <div className="responsive-card-heading">
                  <strong>{facility.display_name || facility.facility_name || "시설명 확인 중"}</strong>
                  <span className="mini-status-badge">{labelValue(facility.operation_status)}</span>
                </div>
                <dl>
                  <div><dt>지역</dt><dd>{facility.region || facility.city || facility.location || "확인되지 않음"}</dd></div>
                  <div><dt>소유 관계</dt><dd>{labelValue(facility.ownership_type)}</dd></div>
                  <div><dt>규모 또는 생산능력</dt><dd>{isTargetCapacity ? `목표 ${capacity}` : capacity}</dd></div>
                  <div><dt>생산 대상</dt><dd>{productionTargets(facility)}</dd></div>
                </dl>
                <button type="button" className="text-button entity-detail-button" onClick={() => setSelectedFacility(facility)}>
                  상세보기
                </button>
              </article>
            );
          })}
        </div>
        </>
      ) : (
        <p>
          {productionSummary.verification_status === "not_applicable"
            ? "이 기업은 생산시설 비교 대상이 아닙니다."
            : "현재 공개자료에서 검증된 생산시설 정보를 확인하지 못했습니다."}
        </p>
      )}
      <CompanyEntityDrawer
        eyebrow="PRODUCTION FACILITY"
        title={selectedFacility?.display_name || selectedFacility?.facility_name || "생산시설 상세정보"}
        subtitle={selectedFacility ? `${labelValue(selectedFacility.operation_status)} · ${labelValue(selectedFacility.ownership_type)}` : ""}
        open={Boolean(selectedFacility)}
        onClose={() => setSelectedFacility(null)}
      >
        {selectedFacility && (
          <FacilityDetail
            company={company}
            facility={selectedFacility}
            productionSummary={productionSummary}
            onShowEvidence={() => openEvidence(selectedFacility, fallbackProductionCapacityLabel(selectedFacility))}
          />
        )}
      </CompanyEntityDrawer>
    </section>
  );
}
