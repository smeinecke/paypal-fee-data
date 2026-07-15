# PayPal Fee Data — Agent Notes

This repository contains the generated schema-v4 PayPal merchant fee data and
the `crawler/` submodule that produces it.

## Key commands

- Run crawler tests: `cd crawler && uv run pytest tests/ -q`
- Regenerate all country data: `cd crawler && uv run paypal-fee-crawler crawl --output .. --max-workers 8 --timeout 20`
- Update README stats after regeneration: `cd .. && uv run python scripts/generate_readme.py`

## Output layout

The `crawl` command expects `--output` to be the **repository root** (`..`), not
`../json`. It writes/updates `json/`, `meta/`, `schemas/` and `change-report.json`
under the output root.

## Common classifier tuning points

- `crawler/src/paypal_fee_crawler/classify.py`:
  - `_TABLE_CATEGORY_KEYWORDS` for product-specific rate-table keywords.
  - `_PRODUCT_ALIASES` for product-name matching in row cells.
  - `fixed_fee_keywords` and `international_surcharge_keywords` for identifying
    fixed-fee and international surcharge tables.
  - Schedule references are explicit: `_FIXED_FEE_SCHEDULE_FOR` and
    `_INTERNATIONAL_SURCHARGE_SCHEDULE_FOR` declare which schedule each product
    uses, and `_*_INHERITANCE` maps declare where a schedule is inherited from
    another product family. Missing or inherited schedules are reported as
    diagnostics in `DerivedFeeResult.diagnostics`; there is no implicit fallback
    to a different schedule family.
  - APM method extraction is token-based (`_extract_apm_methods`). The German
    `alternative_payment_methods` special row is split into a `variant_id`
    `special` rule with `conditions.payment_methods` and a default `variant_id`
    `default` rule.

## Current data status

After the latest regeneration the dataset is:

- 1 complete, 184 partial, 15 unclassified
- 1,266 core fee rules across all countries
- 0 unsupported countries

The remaining unclassified and partial markets are usually locales where a
standard commercial rate table is absent or rates are embedded in a
market-specific hero or prose section.
