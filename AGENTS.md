# PayPal Fee Data — Agent Notes

This repository contains the generated schema-v4 PayPal merchant fee data and
the `crawler/` submodule that produces it.

## Key commands

- Run crawler tests: `cd crawler && uv run pytest tests/ -q`
- Regenerate all country data: `cd crawler && uv run python -m paypal_fee_crawler.cli crawl --output .. --max-workers 3 --request-delay 0.5 --no-fail-on-regression --allow-country-drop`
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
  - Dangling schedule references are cleared (set to `None`) when neither the
    requested product-specific schedule nor the general `commercial` schedule
    exists.

## Current data status

After the latest regeneration the dataset is:

- 195 complete, 4 partial, 1 unclassified
- 1,618 core fee rules across all countries
- 1 unsupported country

The remaining unclassified market is typically `US` (page layout differs from the
CMS table-based structure). The few partial markets are usually locales where a
standard commercial rate table is absent and rates are embedded in a
market-specific hero or prose section.
