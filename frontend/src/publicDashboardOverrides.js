import { DAESEUNG_ENGINEERING_COMPANY } from "./data/daeseungEngineeringCompany";

const COMPANY_DATA_PATH = "/data/companies/companies.json";
const HIDDEN_PUBLIC_ROUTE = "/company-intelligence";

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

function appendDaeseungCompany(payload) {
  if (Array.isArray(payload)) {
    if (payload.some((company) => company?.company_id === DAESEUNG_ENGINEERING_COMPANY.company_id)) return payload;
    return [...payload, DAESEUNG_ENGINEERING_COMPANY];
  }

  if (!payload || typeof payload !== "object") return payload;
  const companies = Array.isArray(payload.companies) ? payload.companies : [];
  if (companies.some((company) => company?.company_id === DAESEUNG_ENGINEERING_COMPANY.company_id)) return payload;

  return {
    ...payload,
    description: `${payload.description || "ModularHub verified company universe"} Includes the separately researched Daeseung Engineering profile.`,
    companies: [...companies, DAESEUNG_ENGINEERING_COMPANY],
  };
}

if (typeof window !== "undefined") {
  if (window.location.pathname === HIDDEN_PUBLIC_ROUTE || window.location.pathname.startsWith(`${HIDDEN_PUBLIC_ROUTE}/`)) {
    window.history.replaceState({}, "", "/not-found");
  }

  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const response = await originalFetch(input, init);
    if (!response.ok || !isCompanyDatasetRequest(input)) return response;

    try {
      const payload = await response.clone().json();
      const enrichedPayload = appendDaeseungCompany(payload);
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
