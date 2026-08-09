import publicCompanySupplements from "./data/publicCompanySupplements.json" with { type: "json" };

const COMPANY_DATA_PATH = "/data/companies/companies.json";

function requestUrl(input) {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input?.url || "";
}

function isCompanyDatasetRequest(input) {
  try {
    const url = new URL(requestUrl(input), window.location.origin);
    return url.pathname.endsWith(COMPANY_DATA_PATH);
  } catch {
    return false;
  }
}

export function appendSupplementalCompanies(payload) {
  const supplements = Array.isArray(publicCompanySupplements.companies)
    ? publicCompanySupplements.companies
    : [];
  if (Array.isArray(payload)) {
    const existingIds = new Set(payload.map((company) => company?.company_id).filter(Boolean));
    const missingSupplements = supplements.filter((company) => !existingIds.has(company?.company_id));
    if (!missingSupplements.length) return payload;
    return [...payload, ...missingSupplements];
  }

  if (!payload || typeof payload !== "object") return payload;
  const companies = Array.isArray(payload.companies) ? payload.companies : [];
  const existingIds = new Set(companies.map((company) => company?.company_id).filter(Boolean));
  const missingSupplements = supplements.filter((company) => !existingIds.has(company?.company_id));
  if (!missingSupplements.length) return payload;

  return {
    ...payload,
    description: `${payload.description || "ModularHub verified company universe"} Includes separately researched supplemental public company profiles.`,
    companies: [...companies, ...missingSupplements],
  };
}

if (typeof window !== "undefined") {
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const response = await originalFetch(input, init);
    if (!response.ok || !isCompanyDatasetRequest(input)) return response;

    try {
      const payload = await response.clone().json();
      const enrichedPayload = appendSupplementalCompanies(payload);
      if (enrichedPayload === payload) return response;

      const headers = new Headers(response.headers);
      headers.set("content-type", "application/json; charset=utf-8");
      headers.delete("content-length");
      headers.delete("content-encoding");

      return new Response(JSON.stringify(enrichedPayload), {
        status: response.status,
        statusText: response.statusText,
        headers,
      });
    } catch {
      return response;
    }
  };
}
