# PayPal Fee Classifier Hardening Plan

## Objective

Migrate the classifier in `paypal-fee-crawler` from order-dependent, keyword-heavy first-match rules to a fail-closed structural-scoring architecture.

The revised classifier will use:

- language-independent table structure;
- embedded token metadata;
- table and reference relationships;
- exact market and region matching;
- an optional manually reviewed fingerprint registry;
- deterministic ambiguity handling;
- shadow comparison against the legacy classifier.

The `paypal-fee-data` repository remains the generated-output consumer.

---

## Design principles

1. **Fail closed**

   A missing or ambiguous classification is preferable to a confident but incorrect result.

2. **Structure before language**

   Table shape, token types, metadata, and relationships carry more weight than captions, headings, or translated keywords.

3. **Comparable category scoring**

   Every fee category uses the same score range and evidence allocation so scores can be ranked meaningfully.

4. **Explicit ambiguity**

   A category is selected only when it:

   - has no structural blockers;
   - exceeds the minimum score;
   - beats the runner-up by the minimum margin.

5. **Separate published output from shadow diagnostics**

   While the legacy classifier remains authoritative, structural-classifier scores and differences must not be mixed into the published `DerivedFees` object.

6. **Stable machine-readable evidence**

   Evidence, blockers, and observations use typed codes rather than relying only on free-form messages.

7. **Incremental rollout**

   Scoring, shadow orchestration, extraction changes, context preservation, and fingerprint promotion are delivered separately.

---

## Assumptions

- `paypal-fee-crawler` is the implementation repository.
- `paypal-fee-data` remains a generated-output repository.
- The existing `market_code` plumbing is preserved.
- `classify_tables` gains an optional `locale` parameter.
- Public output schemas remain unchanged during shadow rollout.
- Synthetic edge cases and real reviewed fixtures are maintained separately.
- A normalized table is treated as having one core fee-table role unless corpus analysis proves multi-label classification is necessary.
- Cross-market consensus is not available inside a single-country classification call and therefore belongs to the corpus/fingerprint phase.

---

# PR 1A — Structural scoring core

## Scope

Introduce the new scoring engine without changing published output or extraction behavior.

## Scoring model

Replace the four order-dependent `_is_*` predicates in `src/paypal_fee_crawler/classify.py` with category-specific scoring functions:

- `score_standard_commercial`
- `score_fixed_fee`
- `score_international_surcharge`
- `score_conversion`

Each function returns a `ScoreResult`.

```python
from dataclasses import dataclass
from enum import StrEnum


class EvidenceSource(StrEnum):
    STRUCTURAL = "structural"
    METADATA = "metadata"
    RELATIONSHIP = "relationship"
    REGISTRY = "registry"
    LEXICAL = "lexical"


class EvidenceCode(StrEnum):
    HAS_PERCENTAGE_COLUMN = "has_percentage_column"
    HAS_MONEY_COLUMN = "has_money_column"
    HAS_MIXED_PERCENT_MONEY_ROW = "has_mixed_percent_money_row"
    HAS_MULTIPLE_CURRENCIES = "has_multiple_currencies"
    HAS_ADDITIVE_PERCENTAGES = "has_additive_percentages"
    METADATA_KEY_MATCH = "metadata_key_match"
    INTERNAL_NAME_MATCH = "internal_name_match"
    KNOWN_DOCUMENT_ID = "known_document_id"
    KNOWN_FINGERPRINT = "known_fingerprint"
    REFERENCE_CONTEXT_MATCH = "reference_context_match"
    POSITIVE_LEXICAL_HINT = "positive_lexical_hint"
    NEGATIVE_LEXICAL_HINT = "negative_lexical_hint"


class BlockerCode(StrEnum):
    ONLY_PERCENTAGES_FOR_FIXED_FEE = "only_percentages_for_fixed_fee"
    ONLY_MONEY_FOR_PERCENTAGE_CATEGORY = "only_money_for_percentage_category"
    NO_USABLE_VALUES = "no_usable_values"
    INCOMPATIBLE_COLUMN_SHAPE = "incompatible_column_shape"


@dataclass(frozen=True)
class EvidenceSignal:
    code: EvidenceCode
    source: EvidenceSource
    weight: int
    detail: str | None = None


@dataclass(frozen=True)
class ScoreResult:
    category: FeeCategory
    score: int
    signals: tuple[EvidenceSignal, ...]
    blockers: tuple[BlockerCode, ...]

    @property
    def eligible(self) -> bool:
        return not self.blockers
```

## Shared score scale

All categories use a `0–100` scale.

Suggested allocation:

| Evidence class | Maximum |
|---|---:|
| Structural evidence | 50 |
| Token metadata | 20 |
| Relationships or registry | 20 |
| Lexical context | 10 |
| **Total** | **100** |

Initial thresholds:

```python
MAX_CATEGORY_SCORE = 100
MINIMUM_SCORE = 60
MINIMUM_MARGIN = 15
```

These values should be constants and covered by tests.

The score is an evidence score, not a probability.

## Classification decision

Score all categories before selecting a result.

```python
@dataclass(frozen=True)
class ClassificationDecision:
    status: Literal["selected", "ambiguous", "unclassified"]
    selected_category: FeeCategory | None
    ranked_scores: tuple[ScoreResult, ...]
    ambiguity_reason: str | None
    winner_margin: int | None
```

Selection rules:

1. Rank all category scores.
2. Reject categories with structural blockers.
3. Select the winner only when:
   - it is eligible;
   - its score is at least `MINIMUM_SCORE`;
   - its score exceeds the runner-up by at least `MINIMUM_MARGIN`.
4. Otherwise return `ambiguous` or `unclassified`.

Do not return the first matching category.

## Keyword behavior

Retain existing positive and negative keyword lists temporarily, but:

- assign them low weights;
- never let a keyword alone establish structural validity;
- treat negative keywords as score reductions rather than automatic vetoes;
- reserve hard rejection for genuine structural contradictions.

## Exact market and region matching

Preserve the existing `market_code` argument and add `locale`.

```python
classify_tables(
    tables,
    market_code=market.paypal_market_code,
    locale=page_locale or market.locale,
)
```

Replace unrestricted substring matching with normalized token matching.

Keep aliases and grouped regions separate:

```python
MARKET_ALIASES = {
    "GB": frozenset({"gb", "uk"}),
}

REGION_GROUPS = {
    "US_CA": frozenset({"us", "usa", "ca", "canada"}),
}
```

Requirements:

- use Unicode-aware token boundaries;
- normalize punctuation and whitespace;
- prevent short market codes from matching inside ordinary words;
- do not treat independent markets such as `US` and `CA` as aliases;
- test canonical codes, aliases, grouped regions, and false positives.

## Category exclusivity

Document the initial invariant:

> A physical normalized table has one core fee-table role.

Add corpus assertions for this assumption.

A table containing a standard percentage and an inline fixed amount must still be classified as a standard-commercial table, not as a fixed-fee currency lookup table.

If corpus analysis finds legitimate multi-role tables, replace the invariant with explicit multi-label support rather than relying on score order.

## Tests

Expand `tests/test_classification.py` to cover:

- all four category score vectors;
- score normalization;
- minimum-score rejection;
- minimum-margin ambiguity;
- structural blockers;
- misleading positive keywords;
- misleading negative keywords;
- changed `FEETB*` IDs;
- exact market-code matching;
- market codes inside ordinary words;
- aliases versus grouped regions;
- category exclusivity;
- deterministic score ordering.

## Non-goals

PR 1A must not:

- modify public `DerivedFees`;
- change extracted fee values;
- change country JSON output;
- add a runtime shadow flag;
- add the fingerprint registry;
- add cross-market consensus.

---

# PR 1B — Shadow orchestration and offline comparison

## Scope

Run the legacy and structural classifiers in parallel while keeping the legacy output authoritative.

## Explicit classifier mode

Use an enum instead of a Boolean.

```python
class ClassifierMode(StrEnum):
    LEGACY = "legacy"
    SHADOW = "shadow"
    STRUCTURAL = "structural"
```

```python
class CrawlConfiguration(BaseModel):
    classifier_mode: ClassifierMode = ClassifierMode.LEGACY
```

Expose the mode through the CLI and test configuration parsing.

## Separate classifier entry points

Create explicit functions:

```python
classify_legacy(...)
classify_structural(...)
```

Both return a common internal result.

```python
@dataclass(frozen=True)
class ClassificationRun:
    derived: DerivedFees
    table_decisions: tuple[ClassificationDecision, ...]
    observations: tuple["ClassificationObservation", ...]
    classifier_version: str
```

Shadow behavior:

```python
legacy_run = classify_legacy(...)
structural_run = classify_structural(...)

published_derived = legacy_run.derived
shadow_comparison = compare_classifier_runs(
    legacy_run,
    structural_run,
)
```

Do not place structural scores or ambiguity metadata into the legacy-derived `DerivedFees`.

## Observations versus cross-run changes

Represent same-run findings separately from historical or legacy-versus-structural changes.

```python
class ObservationKind(StrEnum):
    LOW_MARGIN = "low_margin"
    LEXICAL_ONLY_DECISION = "lexical_only_decision"
    EXTRACTION_CONFLICT = "extraction_conflict"
    UNKNOWN_DOCUMENT_ID = "unknown_document_id"
    UNKNOWN_FINGERPRINT = "unknown_fingerprint"


class ClassificationObservation(BaseModel):
    kind: ObservationKind
    category: FeeCategory | None = None
    table_id: str | None = None
    message: str
```

Cross-run differences remain change records:

```python
class ChangeKind(StrEnum):
    CLASSIFICATION_CHANGED = "classification_changed"
    NEW_DOCUMENT_ID = "new_document_id"
    PUBLISHED_VALUE_CHANGED = "published_value_changed"
```

Add one severity source of truth:

```python
class ChangeSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    REGRESSION = "regression"
```

Each change record carries its severity. Both `has_regression` and regression enforcement derive from that field rather than separate hard-coded string sets.

## Shadow diagnostics output

Publish diagnostics separately from country output, for example:

```text
meta/classification-shadow.json
```

or as a dedicated section of `change-report.json`.

Include:

- legacy category;
- structural category;
- ranked structural scores;
- winner margin;
- ambiguity reason;
- evidence codes;
- blocker codes;
- legacy versus structural extraction differences;
- classifier versions.

The file should be deterministic and stable for diff review.

## Offline corpus comparison

Do not rely only on live crawling because unchanged pages may return `304 Not Modified`.

Add a command such as:

```bash
paypal-fee-crawler compare-classifiers ../paypal-fee-data/json
```

The command must:

1. load each existing `CountryOutput`;
2. classify its stored normalized tables with both engines;
3. compare selected categories;
4. compare extracted values;
5. aggregate observations;
6. write a deterministic report;
7. never rewrite country output.

Suggested outputs:

```text
classification-comparison.json
classification-comparison.md
```

## Tests

Add tests for:

- all three classifier modes;
- legacy output remaining authoritative in shadow mode;
- no structural diagnostics leaking into `DerivedFees`;
- deterministic comparison reports;
- severity-based regression enforcement;
- corpus comparison against a small fixture directory;
- empty and malformed corpus inputs;
- classifier version fields.

## Files likely touched

- `src/paypal_fee_crawler/classify.py`
- `src/paypal_fee_crawler/crawler.py`
- `src/paypal_fee_crawler/models.py`
- `src/paypal_fee_crawler/regression.py`
- `src/paypal_fee_crawler/cli.py`
- `src/paypal_fee_crawler/output.py`
- `tests/test_classification.py`
- `tests/test_regression.py`
- `tests/test_cli.py`

---

# PR 1C — Schema-driven extraction hardening

## Scope

Refactor extraction after structural classification can be compared safely against the legacy behavior.

Extraction returns typed decisions and observations rather than silently choosing a plausible value.

## Shared extraction result

```python
@dataclass(frozen=True)
class ExtractionDecision[T]:
    value: T | None
    selected_rows: tuple[int, ...]
    evidence: tuple[EvidenceSignal, ...]
    observations: tuple[ClassificationObservation, ...]
```

## Standard commercial percentage

Selection priority:

1. a coherent row containing both a percentage and a fixed monetary component;
2. a percentage row linked to an approved fixed-fee table;
3. a structurally coherent percentage-only row;
4. lexical row evidence;
5. otherwise ambiguous.

Do not use broad labels such as the following as decisive selectors:

- `all`
- `other`
- `card`
- `payment`

These may contribute low-weight context only.

A mixed percentage-and-money row is strong evidence but must not be mandatory because some pages reference a separate fixed-fee table.

## Fixed-fee extraction

Evaluate candidate data rows rather than requiring every row to contain one money token.

```python
for row in profile.data_rows:
    money_tokens = accepted_money_tokens(row)

    if not money_tokens:
        continue

    if len(money_tokens) != 1:
        report_ambiguous_row(row)
        continue
```

Requirements:

- derive currency from the money token where available;
- otherwise accept a separately validated currency-label cell;
- deduplicate identical `(currency, amount)` pairs;
- report conflicting values for the same currency;
- reject or downgrade the extraction when valid candidate coverage is insufficient;
- ignore notes, separators, and footers that contain no accepted money token.

## International surcharge extraction

Infer column roles before reading values.

```python
@dataclass(frozen=True)
class ColumnRoleAssignment:
    label_column: int | None
    percentage_columns: tuple[int, ...]
    money_columns: tuple[int, ...]
    confidence: int
```

Extraction steps:

1. identify percentage-bearing columns;
2. identify the likely region-label column;
3. resolve exact market, alias, or region-group matches;
4. select values only from the assigned percentage column;
5. report rows with multiple candidate percentages;
6. avoid taking the first percentage token found anywhere in the row.

## Conversion-spread extraction

Remove the “most common percentage” fallback.

For the first structural release, conversion extraction must be supported by at least one of:

- recognized token metadata;
- an approved fingerprint;
- a known document ID with compatible structure;
- an unambiguous conversion-specific relationship.

Otherwise return no value and emit an ambiguity observation.

## Differential extraction report

For every corpus item, compare:

- legacy extracted values;
- structural extracted values;
- missing values;
- newly found values;
- conflicting values;
- selected table IDs;
- selected row indexes.

No structural extraction becomes authoritative until differences are reviewed.

## Tests

Add extraction tests for:

- mixed percentage-plus-fixed rows;
- separate fixed-fee references;
- percentage-only commercial rows;
- duplicate monetary values;
- conflicting values per currency;
- note and footer rows;
- multiple percentage columns;
- market codes inside labels and ordinary words;
- conversion tables with and without approved evidence;
- deterministic selected-row evidence.

---

# PR 2 — Structural profiles and preserved contexts

## Scope

Build reusable language-independent profiles and preserve every table occurrence and reference context.

## Profiles module

Add:

```text
src/paypal_fee_crawler/profiles.py
```

### Row profile

```python
@dataclass(frozen=True)
class RowProfile:
    row_index: int
    cell_count: int
    percentage_count: int
    money_count: int
    currencies: frozenset[str]
    additive_percentage_count: int
    fee_data_keys: frozenset[str]
    internal_names: frozenset[str]
    content_types: frozenset[str]
    token_kind_pattern: tuple[str, ...]
    is_probable_header: bool
    is_probable_note: bool
```

### Column profile

```python
@dataclass(frozen=True)
class ColumnProfile:
    column_index: int
    percentage_row_count: int
    money_row_count: int
    text_row_count: int
    currencies: frozenset[str]
    token_kind_pattern: tuple[str, ...]
```

### Table profile

```python
@dataclass(frozen=True)
class TableProfile:
    row_count: int
    column_count: int

    rows: tuple[RowProfile, ...]
    columns: tuple[ColumnProfile, ...]

    percentage_rows: frozenset[int]
    money_rows: frozenset[int]
    mixed_percentage_money_rows: frozenset[int]

    percentage_columns: frozenset[int]
    money_columns: frozenset[int]

    currencies: frozenset[str]
    additive_percentage_count: int

    fee_data_keys: frozenset[str]
    internal_names: frozenset[str]
    content_types: frozenset[str]

    document_id: str | None
    source_table_ids: tuple[str, ...]
    contexts: tuple["TableContext", ...]
```

Profile generation must be deterministic and side-effect free.

## Context model

Add:

```python
class TableContext(BaseModel):
    component_id: str | None = None
    caption: str | None = None
    section_path: list[str] = []
    parent_path: list[str] = []
    source_order: int
    reference_id: str | None = None
```

Every physical or referenced table occurrence gets a separate context.

## Component traversal

Update `components.py` to:

- maintain `parent_path` during recursive traversal;
- preserve the existing section hierarchy;
- record each `FeeTableReference` occurrence;
- attach reference caption, section path, parent path, source order, and reference ID;
- merge shared table content without discarding occurrence-specific context;
- avoid duplicate contexts when the same reference is encountered more than once identically.

## Internal versus public representation

Prefer keeping contexts internal during shadow rollout:

```python
@dataclass(frozen=True)
class NormalizedTableRecord:
    table: Table
    contexts: tuple[TableContext, ...]
```

Only add `contexts` directly to the serialized public `Table` model after the schema policy is explicit and the output change is accepted.

## HTML fallback

Populate one context for each HTML table using:

- nearest preceding heading;
- heading hierarchy;
- source order;
- no reference ID.

## Classifier integration

Rewrite structural scoring to consume `TableProfile` rather than rescanning raw table cells independently.

Evidence priority:

1. structural validity;
2. token metadata;
3. table and reference relationships;
4. approved registry evidence;
5. lexical context.

Cross-market consensus remains excluded until PR 3.

## Tests

Add `tests/test_profiles.py` covering:

- row and column token counts;
- mixed rows;
- additive percentages;
- currency extraction;
- metadata aggregation;
- deterministic profile output;
- note/header detection.

Add context tests covering:

- multiple references to one table;
- different captions for the same referenced table;
- different section paths;
- parent-path maintenance;
- duplicate reference suppression;
- HTML fallback context.

Add classifier tests that:

- blank captions and headers;
- replace headings with opaque strings;
- preserve classification when structure and metadata remain sufficient;
- become ambiguous when structure, metadata, and relationships are all removed.

---

# PR 3 — Fingerprint registry, reviewed corpus, and promotion

## Scope

Add reviewed structural fingerprints, cross-market analysis, mutation testing, and the promotion gate for making the structural classifier authoritative.

## Fingerprint registry

Add:

```text
src/paypal_fee_crawler/registry.py
src/paypal_fee_crawler/registries/classifier_clusters.json
```

Load registry resources through `importlib.resources`.

Ensure registry JSON is included in package data in `pyproject.toml`.

## Registry schema

```json
{
  "fingerprint_version": 1,
  "clusters": {
    "commercial-fixed-fees-v1": {
      "category": "fixed_fee",
      "document_ids": ["FEETB18", "FEETB306"],
      "fingerprints": ["sha256:..."],
      "required_features": [
        "money_column",
        "multiple_currencies"
      ],
      "reviewed_examples": ["DE", "GB"],
      "status": "approved"
    }
  }
}
```

Supported statuses:

- `candidate`
- `approved`
- `deprecated`
- `rejected`

Only approved clusters may provide positive classification evidence.

## Canonical fingerprint input

Generate fingerprints from canonical JSON, not string concatenation.

Include:

- token-kind matrix by column;
- normalized `fee_data_key` values;
- normalized `internal_name` values;
- normalized `content_type` values;
- currency-column pattern;
- percentage operators;
- additive-percentage pattern;
- component/reference relationships;
- coarse row-count bucket;
- coarse column-count bucket;
- mixed-row pattern.

Exclude:

- captions;
- translated text;
- headings;
- exact percentages;
- exact monetary amounts;
- fragile exact row counts;
- market-specific source order.

Document the fingerprint algorithm and version it independently.

## Document ID behavior

Document IDs are aliases for reviewed structural clusters, not sole classification truth.

Expected behavior:

- known ID plus compatible structure: positive evidence;
- known fingerprint plus new ID: recognize and report the new ID;
- known ID plus incompatible structure: block or heavily penalize;
- new ID plus new fingerprint: fail closed and emit review observation.

## Fingerprint tooling

Add:

```text
scripts/generate_fingerprints.py
```

or an equivalent CLI command.

Capabilities:

- load normalized tables from a corpus;
- calculate canonical fingerprints;
- group identical or near-identical structures;
- list document IDs by group;
- list markets and locales by group;
- output reviewable JSON and Markdown;
- never automatically approve a cluster;
- produce deterministic ordering.

## Fixture organization

Maintain two separate fixture sets:

```text
tests/fixtures/classification/synthetic/
tests/fixtures/classification/gold/
```

### Synthetic fixtures

Use for isolated behavior:

- misleading keywords;
- renamed headings;
- unknown IDs;
- malformed rows;
- duplicate values;
- exact market-code boundaries.

### Gold fixtures

Use minimized, manually reviewed examples sampled from real normalized country output.

Example:

```json
{
  "case_id": "de-commercial-standard-001",
  "source_market": "DE",
  "source_document_id": "FEETB16",
  "expected": {
    "category": "standard_commercial",
    "percentage": "2.99"
  },
  "table": {}
}
```

Provenance fields are for review and traceability only; they must not become accidental classifier inputs.

## Mutation tests

For each representative gold case, test mutations such as:

- replace captions and headers with opaque text;
- replace or remove `FEETB*` IDs;
- insert misleading positive keywords;
- insert misleading negative keywords;
- remove token metadata;
- reorder tables;
- reorder rows where semantics permit;
- duplicate table references;
- add a second percentage token to a row;
- add a second money token to a row;
- add notes and footers;
- place market codes inside ordinary words;
- vary punctuation and Unicode whitespace;
- add or remove currencies;
- change exact rates while preserving structure.

Expected behavior:

- structure-backed decisions survive lexical mutation;
- metadata-backed decisions survive document-ID changes;
- removal of all non-lexical evidence generally becomes ambiguous;
- contradictory structures fail closed;
- extraction conflicts are reported rather than silently resolved.

## Cross-market consensus

Build consensus offline from the corpus, not inside a single-country classification call.

Possible evidence:

- the same fingerprint is approved for one category across many markets;
- the same metadata key consistently maps to one category;
- a new document ID appears with an already approved fingerprint;
- one market is an outlier within an otherwise stable cluster.

Consensus output must be reviewable and must not automatically approve new clusters.

## Promotion gate

Before switching the default mode to `STRUCTURAL`, require:

- no unexplained high-severity classification changes;
- reviewed extraction differences;
- acceptable gold-set precision;
- acceptable corpus ambiguity rate;
- no lexical-only selected decisions unless explicitly allowlisted;
- no known-ID/incompatible-structure cases;
- deterministic output across repeated runs;
- `pytest`, `ruff`, and `pyright` passing.

Precision should be prioritized over recall.

## Promotion behavior

When structural mode becomes authoritative:

1. switch the default `ClassifierMode`;
2. retain legacy comparison for at least one release;
3. decide whether diagnostics belong in public output or only reports;
4. apply the explicit schema-version policy;
5. regenerate JSON schema and country outputs;
6. document migration and rollback steps.

---

# Public schema policy

Do not modify public country output during shadow mode.

Before adding fields such as:

- classification scores;
- ambiguity reasons;
- winner margins;
- table contexts;
- classifier version;

choose and document one policy:

## Option A — Additive version-1 policy

Optional additive fields do not require a schema-version increment.

Requirements:

- document the compatibility guarantee;
- test old readers against new output;
- keep existing fields stable;
- regenerate the version-1 schema deliberately.

## Option B — Strict schema versioning

Any serialized structural change requires schema version 2.

Requirements:

- create a new schema path;
- update `schema-version.json`;
- document migration;
- preserve version-1 artifacts where required.

Do not justify a silent schema change solely because the new fields are not yet used externally.

---

# Status semantics

Preserve the existing high-level status contract unless reviewed corpus evidence requires a change:

- `complete`: standard-commercial and fixed-fee values are confidently classified and extracted;
- `partial`: one or more exposed categories are missing or have extraction warnings;
- `unclassified`: required tables are ambiguous or structurally unsupported.

Low-margin selected decisions should generally not produce `complete`.

---

# Observability and diagnostics

Every structural decision should be explainable through stable fields:

```json
{
  "table_id": "FEETB18",
  "selected_category": "fixed_fee",
  "status": "selected",
  "winner_score": 84,
  "runner_up_score": 31,
  "winner_margin": 53,
  "signals": [
    {
      "code": "has_money_column",
      "source": "structural",
      "weight": 25
    },
    {
      "code": "has_multiple_currencies",
      "source": "structural",
      "weight": 15
    }
  ],
  "blockers": []
}
```

Diagnostics must support:

- deterministic diffs;
- machine filtering;
- manual review;
- aggregate corpus analysis;
- future threshold calibration.

Free-form messages may supplement typed fields but must not replace them.

---

# Validation strategy

Run after each PR:

```bash
pytest
ruff check .
pyright
```

Also run:

```bash
paypal-fee-crawler compare-classifiers ../paypal-fee-data/json
```

when the comparison command becomes available.

Required validation layers:

1. unit tests;
2. synthetic mutation tests;
3. manually reviewed gold fixtures;
4. full-corpus differential tests;
5. deterministic rerun tests;
6. packaging tests for the fingerprint registry;
7. schema compatibility tests when public models change.

---

# Revised file map

## Existing files

- `src/paypal_fee_crawler/classify.py`
- `src/paypal_fee_crawler/crawler.py`
- `src/paypal_fee_crawler/components.py`
- `src/paypal_fee_crawler/html_tables.py`
- `src/paypal_fee_crawler/models.py`
- `src/paypal_fee_crawler/regression.py`
- `src/paypal_fee_crawler/validation.py`
- `src/paypal_fee_crawler/output.py`
- `src/paypal_fee_crawler/cli.py`
- `pyproject.toml`
- `tests/test_classification.py`
- `tests/test_regression.py`
- `tests/test_cli.py`

## New files

- `src/paypal_fee_crawler/profiles.py`
- `src/paypal_fee_crawler/registry.py`
- `src/paypal_fee_crawler/registries/classifier_clusters.json`
- `tests/test_profiles.py`
- `tests/fixtures/classification/synthetic/`
- `tests/fixtures/classification/gold/`
- `scripts/generate_fingerprints.py`

---

# Definition of done

The migration is complete when:

- table categories are no longer selected by first-match rule order;
- all categories use comparable structural evidence scores;
- short market codes cannot match arbitrary substrings;
- aliases and grouped regions are modeled separately;
- ambiguous tables fail closed;
- legacy and structural outputs can be compared offline;
- shadow diagnostics do not contaminate published legacy results;
- extraction uses explicit row and column roles;
- reference occurrences retain their original context;
- fingerprints are versioned and manually reviewed;
- synthetic and real gold fixtures cover supported page families;
- corpus tests demonstrate higher robustness to wording and ID changes;
- the structural classifier meets the promotion gate and becomes authoritative through an explicit configuration change.
