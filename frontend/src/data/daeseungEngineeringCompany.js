import publicCompanySupplements from "./publicCompanySupplements.json" with { type: "json" };

export const DAESEUNG_ENGINEERING_COMPANY = publicCompanySupplements.companies.find(
  (company) => company.company_id === "daeseung-engineering",
);
