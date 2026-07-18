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
    if re.search(pattern, text):
        fail(f"{name}: forbidden pattern {pattern!r} found")


def check_present(pattern: str, text: str, name: str) -> None:
    if not re.search(pattern, text):
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


verify = (WORKFLOWS / "verify.yml").read_text(encoding="utf-8")
daily = (WORKFLOWS / "daily-crawl.yml").read_text(encoding="utf-8")

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
