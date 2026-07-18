#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# 1. crawler submodule exists and is initialized
if ! git -C crawler rev-parse HEAD >/dev/null 2>&1; then
  echo "crawler submodule is not initialized" >&2
  exit 1
fi

# 2. required generated artifacts exist
required_files=(
  README.md
  change-report.json
  json/index.json
  json/core-fees.json
  meta/countries.json
  meta/crawl-report.json
  meta/crawler-revision.json
  meta/schema-version.json
  meta/transient-failures.json
  meta/unsupported-countries.json
  schemas/manifest-v1.schema.json
  schemas/paypal-fees-v1.schema.json
  schemas/core-fees-v1.schema.json
  schemas/index-v1.schema.json
)
for f in "${required_files[@]}"; do
  if [[ ! -e "$f" ]]; then
    echo "Required generated artifact missing: $f" >&2
    exit 1
  fi
done

# 3. strict validation + publication-tree completeness
(
  cd crawler
  uv run paypal-fee-crawler validate .. --strict --require-all-complete
)

# 4. crawler revision metadata equals submodule HEAD
submodule_rev="$(git -C crawler rev-parse HEAD)"
metadata_rev="$(python3 -c 'import json; print(json.load(open("meta/crawler-revision.json"))["crawler_revision"])')"
if [[ "$submodule_rev" != "$metadata_rev" ]]; then
  echo "Crawler revision mismatch: submodule=$submodule_rev metadata=$metadata_rev" >&2
  exit 1
fi

# 5. change-report.json is valid and has_regression is exactly false
python3 - <<'PY'
import json
from pathlib import Path

path = Path("change-report.json")
if not path.exists():
    raise SystemExit("change-report.json is missing")
try:
    report = json.loads(path.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    raise SystemExit(f"change-report.json is malformed: {exc}")
if not isinstance(report, dict):
    raise SystemExit("change-report.json must be an object")
if "has_regression" not in report:
    raise SystemExit("change-report.json is missing has_regression")
if report.get("has_regression") is not False:
    raise SystemExit(f"change-report.json has_regression must be exactly False, got {report['has_regression']!r}")
PY

# 6. meta/crawl-report.json is valid and reports success
python3 - <<'PY'
import json
from pathlib import Path

path = Path("meta/crawl-report.json")
if not path.exists():
    raise SystemExit("meta/crawl-report.json is missing")
try:
    report = json.loads(path.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    raise SystemExit(f"meta/crawl-report.json is malformed: {exc}")
if not isinstance(report, dict):
    raise SystemExit("meta/crawl-report.json must be an object")
if report.get("exit_code") != 0:
    raise SystemExit(f"meta/crawl-report.json exit_code is not 0: {report.get('exit_code')}")
PY

# 7. README metrics match generated artifacts
python3 - <<'PY'
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
import generate_readme

stats = generate_readme._derive_stats(Path("."))
rendered = generate_readme._render_stats(stats)
content = Path("README.md").read_text(encoding="utf-8")
match = re.search(r"<!-- STATS_START -->\n(.*?)<!-- STATS_END -->", content, re.DOTALL)
if not match:
    raise SystemExit("README.md does not contain STATS markers")
if match.group(1).strip() != rendered.strip():
    raise SystemExit("README.md metrics do not match generated artifacts")
PY

echo "Publication verification passed (crawler revision $metadata_rev)."
