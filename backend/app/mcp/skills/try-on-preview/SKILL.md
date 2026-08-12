---
name: try-on-preview
version: 1.0.0
description: Request privacy-safe synthetic-model try-on previews with explicit confirmation.
allowed-tools:
  - try_on_create_preview
  - catalog_get_product
---

# Try-on preview

1. Verify the product first.
2. Explain that the preview uses a synthetic adult model and is not a precise fit or fabric simulation.
3. Ask for explicit approval before creating a preview.
4. Supply a stable idempotency key so retries do not generate duplicate jobs.
5. Do not collect or send a person photo through this skill.
