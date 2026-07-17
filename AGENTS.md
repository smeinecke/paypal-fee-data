# PayPal Fee Data — Agent Notes

This repository contains the generated schema-v4 PayPal merchant fee data and
the `crawler/` submodule that produces it.

## Key commands

- Run crawler tests: `cd crawler && uv run pytest tests/ -q`
- Regenerate all country data: `cd crawler && uv run paypal-fee-crawler crawl --output .. --max-workers 8 --timeout 20`
- Update README stats after regeneration: `cd .. && uv run python scripts/generate_readme.py`
- Validate structure and schemas: `cd crawler && uv run paypal-fee-crawler validate ..`
- Run strict publication-readiness checks: `cd crawler && uv run paypal-fee-crawler validate .. --strict`

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

## HTTP response cache

The crawler keeps a 24-hour on-disk HTTP cache under `.cache/paypal-fee-crawler/http/`
by default.  Cached responses are keyed by normalized URL, market, locale, relevant
content-negotiation headers, and a crawler-specific cache version.  Fresh entries are
returned directly; expired entries are revalidated with `If-None-Match`/`If-Modified-Since`.

CLI flags:

- `--cache-dir PATH` — cache directory (default: `.cache/paypal-fee-crawler/http/`).
- `--cache-ttl-hours HOURS` — entry TTL in hours (default: 24).
- `--no-cache` — bypass cache reads and writes.
- `--refresh-cache` — force network revalidation/update.

Environment variables `PAYPAL_FEE_CRAWLER_CACHE_DIR`, `PAYPAL_FEE_CRAWLER_CACHE_TTL_HOURS`,
`PAYPAL_FEE_CRAWLER_NO_CACHE`, and `PAYPAL_FEE_CRAWLER_REFRESH_CACHE` are also supported.
The `crawled_at` timestamp in generated output always reflects the current crawl, not the
cache timestamp, so cached data does not affect determinism.

## Validation modes

- `validate ..` checks schemas, cross-file consistency, and schedule references.
- `validate .. --strict` checks for blocking semantic defects: conflicting rule
  identities, dangling references, invalid calculable rules, unsupported fee
  shapes, and a clean `change-report.json`. Partial and unclassified markets are
  allowed because they still produce useful data.
- `validate .. --require-all-complete` rejects any partial or unclassified
  market, as well as diagnostics or unresolved fee candidates.

## Current data status

After the latest regeneration the dataset is:

- 125 complete, 60 partial, 15 unclassified
- 4,004 core fee rules across all countries
- 0 classifier diagnostics
- 2 unsupported countries
- `change-report.json`: no regressions (`has_regression: false`)

The remaining unclassified and partial markets are usually locales where a
standard commercial rate table is absent or rates are embedded in a
market-specific hero or prose section.
