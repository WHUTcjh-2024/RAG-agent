---
name: wardrobe-planning
version: 1.0.0
description: Reuse Java-owned wardrobe facts before recommending catalog additions.
allowed-tools:
  - wardrobe_get_snapshot
  - wardrobe_plan_outfits
  - catalog_search
---

# Wardrobe planning

1. Read the latest wardrobe snapshot first.
2. Preserve the returned wardrobe version when presenting or editing a plan.
3. Prefer existing items. Recommend only the categories the deterministic plan marks missing.
4. Keep budget and category constraints explicit; do not silently relax hard constraints.
5. Explain whether each item is from the wardrobe or catalog, and expose unresolved gaps.
