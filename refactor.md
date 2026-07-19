# Refactoring & Optimization Plan

Scope: the `crawler/` submodule (`paypal_fee_crawler`, ~14,800 lines src) plus repo-level
`scripts/`. Goal: reduce complexity, remove confirmed-dead code, restructure oversized
modules, and optimize the hot path — **without removing any currently used feature**.

All output data (`json/`, `meta/`, `schemas/`) must stay byte-identical after every phase
(verified via `change-report.json` / `_country_output_hash`), and the full test suite
(202 tests) must pass unchanged.

---

## Current state (measured)

| Metric | Value |
|---|---|
| Largest file | `classify.py` — **7,276 lines** (~2,500 of them pure data tables) |
| radon average complexity | C (15.36) |
| D-rated functions | 10 (6 in `classify.py`, 2 in `output.py`, 1 each in `validation.py`, `pricing_tokens.py`) |
| Public API of `classify.py` | 1 function (`classify_tables`); 18 private helpers imported by tests, 1 by `validation.py` |
| Import graph | **Acyclic** — `classify` depends only on `models`, `normalize`, `pricing_tokens` |
| Entry points | `cli.py:main` (console script), `scripts/seed_from_fixtures.py` (ad-hoc) |

The clean, acyclic import graph and the tiny external API of `classify.py` make the
structural split (Phase 3) **feasible and low-risk**.

---

## Phase 1 — Delete confirmed-dead code (no behavior change)

All items verified unreferenced across `src/`, `tests/`, `scripts/`:

- [x] `classify.py`: `_row_text` (1035), `_first_money_text` (1094), `_extract_all_money` (1102).
- [x] `comparison.py`: entire module is a legacy no-op stub. `compare_against_gold` /
      `compare_classifiers` have zero references; `compare_runs` / `ComparisonResult` are
      referenced only by a test asserting the stub returns empty
      (`tests/test_classify_unit.py:254-255`). Delete module + that test. The docstring's
      claim that CLI promotion logic imports it is false — `cli.py` does not.
- [x] `market_mapping.py`: `MarketIdentity` class (37–66), `PAYPAL_SPECIFIC_MARKETS` (26),
      `safe_filename` (107), `is_safe_filename` (98), `_UNSAFE_PATH_RE` (34). Filenames are
      built from `market.url_slug` everywhere; this whole subsystem is unused. Keep
      `normalize_paypal_market_code`, `iso_country_code_for`, `PAYPAL_MARKET_TO_ISO`.
- [x] `pricing_tokens.py`: `is_numeric_amount` (226), `parse_amount` (231).
- [x] `models.py`: `ChangeKind` enum (789–796, zero references).
- [x] `output.py`: `publish(shadow_runs=...)` parameter and the `classification-shadow.json`
      branch (453–457) — no caller ever passes it. Same for the `diagnostics` parameter's
      classifier-version derivation in `_build_state_entry` (166–176). Drop the unused
      `outputs` param of `_run_generated_at` (155).
- [x] `validation.py`: gutted `if ...: pass` branch in `_validate_currency_codes` (44–51).

**Decision needed (deprecated-but-wired, do NOT silently delete):**

- `CrawlConfiguration.timeout` + CLI `--timeout`: validated but **never consumed** — the
  HTTP client uses `connect_timeout`/`read_timeout`. AGENTS.md even documents
  `--timeout 20`. Recommend **wiring it** (map to read/connect timeouts) rather than
  removing, since users pass it today.
- `CrawlConfiguration.atomic` + `--atomic/--no-atomic` and `refresh_country_manifest`:
  set from CLI, never read. Recommend either wiring or deprecating with a warning; keep
  the flags parseable so existing invocations don't break.
- `models.ClassifierMode` + `classifier_mode` field: kept "for config parsing compat";
  keep the field accepted but drop the dead enum plumbing once confirmed no config files
  set it.
- `CoverageSummary.inherited_schedules`: documented as deprecated duplicate of
  `inherited_schedule_references` — part of the published schema, so keep until a schema
  version bump.

Verification: `make all` (ruff, pyright, bandit, radon, vulture, xenon, pytest) + a full
`crawl` against cached fixtures produces an empty change report.

---

## Phase 2 — Mechanical extraction inside `classify.py` (no behavior change)

- [x] Extract the **~450-line inline `mapping` dict** from `_schedule_name_from_table`
      (3906–4368) to a module constant. The 462-line function becomes ~15 lines.
- [x] Hoist the four large keyword tuples built on **every call** of
      `_classify_table_category` (`fixed_fee_keywords` 1544, `min_max_fee_keywords` 1587,
      `direct_fixed_fee_keywords` 1641, `international_surcharge_keywords` 1665) to module
      constants. (Also a perf win — see Phase 5.)
- [x] Flatten the 4 nested functions inside `_resolve_schedule_inheritance` (6208–6426)
      to module-level helpers.

---

## Phase 3 — Split `classify.py` into a package (structural)

Feasibility confirmed: acyclic imports, single production consumer (`classify_tables`),
18 test-imported private names re-exportable from `__init__.py` → **zero import churn**
for tests, `validation.py`, `crawler.py`, and `seed_from_fixtures.py`.

Target layout `paypal_fee_crawler/classify/`:

| Module | Content (current line ranges) | ~Size |
|---|---|---|
| `patterns.py` | All pure data: `_PRODUCT_ALIASES` (47–394), category keywords/negative signals (396–1003), APM aliases + language token sets (1883–2472), `_*_VARIANTS` tables (2696–3172), schedule-name mapping (from Phase 2), `_REGION_PATTERNS` (4826–4965), schedule/inheritance maps (5769–5894) | ~2,500 |
| `text_utils.py` | `_norm`, `_table_text`, `_row_label`, money/percentage extractors (1004–1397) | ~400 |
| `products.py` | Product + table-category classification (1399–1873) | ~475 |
| `apm.py` | APM tokenization/extraction + label predicates (2472–2695) | ~220 |
| `variants.py` | `_variant_for_*`, `_VARIANT_DISPATCH`, `_variant_id_for_row` (3173–3397) | ~225 |
| `conditions.py` | `_conditions_for_*`, `_extract_amount_condition` (3398–3905) | ~510 |
| `schedules.py` | Signature/id helpers, schedule extraction/merge/inheritance (4369–4825, 5895–6522) | ~1,080 |
| `references.py` | Reference detection/resolution (4966–5252) | ~290 |
| `rules.py` | `_ExtractedRule`, rate-table rule extraction (5253–5768) | ~515 |
| `__init__.py` | `classify_tables` orchestration (7072–7276) + status/dedup/coverage (6523–7066) + **re-exports** of `classify_tables`, `_fee_components_for_rule`, and the 18 test-imported helpers | ~750 |

Rules:
- Re-export every externally imported name from `paypal_fee_crawler.classify` so
  `from paypal_fee_crawler.classify import X` keeps working everywhere.
- Move in dependency order (patterns → text_utils → leaf logic → orchestrator), running
  `pytest -q` after each move.

Result: no file over ~1,100 lines; the monolith becomes a data module + focused logic
modules of 200–600 lines.

## Phase 3b — Consolidate duplicated skeletons in classify

- [x] **`_variant_for_*` family** (16 functions, 3193–3362): 7–8 are one-liners of the form
      `_first_variant_match(field, RULES) or default`. Drive those from a
      `{product: (field, rules, default)}` table with one generic function; keep the
      complex ones as functions in the same dispatch. Constraint: keep
      `_variant_for_withdrawals` as a callable with its current signature (test-imported).
- [x] **Parallel schedule lookups**: `_fixed_fee_schedule_for` (5806) and
      `_international_surcharge_schedule_for` (5818) are near-identical over mirrored
      table triples (`_*_SCHEDULE_FOR` / `_*_INHERITANCE` / `_*_FALLBACK`) — one
      parameterized lookup over a `{schedule_type: tables}` map.
- [x] **Keyword matching**: `_first_variant_match`, `_all_variant_matches`,
      `_matches_region_pattern`, and ad-hoc `any(kw in text)` loops all reimplement
      "any keyword hits this text" — unify on one matcher (also enables Phase 5 #4).

Estimated net logic-line reduction from Phases 2–3b: **~120–170 lines**; the real win is
`classify.py` shrinking ~65% into navigable modules.

---

## Phase 4 — Cross-module dedup & centralization (rest of crawler)

- [x] **`models.py` MarketCodeMixin**: the validator pair
      `_validate_paypal_market_code`/`_validate_iso_country_code` + `country_code`
      property (+ `_migrate_legacy`) is copy-pasted across 5 models (`Market`,
      `PublicMarket`, `CountryIndexEntry`, `UnsupportedCountry`, `PublicCoreFeeEntry`).
      Extract one mixin. Same for the `_validate_origin` duplicate in the two schedule
      models.
- [x] **Move `_country_output_hash`** out of `regression.py` into a shared
      `hashing.py`/`serialize.py` util — `output.py` and `validation.py` currently import
      a private symbol from an unrelated module.
- [x] **Single source of truth for managed paths**: `output.MANAGED_PATHS` vs
      `validation._MANAGED_ROOTS` are the same set defined twice.
- [x] **`constants.py`**: PayPal base URL, fee-page path template, host allowlist,
      default discovery URL (currently spread over `discovery.py`, `crawler.py:91`,
      `models.py`, `http.py`, `seed_from_fixtures.py`); classifier metadata literal
      `("rules", "rules-v1")` (built 4×).
- [x] **Currency/decimal ownership**: move `CURRENCY_CODES`, `_normalize_decimal`,
      `_to_canonical_string` from `pricing_tokens.py` into `normalize.py` (or
      `currencies.py`) and invert the import; reuse `clean_text` in
      `render_rich_text_node` instead of the inline duplicate.
- [x] **Regression-kind severity**: `models._CHANGE_SEVERITY_BY_KIND` vs the hardcoded
      allowlist in `regression.enforce_regression` define "which kinds are regressions"
      twice (and the latter lists a never-emitted `removed_table`). Derive one from the
      other.
- [x] **`cli.py` shared options**: extract composite Click decorators for the cache
      option block and the http option block, each currently copy-pasted across 3
      commands; collapse the `_build_config` 20-arg mirroring.
- [x] **`crawler.py` 9-tuple**: replace `_extract_page_content`'s 9-value return with a
      small `PageContent` dataclass.
- [x] **`components.py`**: extract the repeated "check node, then its content/fields
      wrapper" iteration (~5 sites); parameterize `_extract_numbered_headers` vs
      `_extract_numbered_cells` (same routine, different kind/model); consolidate the 3
      table-merge sites.
- [x] **`pricing_tokens.py`**: collapse the 3 identical `_render_*_child` renderers;
      replace the inline embedded-type set at 476 with `_EMBEDDED_TYPES`; dedupe the
      operator-mapping and window-scan logic in `_parse_number_token`/`tokenize_text`.
- [x] **`validation.py`**: one `_schema_errors(model, data)` helper for the 5 repeated
      try/except ValidationError blocks; one `_generate_schema(model, filename)` for the
      4 identical generators; stop double-applying strict/require-all-complete checks
      (per-file and again in `validate_output_tree`).
- [x] **`regression.py`**: `_safe_load(path, loader)` for the six identical `_load_*`
      skeletons.
- [x] **`cms_context.py` / `html_tables.py` / `http.py`**: factor the shared
      parse-scripts generator (3 functions re-parse the same HTML); parse the page once
      in `crawler._extract_page_content` and pass the tree to
      `extract_html_tables`/`extract_html_pdf_url`/`extract_html_locale` (currently 3
      parses); merge the 3 independent `html.fromstring` calls in blocking-page
      detection into one signal-extraction pass.
- [x] **`discovery.py`**: factor the near-identical `_try_candidates` /
      `_try_homepage_links` loops; reuse `components.iter_components` for the 3
      hand-rolled recursive dict walkers.
- [x] **`seed_from_fixtures.py`**: stop duplicating `crawler.py`'s
      publish/change-report orchestration — expose a reusable method on `Crawler` and
      call it.

Split candidates beyond classify (optional, lower priority): `components.py`
(traversal vs table-building vs merging), `output.py` (publish/serialize vs
commit/journal/rollback). Both are cohesive enough to defer.

---

## Phase 5 — Performance optimizations

Hot path: `classify_tables` per country (~200) × tables × rows.

**High impact**

1. **Precompute normalized product aliases.** `_classify_product` calls `_norm(alias)`
   for all ~316 static aliases on *every call*, and it runs per row (twice per row via
   `_resolve_product_id` and `_classify_table_by_row_labels`). Build a module-level
   pre-normalized alias table once. Single largest waste in the classifier.
2. **Unblock the event loop.** `classify_tables` runs synchronously inside the async
   crawl coroutine (`crawler.py:488`), serializing all CPU classification and stalling
   concurrent fetches regardless of `--max-workers`. Minimum fix:
   `await asyncio.to_thread(...)`; for real CPU parallelism use a
   `ProcessPoolExecutor` via `run_in_executor`.

**Medium impact**

3. **Classify each table's category once.** `_classify_table_category` is recomputed for
   the same table at 3 sites (6151, 7087, 7229) and rebuilds its keyword tuples per call
   (fixed by Phase 2). Cache category per table in `classify_tables`.
4. **Pre-normalize static keyword tables at import** (`_TABLE_CATEGORY_KEYWORDS` ~289
   keywords normalized per table in `_select_category_from_scores`; same pattern at
   1829, 1869, 4364, 5036). Combine fixed keyword groups into one precompiled
   alternation regex instead of per-keyword `re.escape`+`re.search` in
   `_keyword_in_text`.
5. **Compute per-row derived values once.** In the row loop (5678–5708),
   `_extract_apm_methods(label)` runs at least twice, `_is_limit_or_cap_row` runs twice
   with identical args, and multiple predicates each re-`_norm` the same label. Compute
   `label_norm` + APM methods once and thread through.

**Low impact / opportunistic**

6. Precompile the hottest inline regexes (`classify.py:1218, 2479, 2536`) to module
   level, matching the existing `_APM_SEPARATOR_RE` style.
7. Drop redundant `_norm()` on already-normalized table text
   (`_is_maximum_fee_table` 1492, `_is_withdrawals_rate_table` 1504).
8. `output._list_changed_files`: compare `st_size` (or existing content hashes) before
   full `read_text()` equality over ~400 file reads at publish time.
9. `http_cache` sync file I/O inside async fetch → `asyncio.to_thread` for consistency.

**Quick win:** `@functools.lru_cache(maxsize=100_000)` on `_norm` captures much of #1/#4/#5
in one line — acceptable stopgap, but the module-level precompute is the proper fix.

Benchmark before/after: time a full `crawl` from warm HTTP cache (pure classify+publish
cost) and record in the PR.

---

## Repo-level scripts

`scripts/generate_readme.py`, `verify_publication.sh`, `verify_workflows.py` are small
and single-purpose — no action needed.

---

## Execution order & safety net

| Phase | Risk | Gate |
|---|---|---|
| 1 dead code | Low | `make all` + empty change report on regen |
| 2 mechanical extraction | Low | same |
| 5.1/5.3–5.7 classify perf | Low–Med | same + benchmark; output must be byte-identical |
| 3 classify package split | Medium | `pytest -q` after each module move; imports re-exported |
| 3b skeleton consolidation | Medium | unit tests per family; keep test-imported signatures |
| 4 cross-module dedup | Medium | `make all`; schema files unchanged |
| 5.2 async offload | Medium | full crawl comparison run |

Non-negotiable invariants:
- `paypal-fee-crawler crawl/validate/diff/inspect/discover-countries/crawl-country` CLIs
  keep accepting all current flags.
- `from paypal_fee_crawler.classify import <anything currently imported>` keeps working.
- Published output (`json/`, `meta/`, `schemas/`, `change-report.json`) stays
  byte-identical for identical inputs.
- No deprecated-but-published schema field is removed (e.g.
  `CoverageSummary.inherited_schedules`).
