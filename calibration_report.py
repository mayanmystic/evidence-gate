#!/usr/bin/env python3
"""
calibration-report.py — System-level confidence calibration tracker.

Reads all validated and falsified cards, groups by confidence_before band,
and computes: predicted confidence vs. observed accuracy. Flags systematic
over- or under-confidence at the system level.

Also reads predictions.jsonl (if present) for finer-grained tracking of
individual predictions beyond card-level outcomes.

Usage:
    python3 calibration-report.py [--cards-root PATH] [--json] [--brief]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

CARDS_ROOT = Path.home() / ".evidence-gate" / "cards"
PREDICTIONS_LOG = CARDS_ROOT.parent / "predictions.jsonl"
CALIBRATION_LOG = CARDS_ROOT.parent / "calibration-history.jsonl"
ACTION_LOG = CARDS_ROOT.parent / "action-outcomes.jsonl"

OUTCOME_STAGES = ("validated", "falsified")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

# Calibration bands: (low, high, label)
BANDS = [
    (0.0, 0.2,  "0–20%"),
    (0.2, 0.4,  "20–40%"),
    (0.4, 0.6,  "40–60%"),
    (0.6, 0.8,  "60–80%"),
    (0.8, 1.01, "80–100%"),
]

WELL_CALIBRATED_THRESHOLD = 0.15   # |predicted - actual| < 15% = well calibrated
CONCERNING_THRESHOLD = 0.25        # > 25% = concerning miscalibration


# ── Parsing ──────────────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    fm: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def parse_float(value: str) -> float | None:
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


# ── Data loading ─────────────────────────────────────────────────────────────

@dataclass
class Prediction:
    card_id: str
    confidence_before: float
    confidence_after: float | None
    outcome: str          # "validated" | "falsified"
    domain: str
    created: str
    last_reviewed: str


def load_card_predictions(cards_root: Path) -> list[Prediction]:
    predictions = []
    for stage in OUTCOME_STAGES:
        stage_dir = cards_root / stage
        if not stage_dir.exists():
            continue
        for path in sorted(stage_dir.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            fm = parse_frontmatter(text)
            cb = parse_float(fm.get("confidence_before", ""))
            if cb is None:
                continue  # skip cards without confidence tracking
            ca = parse_float(fm.get("confidence_after", ""))
            predictions.append(Prediction(
                card_id=fm.get("id", path.stem),
                confidence_before=cb,
                confidence_after=ca,
                outcome=stage,
                domain=fm.get("domain", ""),
                created=fm.get("created_date", fm.get("created", "")),
                last_reviewed=fm.get("last_reviewed", ""),
            ))
    return predictions


# ── Calibration math ─────────────────────────────────────────────────────────

@dataclass
class BandResult:
    label: str
    low: float
    high: float
    total: int = 0
    validated: int = 0
    falsified: int = 0
    cards: list[str] = field(default_factory=list)

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2

    @property
    def actual_accuracy(self) -> float | None:
        if self.total == 0:
            return None
        return self.validated / self.total

    @property
    def calibration_error(self) -> float | None:
        acc = self.actual_accuracy
        if acc is None:
            return None
        return self.midpoint - acc  # positive = overconfident, negative = underconfident

    @property
    def calibration_status(self) -> str:
        err = self.calibration_error
        if err is None:
            return "no data"
        abs_err = abs(err)
        if abs_err < WELL_CALIBRATED_THRESHOLD:
            return "✓ well-calibrated"
        elif abs_err < CONCERNING_THRESHOLD:
            direction = "over" if err > 0 else "under"
            return f"⚠  {direction}confident ({abs_err:.0%} off)"
        else:
            direction = "over" if err > 0 else "under"
            return f"✗ significantly {direction}confident ({abs_err:.0%} off)"


def compute_calibration(predictions: list[Prediction]) -> list[BandResult]:
    bands = [BandResult(label=l, low=lo, high=hi) for lo, hi, l in BANDS]
    for p in predictions:
        for band in bands:
            if band.low <= p.confidence_before < band.high:
                band.total += 1
                band.cards.append(p.card_id)
                if p.outcome == "validated":
                    band.validated += 1
                else:
                    band.falsified += 1
                break
    return bands


def overall_calibration_error(bands: list[BandResult]) -> float | None:
    """Mean absolute calibration error across populated bands."""
    errors = [abs(b.calibration_error) for b in bands if b.calibration_error is not None]
    if not errors:
        return None
    return sum(errors) / len(errors)


# ── Reporting ─────────────────────────────────────────────────────────────────

def print_report(predictions: list[Prediction], cards_root: Path, brief: bool = False) -> None:
    bands = compute_calibration(predictions)
    mace = overall_calibration_error(bands)
    today = date.today().isoformat()

    validated_total = sum(1 for p in predictions if p.outcome == "validated")
    falsified_total = sum(1 for p in predictions if p.outcome == "falsified")
    total = len(predictions)

    print(f"Calibration Report — {today}")
    print(f"Cards with tracked predictions: {total} ({validated_total} validated, {falsified_total} falsified)")
    if mace is not None:
        status = "✓ well-calibrated" if mace < WELL_CALIBRATED_THRESHOLD else ("⚠  needs attention" if mace < CONCERNING_THRESHOLD else "✗ systematic bias detected")
        print(f"Mean absolute calibration error: {mace:.1%}  {status}")
    else:
        print("Mean absolute calibration error: n/a (no outcome data yet)")
    print()

    if not brief:
        print("By confidence band:")
        print(f"  {'Band':<12} {'Predicted':>10} {'Actual':>8} {'Cards':>6}  Status")
        print(f"  {'-'*12} {'-'*10} {'-'*8} {'-'*6}  {'-'*30}")
        for band in bands:
            if band.total == 0:
                print(f"  {band.label:<12} {'—':>10} {'—':>8} {0:>6}  no data")
                continue
            acc = band.actual_accuracy
            acc_str = f"{acc:.0%}" if acc is not None else "—"
            print(f"  {band.label:<12} {band.midpoint:>9.0%} {acc_str:>8} {band.total:>6}  {band.calibration_status}")
        print()

    # Domain breakdown (if varied)
    domains = {}
    for p in predictions:
        d = p.domain or "unknown"
        if d not in domains:
            domains[d] = {"validated": 0, "falsified": 0}
        domains[d][p.outcome] += 1

    if len(domains) > 1 and not brief:
        print("By domain:")
        for domain, counts in sorted(domains.items()):
            total_d = counts["validated"] + counts["falsified"]
            acc_d = counts["validated"] / total_d if total_d > 0 else 0
            print(f"  {domain:<25} {counts['validated']}/{total_d} validated ({acc_d:.0%} accuracy)")
        print()

    # Actionable findings
    findings = []
    for band in bands:
        err = band.calibration_error
        if err is None or band.total < 2:
            continue
        if abs(err) >= CONCERNING_THRESHOLD:
            direction = "overconfident" if err > 0 else "underconfident"
            findings.append(
                f"Systematic {direction} at {band.label} band "
                f"(predicted {band.midpoint:.0%}, actual {band.actual_accuracy:.0%})"
            )

    if findings:
        print("Actionable findings:")
        for f in findings:
            print(f"  → {f}")
        print()
    elif total >= 5:
        print("No systematic bias detected. Keep tracking.")
        print()

    if total < 5:
        print(f"Note: Only {total} cards with outcome data. Calibration statistics are unreliable until n≥10.")
        print("      Keep logging predictions with confidence_before on all candidate cards.")

    # Belief-in-practice accuracy (complements card-level calibration)
    if not brief and ACTION_LOG.exists():
        resolved = []
        with open(ACTION_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    import json as _json
                    a = _json.loads(line)
                except ValueError:
                    continue
                if not a.get("outcome_pending") and a.get("result"):
                    resolved.append(a)
        if resolved:
            good = sum(1 for a in resolved if a["result"] == "good")
            bad  = sum(1 for a in resolved if a["result"] == "bad")
            acc  = good / len(resolved) if resolved else 0
            n_cards = len(set(a["card_id"] for a in resolved))
            print()
            print(f"Belief-in-practice: {good}/{len(resolved)} good outcomes ({acc:.0%}) across {n_cards} cards")
            if bad > 0:
                bad_cards = list(set(a["card_id"] for a in resolved if a["result"] == "bad"))
                print(f"  Cards with bad outcomes: {', '.join(bad_cards)}")
                print("  → Re-run adversarial-review.py --prep on these cards")


def report_to_json(predictions: list[Prediction], cards_root: Path) -> dict:
    bands = compute_calibration(predictions)
    mace = overall_calibration_error(bands)
    return {
        "date": date.today().isoformat(),
        "total_predictions": len(predictions),
        "validated": sum(1 for p in predictions if p.outcome == "validated"),
        "falsified": sum(1 for p in predictions if p.outcome == "falsified"),
        "mace": round(mace, 4) if mace is not None else None,
        "well_calibrated": (mace < WELL_CALIBRATED_THRESHOLD) if mace is not None else None,
        "bands": [
            {
                "label": b.label,
                "midpoint": b.midpoint,
                "total": b.total,
                "validated": b.validated,
                "falsified": b.falsified,
                "actual_accuracy": round(b.actual_accuracy, 4) if b.actual_accuracy is not None else None,
                "calibration_error": round(b.calibration_error, 4) if b.calibration_error is not None else None,
                "status": b.calibration_status,
            }
            for b in bands
        ],
    }


def append_to_history(report: dict) -> None:
    """Append this run to the calibration history log for trend tracking."""
    with open(CALIBRATION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(report) + "\n")


def load_calibration_trend(n_weeks: int = 8) -> list[dict]:
    """Load last N calibration snapshots for trend display."""
    if not CALIBRATION_LOG.exists():
        return []
    rows = []
    with open(CALIBRATION_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    return rows[-n_weeks:]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards-root", type=Path, default=CARDS_ROOT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--brief", action="store_true", help="One-line summary only")
    parser.add_argument("--trend", action="store_true", help="Show calibration trend over time")
    args = parser.parse_args()

    if args.trend:
        history = load_calibration_trend()
        if not history:
            print("No calibration history yet. Run without --trend to generate first snapshot.")
            return 0
        print("Calibration trend (MACE = mean absolute calibration error):")
        for row in history:
            mace = row.get("mace")
            mace_str = f"{mace:.1%}" if mace is not None else "n/a"
            n = row.get("total_predictions", 0)
            flag = " ⚠" if (mace and mace >= CONCERNING_THRESHOLD) else ""
            print(f"  {row['date']}  MACE={mace_str}  n={n}{flag}")
        return 0

    predictions = load_card_predictions(args.cards_root)

    if args.json:
        report = report_to_json(predictions, args.cards_root)
        append_to_history(report)
        print(json.dumps(report, ensure_ascii=False))
    else:
        print_report(predictions, args.cards_root, brief=args.brief)
        report = report_to_json(predictions, args.cards_root)
        append_to_history(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
