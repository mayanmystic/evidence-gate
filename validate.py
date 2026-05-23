#!/usr/bin/env python3
"""
validate.py — Evidence Gate validation script.

Walks the cards directory structure and verifies:
  - frontmatter `status` matches the directory the card lives in
  - `id` follows CARD-YYYYMMDD-NNN-slug format (any namespace prefix allowed)
  - required body sections are present and non-empty for the card's status
  - `confidence_before` / `confidence_after` are valid floats in [0, 1]
  - dates parse as ISO YYYY-MM-DD
  - validated cards past `expiry_or_retest_date` are surfaced as warnings

Exits 0 if all cards pass, 1 if any error. No external dependencies.

Usage:
    python3 validate.py [--cards-root PATH] [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

DEFAULT_CARDS_ROOT = Path.home() / ".evidence-gate" / "cards"

VALID_STATUSES = {"candidate", "tested_once", "validated", "falsified", "retired"}
VALID_EVIDENCE_LEVELS = {"idea", "inference", "tested_once", "replicated", "validated", "falsified", "retired"}

# Required body sections by status (cumulative).
ALWAYS_REQUIRED = {"# Claim", "# Why we believe it", "# Scope"}
TESTED_REQUIRED = ALWAYS_REQUIRED | {"# Prediction", "# Test", "# Outcome"}
VALIDATED_REQUIRED = TESTED_REQUIRED | {"# Confidence update"}
FALSIFIED_REQUIRED = TESTED_REQUIRED  # outcome section explains the falsification

REQUIRED_BY_STATUS = {
    "candidate": ALWAYS_REQUIRED,
    "tested_once": TESTED_REQUIRED,
    "validated": VALIDATED_REQUIRED,
    "falsified": FALSIFIED_REQUIRED,
    "retired": ALWAYS_REQUIRED,
}

# ID pattern: optional namespace prefix, date, sequence number, slug
# Examples: CARD-20260101-001-my-claim, PRODUCT-20260101-001-my-claim, 20260101-001-my-claim
ID_RE = re.compile(r"^([A-Z]+-)?(\d{8})-(\d{3})-[a-z0-9-]+$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


@dataclass
class CardError:
    path: Path
    message: str


@dataclass
class CardWarning:
    path: Path
    message: str


@dataclass
class Report:
    errors: list[CardError] = field(default_factory=list)
    warnings: list[CardWarning] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=lambda: {s: 0 for s in VALID_STATUSES})
    items: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse YAML-style frontmatter. No external dependencies."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    fm_text = match.group(1)
    body = text[match.end():]
    fm: dict[str, str] = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm, body


def extract_sections(body: str) -> dict[str, str]:
    """Split body on H1 headings, return {heading: section_body}."""
    sections: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("# "):
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            current = line.rstrip()
            lines = []
        else:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines).strip()
    return sections


def parse_iso_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_confidence(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def validate_card(path: Path, expected_status: str, report: Report) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        report.errors.append(CardError(path, f"could not read: {e}"))
        return

    fm, body = parse_frontmatter(text)
    if not fm:
        report.errors.append(CardError(path, "missing or malformed YAML frontmatter"))
        return

    # ID validation
    card_id = fm.get("id", "")
    if not card_id:
        report.errors.append(CardError(path, "frontmatter missing `id`"))
    elif not ID_RE.match(card_id):
        report.errors.append(
            CardError(path, f"`id` must match [PREFIX-]YYYYMMDD-NNN-slug pattern: got {card_id!r}")
        )

    # Status must match directory
    status = fm.get("status", "")
    if status not in VALID_STATUSES:
        report.errors.append(
            CardError(path, f"`status` must be one of {sorted(VALID_STATUSES)}, got {status!r}")
        )
    elif status != expected_status:
        report.errors.append(
            CardError(path, f"directory says status={expected_status!r} but frontmatter says {status!r}")
        )

    if card_id:
        report.items.append({
            "id": card_id,
            "status": status or expected_status,
            "path": str(path),
            "title": fm.get("title", ""),
            "created": fm.get("created", ""),
            "domain": fm.get("domain", ""),
            "encounter_count": fm.get("encounter_count", "0"),
            "confidence_after": fm.get("confidence_after", ""),
            "expiry_or_retest_date": fm.get("expiry_or_retest_date", ""),
        })

    # Evidence level (optional, but must be valid if present)
    evidence_level = fm.get("evidence_level", "")
    if evidence_level and evidence_level not in VALID_EVIDENCE_LEVELS:
        report.errors.append(
            CardError(path, f"`evidence_level` must be one of {sorted(VALID_EVIDENCE_LEVELS)}, got {evidence_level!r}")
        )

    # Confidence values
    for field_name in ("confidence_before", "confidence_after"):
        raw = fm.get(field_name, "")
        val = parse_confidence(raw)
        if raw and val is None:
            report.errors.append(CardError(path, f"`{field_name}` is not a valid float: {raw!r}"))
        elif val is not None and not (0.0 <= val <= 1.0):
            report.errors.append(CardError(path, f"`{field_name}` out of range [0, 1]: {val}"))

    ca = parse_confidence(fm.get("confidence_after", ""))

    # Date fields
    for field_name in ("created", "last_reviewed", "expiry_or_retest_date"):
        raw = fm.get(field_name, "")
        if raw and parse_iso_date(raw) is None:
            report.errors.append(CardError(path, f"`{field_name}` not ISO YYYY-MM-DD: {raw!r}"))

    # Required body sections
    sections = extract_sections(body)
    required = REQUIRED_BY_STATUS.get(status, ALWAYS_REQUIRED)
    for heading in sorted(required):
        if heading not in sections:
            report.errors.append(CardError(path, f"missing required section: {heading}"))
        elif not sections[heading].strip():
            report.errors.append(CardError(path, f"required section `{heading}` is empty"))

    # Promotion gate: validated cards must have confidence_after
    if status == "validated" and ca is None:
        report.errors.append(
            CardError(path, "validated card missing `confidence_after` (required for promotion gate)")
        )

    # Expiry warning for validated cards past their retest date
    expiry = parse_iso_date(fm.get("expiry_or_retest_date", ""))
    if status == "validated" and expiry and expiry < date.today():
        report.warnings.append(
            CardWarning(path, f"past expiry date ({expiry.isoformat()}) — re-test or retire")
        )

    # Behavioral impact warning: validated cards that haven't been used
    if status == "validated" and not fm.get("behavioral_impact_last_seen", "").strip():
        report.warnings.append(
            CardWarning(path, "no `behavioral_impact_last_seen` date — was this belief ever used? Consider retiring.")
        )

    # Encounter threshold warning
    try:
        threshold = int(fm.get("retest_after_n_encounters", "3") or "3")
        count = int(fm.get("encounter_count", "0") or "0")
        if status in ("tested_once", "validated") and count >= threshold:
            report.warnings.append(
                CardWarning(
                    path,
                    f"encounter_count ({count}) >= retest threshold ({threshold}) — review and re-evaluate"
                )
            )
    except ValueError:
        pass

    # Falsification condition check (warn if missing on candidate cards)
    if status == "candidate":
        body_lower = body.lower()
        has_falsification = (
            "falsif" in body_lower
            or "falsification condition" in body_lower
            or "# proxy encounters" in body_lower
            or "explicit falsification" in body_lower
        )
        if not has_falsification:
            report.warnings.append(
                CardWarning(
                    path,
                    "candidate card has no falsification condition — add one before relying on this belief"
                )
            )


def validate_cards_root(cards_root: Path) -> Report:
    report = Report()
    if not cards_root.exists():
        report.errors.append(CardError(cards_root, f"cards root does not exist: {cards_root}"))
        return report

    for status in sorted(VALID_STATUSES):
        status_dir = cards_root / status
        if not status_dir.exists():
            continue
        for path in sorted(status_dir.glob("*.md")):
            report.counts[status] += 1
            validate_card(path, status, report)

    return report


def print_report(report: Report, cards_root: Path) -> None:
    total = sum(report.counts.values())
    print(f"Cards root: {cards_root}")
    print(f"Total cards: {total}")
    for status in sorted(VALID_STATUSES):
        if report.counts[status]:
            print(f"  {status}: {report.counts[status]}")
    print()

    if report.warnings:
        print(f"WARNINGS ({len(report.warnings)}):")
        for w in report.warnings:
            try:
                rel = w.path.relative_to(cards_root)
            except ValueError:
                rel = w.path
            print(f"  ⚠  {rel}: {w.message}")
        print()

    if report.errors:
        print(f"VALIDATION: FAIL ({len(report.errors)} errors)")
        for e in report.errors:
            try:
                rel = e.path.relative_to(cards_root)
            except ValueError:
                rel = e.path
            print(f"  ✗  {rel}: {e.message}")
        sys.exit(1)
    else:
        print("VALIDATION: PASS")


def report_to_json(report: Report, cards_root: Path) -> dict:
    def rel(path: Path) -> str:
        try:
            return str(path.relative_to(cards_root))
        except ValueError:
            return str(path)

    return {
        "ok": report.ok,
        "cards_root": str(cards_root),
        "total": sum(report.counts.values()),
        "counts": report.counts,
        "items": report.items,
        "warnings": [{"path": rel(w.path), "message": w.message} for w in report.warnings],
        "errors": [{"path": rel(e.path), "message": e.message} for e in report.errors],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate evidence-gate cards against the schema."
    )
    parser.add_argument(
        "--cards-root",
        type=Path,
        default=DEFAULT_CARDS_ROOT,
        help=f"Path to cards directory (default: {DEFAULT_CARDS_ROOT})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON report",
    )
    args = parser.parse_args()

    report = validate_cards_root(args.cards_root)
    if args.json:
        print(json.dumps(report_to_json(report, args.cards_root), ensure_ascii=False))
        return 0 if report.ok else 1
    else:
        print_report(report, args.cards_root)
        return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
