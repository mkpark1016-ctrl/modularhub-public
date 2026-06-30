export function matchesSourceType(item, selectedSourceType) {
  if (selectedSourceType === "all") return true;
  return item?.source_type === selectedSourceType;
}

export function matchesAgency(item, selectedAgency, getAgencyValue) {
  if (selectedAgency === "all") return true;
  return getAgencyValue(item) === selectedAgency;
}

export function matchesLifecycleStatus(item, selectedStatus, getStatus) {
  if (selectedStatus === "all") return true;
  return getStatus(item) === selectedStatus;
}

export function matchesBusinessFilters(item, filters, helpers) {
  return (
    matchesSourceType(item, filters.sourceType) &&
    matchesAgency(item, filters.agency, helpers.getAgencyValue) &&
    matchesLifecycleStatus(item, filters.status, helpers.getStatus)
  );
}
