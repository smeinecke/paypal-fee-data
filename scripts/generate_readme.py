#!/usr/bin/env python3
"""Refresh the PayPal fee data README with live statistics."""

from __future__ import annotations

import contextlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

STATS_START = "<!-- STATS_START -->"
STATS_END = "<!-- STATS_END -->"


def _load_json(path: Path) -> dict | list:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _format_dt(value: str | None) -> str:
    if not value:
        return "—"
    with contextlib.suppress(Exception):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    return value


def _derive_stats(data_dir: Path) -> dict:
    index = _load_json(data_dir / "json" / "index.json")
    core_fees = _load_json(data_dir / "json" / "core-fees.json")
    countries_meta = _load_json(data_dir / "meta" / "countries.json")
    unsupported = _load_json(data_dir / "meta" / "unsupported-countries.json")

    countries = index.get("countries", [])
    total_countries = len(countries)
    status_counts: dict[str, int] = {}
    for country in countries:
        status = country.get("derived_status") or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1

    rule_count = 0
    rule_categories: set[str] = set()
    for country in core_fees.get("countries", []):
        derived = country.get("derived", {})
        transaction_rules = derived.get("transaction_fee_rules") or []
        rule_count += len(transaction_rules)
        for rule in transaction_rules:
            rule_categories.add(rule.get("id", "unknown"))
        if derived.get("fixed_fee_schedules"):
            rule_categories.add("fixed_fee_schedules")
        if derived.get("international_surcharge_schedules"):
            rule_categories.add("international_surcharge_schedules")
        if derived.get("currency_conversion"):
            rule_count += 1
            rule_categories.add("currency_conversion")

    regions: set[str] = set()
    for market in countries_meta.get("markets", []):
        region = market.get("region")
        if region:
            regions.add(region)

    latest_update = None
    for country in countries:
        updated = country.get("source_updated_at") or country.get("generated_at")
        if updated:
            with contextlib.suppress(Exception):
                candidate = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                if latest_update is None or candidate > latest_update:
                    latest_update = candidate

    generated_at = index.get("generated_at") or core_fees.get("generated_at")
    if generated_at and latest_update is None:
        with contextlib.suppress(Exception):
            latest_update = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))

    unsupported_count = 0
    if isinstance(unsupported, dict):
        unsupported_count = len(unsupported.get("unsupported", []))
    elif isinstance(unsupported, list):
        unsupported_count = len(unsupported)

    return {
        "total_countries": total_countries,
        "status_counts": status_counts,
        "total_rules": rule_count,
        "rule_categories": sorted(rule_categories),
        "regions": sorted(regions),
        "unsupported_count": unsupported_count,
        "latest_update": latest_update,
    }


def _render_stats(stats: dict) -> str:
    status_order = ["complete", "partial", "unclassified", "failed"]
    status_parts = []
    for status in status_order:
        count = stats["status_counts"].get(status, 0)
        if count:
            status_parts.append(f"{count} {status}")
    for status, count in sorted(stats["status_counts"].items()):
        if status not in status_order:
            status_parts.append(f"{count} {status}")
    status_str = ", ".join(status_parts) if status_parts else "—"

    lines = [
        "| Metric | Value |",
        "|--------|------:|",
        f"| Countries | **{stats['total_countries']}** |",
        f"| Derivation status | {status_str} |",
        f"| Core fee rules | **{stats['total_rules']:,}** |",
        f"| Rule categories | {', '.join(stats['rule_categories']) or '—'} |",
        f"| Regions | {len(stats['regions'])} ({', '.join(stats['regions']) or '—'}) |",
        f"| Unsupported countries | {stats['unsupported_count']} |",
        f"| Last crawled | {_format_dt(stats['latest_update'].isoformat().replace('+00:00', 'Z') if stats['latest_update'] else None)} |",
        "",
    ]
    return "\n".join(lines)


def _replace_section(content: str, start_marker: str, end_marker: str, body: str) -> str:
    pattern = re.compile(re.escape(start_marker) + r".*?" + re.escape(end_marker), re.DOTALL)
    replacement = f"{start_marker}\n{body}{end_marker}"
    if pattern.search(content):
        return pattern.sub(replacement, content)
    print(f"WARNING: markers '{start_marker}' / '{end_marker}' not found", file=sys.stderr)
    return content


def main() -> int:
    data_dir = Path(__file__).parent.parent
    readme_path = data_dir / "README.md"
    if not readme_path.exists():
        print(f"ERROR: README not found: {readme_path}", file=sys.stderr)
        return 1

    stats = _derive_stats(data_dir)
    body = _render_stats(stats)

    content = readme_path.read_text(encoding="utf-8")
    content = _replace_section(content, STATS_START, STATS_END, body)
    readme_path.write_text(content, encoding="utf-8")
    print(f"README updated: {readme_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
