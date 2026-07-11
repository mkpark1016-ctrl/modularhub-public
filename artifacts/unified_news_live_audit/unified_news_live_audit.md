# Unified News Live Audit

- Final status: FAIL
- Public news generated_at: 2026-07-11T14:18:15+09:00
- Total news count: 1158
- Domestic pipeline count: 1105
- RSS overseas pipeline count: 53

## Unified-v2 Contract

- Score version mismatch: 0
- Relevance level missing: 0
- Relevance level invalid: 0
- Relevance score missing: 0
- Score range violation: 0
- Components missing: 0
- Reasons missing: 0
- Excluded public count: 27
- ID missing: 0
- ID duplicate: 0
- URL duplicate: 0
- Title/date duplicate: 7

## Score Distribution

### overall
- Count: 1158
- Min / P25 / Median / Average / P75 / Max: 0 / 40.0 / 45.0 / 49.17 / 55.0 / 95
- Levels: {'direct': 296, 'adjacent': 834, 'reference': 1, 'excluded': 27}
- Score bins: {'0_19': 27, '20_39': 228, '40_59': 620, '60_79': 193, '80_100': 90}

### domestic_pipeline
- Count: 1105
- Min / P25 / Median / Average / P75 / Max: 0 / 40.0 / 45 / 47.76 / 55.0 / 95
- Levels: {'direct': 244, 'adjacent': 833, 'reference': 1, 'excluded': 27}
- Score bins: {'0_19': 27, '20_39': 228, '40_59': 619, '60_79': 169, '80_100': 62}

### rss_overseas_pipeline
- Count: 53
- Min / P25 / Median / Average / P75 / Max: 45 / 70.0 / 80 / 78.49 / 85.0 / 95
- Levels: {'direct': 52, 'adjacent': 1, 'reference': 0, 'excluded': 0}
- Score bins: {'0_19': 0, '20_39': 0, '40_59': 1, '60_79': 24, '80_100': 28}

## Component Comparison

- Largest component difference: core (24.49)
- Average absolute differences: {'core': 24.49, 'business': 0.03, 'freshness': 6.09, 'completeness': 0.12}

## Region Audit

- RSS overseas pipeline with domestic publisher candidate: 5
- Domestic pipeline with overseas publisher candidate: 0
- Unknown publisher region count: 366

## Relevance Sort Top 50

- Level counts: {'direct': 50}
- Publisher region counts: {'unknown': 18, 'domestic': 31, 'overseas': 1}
- Adjacent before direct violations: 0
- Unnatural score/level count: 0
- Same issue duplicate count: 1
- Potential unrelated count: 0

## Collection Warnings

- known_important_bid_collection_failed: Does not change scoring for existing public news; may delay new bid visibility. Next: separate collector hotfix
- g2b_procurement_plan_collection_failed: Does not change scoring for existing public news; may reduce newly collected procurement-plan coverage. Next: separate procurement-plan hotfix
- partial_bid_or_news_collector_failure: Existing public JSON is preserved by cumulative export guards; newly available records may be missing. Next: inspect failing collector logs
- d2b_legacy_api_stopped: Known disabled source; not a relevance scoring issue. Next: separate D2B GW API migration
- node_action_runtime_deprecation: No effect on news scores or public JSON content. Next: workflow maintenance

## Recommendations

- Fix public export or collection policy so relevance_level=excluded items are not published.
- Add whole-news title/date duplicate normalization or review duplicate carry-over in cumulative public news.
- Audit RSS-sourced domestic publishers and plan a separate publisher_region display hotfix.
- Add explicit publisher-domain mappings for high-volume unknown publishers after manual review.
- Keep unified-v2 scoring unchanged until region-display behavior is fixed in a separate hotfix.
