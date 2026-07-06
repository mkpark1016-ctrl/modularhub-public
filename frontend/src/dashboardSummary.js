export function buildDashboardSummary({ businessSummary = {}, newsSummary = {} }) {
  return {
    active: businessSummary.active ?? 0,
    dueWithin7: businessSummary.dueWithin7 ?? 0,
    recentlyPosted7: businessSummary.recentlyPosted7 ?? 0,
    important: businessSummary.important ?? 0,
    recentNews7: newsSummary.recent7 ?? 0,
    recentDirect7: newsSummary.recentDirect7 ?? 0,
    recentAdjacent7: newsSummary.recentAdjacent7 ?? 0,
  };
}
