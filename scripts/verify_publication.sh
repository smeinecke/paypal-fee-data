#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

cd crawler
uv run paypal-fee-crawler validate .. --strict
cd ..

submodule_rev="$(git -C crawler rev-parse HEAD)"
metadata_rev="$(python3 -c 'import json; print(json.load(open("meta/crawler-revision.json"))["crawler_revision"])')"

if [ "$submodule_rev" != "$metadata_rev" ]; then
  echo "Crawler revision mismatch: submodule=$submodule_rev metadata=$metadata_rev" >&2
  exit 1
fi

echo "Crawler revision matches: $metadata_rev"
