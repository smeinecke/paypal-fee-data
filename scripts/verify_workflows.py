#!/usr/bin/env python3
"""Lightweight workflow hardening checks for paypal-fee-data."""

from __future__ import annotations

import re
import sys
from pathlib import Path

WORKFLOWS = Path(".github/workflows")
errors: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


def check_not_present(pattern: str, text: str, name: str) -> None:
    if re.search(pattern, text, re.MULTILINE):
        fail(f"{name}: forbidden pattern {pattern!r} found")


def check_present(pattern: str, text: str, name: str) -> None:
    if not re.search(pattern, text, re.MULTILINE):
        fail(f"{name}: required pattern {pattern!r} not found")


def check_sha_pinned(text: str, name: str) -> None:
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("uses:") and not re.match(r"^-\s+uses:\s+", stripped):
            continue
        spec = stripped.split("uses:", 1)[1].split("#")[0].strip()
        if "@" not in spec:
            continue
        _, ref = spec.rsplit("@", 1)
        if not re.fullmatch(r"[0-9a-fA-F]{40}", ref):
            fail(f"{name}:{lineno}: action {spec!r} is not pinned to a 40-character SHA")


def _base_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _parse_list_block(text: str, key: str) -> list[str] | None:
    pattern = re.compile(rf"^(\s*){re.escape(key)}:\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return None
    base = _base_indent(match.group(0))
    items: list[str] = []
    for line in text[match.end() :].splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = _base_indent(line)
        if indent <= base:
            break
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip().strip('"\''))
    return items


def _parse_dict_block(text: str, key: str) -> dict[str, str] | None:
    pattern = re.compile(rf"^(\s*){re.escape(key)}:\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return None
    base = _base_indent(match.group(0))
    items: dict[str, str] = {}
    for line in text[match.end() :].splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = _base_indent(line)
        if indent <= base:
            break
        stripped = line.strip()
        if stripped.startswith("-"):
            continue
        if ":" in stripped:
            k, v = stripped.split(":", 1)
            items[k.strip()] = v.strip().strip('"\'')
    return items


def _check_notify_workflow(notify_path: Path) -> None:
    if not notify_path.exists():
        fail("notify-ci-failure.yml is missing")
        return

    text = notify_path.read_text(encoding="utf-8")
    name = notify_path.name

    check_present(r"^name:\s*Notify CI Failure\s*$", text, name)

    monitored = _parse_list_block(text, "workflows")
    if monitored is None:
        fail(f"{name}: workflow_run.workflows list not found")
    else:
        expected = {"Daily Crawl", "Verify Publication"}
        if set(monitored) != expected:
            fail(f"{name}: workflow_run.workflows must be exactly {sorted(expected)}, got {monitored}")
        if "Notify CI Failure" in monitored:
            fail(f"{name}: workflow must not monitor itself")

    permissions = _parse_dict_block(text, "permissions")
    if permissions is None:
        fail(f"{name}: permissions block not found")
    else:
        expected_perms = {
            "contents": "read",
            "actions": "read",
            "issues": "write",
        }
        if set(permissions.keys()) != set(expected_perms.keys()):
            fail(f"{name}: permissions must contain exactly {sorted(expected_perms.keys())}, got {sorted(permissions.keys())}")
        for key, value in expected_perms.items():
            if permissions.get(key) != value:
                fail(f"{name}: permission {key!r} must be {value!r}, got {permissions.get(key)!r}")

    check_not_present(r"actions/checkout", text, name)
    check_not_present(r"actions/download-artifact", text, name)
    check_not_present(r"uses:\s*[^/\s]+/", text, name)

    check_present(r'gh\(\s*"issue",\s*"create"', text, name)
    check_present(r'gh\(\s*"issue",\s*"comment"', text, name)
    check_present(r'gh\(\s*"issue",\s*"edit"', text, name)
    check_present(r'"--state",\s*"closed"', text, name)
    check_present(r"smeinecke", text, name)
    check_present(r'conclusion == "success"', text, name)

    required_body_fields = [
        "Repository:",
        "Workflow:",
        "Conclusion:",
        "Branch:",
        "Commit SHA:",
        "Event:",
        "Run number:",
        "Run attempt:",
        "Actor:",
        "Started at:",
        "Updated at:",
        "Run URL:",
    ]
    for field in required_body_fields:
        if field not in text:
            fail(f"{name}: required issue body field {field!r} not found")


verify = (WORKFLOWS / "verify.yml").read_text(encoding="utf-8")
daily = (WORKFLOWS / "daily-crawl.yml").read_text(encoding="utf-8")

notify = WORKFLOWS / "notify-ci-failure.yml"
_check_notify_workflow(notify)

check_not_present(r"ref:\s*main", verify, "verify.yml")
check_not_present(r"EndBug/add-and-commit", daily, "daily-crawl.yml")
check_not_present(r"ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION", daily, "daily-crawl.yml")

check_present(r"concurrency:", daily, "daily-crawl.yml")
check_present(r"make all", verify, "verify.yml")
check_present(r"--require-all-complete", verify, "verify.yml")
check_present(r"--require-all-complete", daily, "daily-crawl.yml")
check_present(r"bash scripts/verify_publication\.sh", verify, "verify.yml")
check_present(r"bash scripts/verify_publication\.sh", daily, "daily-crawl.yml")

check_sha_pinned(verify, "verify.yml")
check_sha_pinned(daily, "daily-crawl.yml")

if errors:
    for error in errors:
        print(error, file=sys.stderr)
    sys.exit(1)

print("Workflow hardening checks passed.")
