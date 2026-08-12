---
name: purchase-decision
version: 1.0.0
description: Produce evidence-backed clothing purchase advice without inventing business facts.
allowed-tools:
  - catalog_search
  - catalog_get_product
  - decision_facts_get
  - wardrobe_get_snapshot
  - wardrobe_plan_outfits
  - try_on_create_preview
  - cart_prepare_add
---

# Purchase decision

1. Use `catalog_search` or `catalog_get_product` for candidate facts.
2. Use `decision_facts_get` for price, stock, SKU size, return policy and body
   facts. Only fields with Java-issued provenance may support a purchase claim.
3. Use `wardrobe_get_snapshot` before wardrobe compatibility claims. Do not infer
   an item the user owns.
4. State unknowns and request the minimum missing input instead of guessing.
5. `try_on_create_preview` is appearance-only, creates a synthetic model, and
   requires `user_confirmed: true`; never describe it as a fit guarantee.
6. `cart_prepare_add` is allowed only after an explicit user request and returns a
   confirmation token. It never changes the cart; Java confirms the final action.

Never place orders, pay, or claim that an unverified result is in stock.
