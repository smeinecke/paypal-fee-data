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
  - Textual schedule references (`_resolve_reference`) are resolved by matching
    the referenced product family and, when there are multiple candidates, by
    the source rule's `variant_id` and `conditions`. The source market is only
    injected when a candidate explicitly lists that market, so generic target
    rules still match when no market-specific rule exists.
  - APM method extraction is token-based (`_extract_apm_methods`). Add new
    method token sets to `_APM_METHOD_MATCHERS`, region tokens for bank-transfer
    variants, and generic header phrases/tokens to `_APM_HEADER_PHRASES` /
    `_APM_HEADER_TOKENS` to suppress noise from variant-only rows.

## Current data status

After the latest regeneration the dataset is:

- 183 complete, 2 partial, 15 unclassified
- 3,379 core fee rules across all countries
- 0 classifier diagnostics
- 1 unsupported country

The remaining unclassified and partial markets are usually locales where a
standard commercial rate table is absent or rates are embedded in a
market-specific hero or prose section.
