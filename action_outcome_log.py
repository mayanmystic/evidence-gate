#!/usr/bin/env python3
"""
action-outcome-log.py — Close the belief → action → outcome → belief loop.

When a validated card drives a decision, log the action at decision time.
When the outcome is observable, record it. This data feeds back into
calibration-report.py and provides evidence for re-evaluating card confidence.

This is the final layer of the evidence gate: beliefs don't just get tested
in the abstract — they get tested in real decisions, with real consequences.

MODES:
  --log CARD-ID         Log that a validated card drove a decision.
    --action "..."      What decision/action was taken (required)
    --context "..."     Why/when (optional)

  --outcome ACTION-ID   Record what happened after an action.
    --result good|neutral|bad
    --evidence "..."    What was observed (required)

  --pending             Show actions awaiting outcome recording (>1h old).

  --review CARD-ID      Show all action-outcome history for a card.

  --impact              Summary: how well are validated beliefs performing
                        in real decisions? Accuracy by card, by domain.

  --today               Show all actions logged today (useful in daily cron).

Usage examples:
    # Log a decision driven by a card
    python3 action_outcome_log.py --log CARD-20260507-001-telegram-first-async-updates \\
      --action "Sent nightly build result to Telegram instead of inline" \\
      --context "Brayden mid-session, async delivery preferred per card"

    # Record the outcome later
    python3 action_outcome_log.py --outcome ACT-20260523-001 \\
      --result good \\
      --evidence "Brayden checked Telegram at natural break, confirmed it was right call"

    # Check what's awaiting outcomes
    python3 action_outcome_log.py --pending

    # How are validated cards performing in practice?
    python3 action_outcome_log.py --impact
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

CARDS_ROOT = Path.home() / ".evidence-gate" / "cards"
ACTION_LOG = CARDS_ROOT.parent / "action-outcomes.jsonl"
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

VALID_RESULTS = ("good", "neutral", "bad")


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def find_card_meta(cards_root: Path, card_id: str) -> dict | None:
    """Return basic card metadata (title, domain) without loading full body."""
    all_stages = ("candidate", "tested_once", "validated", "falsified", "retired")
    for stage in all_stages:
        stage_dir = cards_root / stage
        if not stage_dir.exists():
            continue
        for path in stage_dir.glob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            fm = parse_frontmatter(text)
            if fm.get("id") == card_id:
                return {
                    "id": card_id,
                    "title": fm.get("title", ""),
                    "domain": fm.get("domain", ""),
                    "status": fm.get("status", stage),
                }
    return None


def load_all_actions() -> list[dict]:
    if not ACTION_LOG.exists():
        return []
    actions = []
    with open(ACTION_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    actions.append(json.loads(line))
                except ValueError:
                    pass
    return actions


def save_action(entry: dict) -> None:
    with open(ACTION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def next_action_id() -> str:
    today = date.today().strftime("%Y%m%d")
    actions = load_all_actions()
    today_actions = [a for a in actions if a.get("action_id", "").startswith(f"ACT-{today}-")]
    seq = len(today_actions) + 1
    return f"ACT-{today}-{seq:03d}"


# ── Log mode ──────────────────────────────────────────────────────────────────

def cmd_log(cards_root: Path, card_id: str, action: str, context: str) -> None:
    # Verify card exists
    meta = find_card_meta(cards_root, card_id)
    if not meta:
        print(f"WARNING: Card {card_id!r} not found — logging anyway")
        meta = {"id": card_id, "title": "", "domain": ""}
    elif meta["status"] not in ("validated",):
        print(f"WARNING: Card {card_id!r} is {meta['status']!r}, not validated. "
              f"Only validated beliefs should be driving decisions. Logging anyway.")

    action_id = next_action_id()
    entry = {
        "kind": "action",
        "action_id": action_id,
        "card_id": card_id,
        "card_title": meta.get("title", ""),
        "card_domain": meta.get("domain", ""),
        "ts": datetime.now(timezone.utc).isoformat(),
        "date": date.today().isoformat(),
        "action": action,
        "context": context,
        "outcome_pending": True,
        "result": None,
        "outcome_evidence": None,
        "outcome_date": None,
    }
    save_action(entry)
    print(f"LOGGED: {action_id}")
    print(f"  Card: {card_id}")
    print(f"  Action: {action[:100]}")
    print(f"  Record outcome when observable:")
    print(f"    python3 action_outcome_log.py --outcome {action_id} --result good|neutral|bad --evidence \"...\"")


# ── Outcome mode ──────────────────────────────────────────────────────────────

def cmd_outcome(action_id: str, result: str, evidence: str) -> None:
    if result not in VALID_RESULTS:
        print(f"ERROR: --result must be one of {VALID_RESULTS}")
        sys.exit(1)

    actions = load_all_actions()
    target = next((a for a in actions if a.get("action_id") == action_id), None)
    if not target:
        print(f"ERROR: Action {action_id!r} not found")
        sys.exit(1)

    if not target.get("outcome_pending"):
        print(f"WARNING: {action_id} already has an outcome recorded. Overwriting.")

    # Rewrite the log with the updated entry
    outcome_date = date.today().isoformat()
    updated = []
    for a in actions:
        if a.get("action_id") == action_id:
            a = dict(a)
            a["outcome_pending"] = False
            a["result"] = result
            a["outcome_evidence"] = evidence
            a["outcome_date"] = outcome_date
        updated.append(a)

    ACTION_LOG.write_text(
        "\n".join(json.dumps(a) for a in updated) + "\n",
        encoding="utf-8"
    )

    emoji = {"good": "✅", "neutral": "➡️", "bad": "❌"}[result]
    print(f"OUTCOME RECORDED: {action_id}")
    print(f"  Card: {target.get('card_id')}")
    print(f"  Result: {emoji} {result}")
    print(f"  Evidence: {evidence[:120]}")

    if result == "bad":
        print(f"\n  ⚠  Bad outcome on a validated belief. Consider:")
        print(f"     1. Running adversarial-review.py --prep {target.get('card_id')} to re-challenge")
        print(f"     2. Recording a falsifying encounter: encounter-detector.py --record {target.get('card_id')} --falsifying --strength strong --evidence \"...\"")


# ── Pending mode ──────────────────────────────────────────────────────────────

def cmd_pending(min_age_hours: int = 1) -> None:
    actions = load_all_actions()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=min_age_hours)

    pending = []
    for a in actions:
        if not a.get("outcome_pending"):
            continue
        try:
            ts = datetime.fromisoformat(a["ts"])
            if ts > cutoff:
                continue  # too recent
        except (KeyError, ValueError):
            pass
        pending.append(a)

    if not pending:
        print("No pending outcomes.")
        return

    print(f"Pending outcomes ({len(pending)}) — actions waiting for outcome recording:")
    print()
    for a in pending:
        age_str = ""
        try:
            ts = datetime.fromisoformat(a["ts"])
            age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
            age_str = f" ({age_hours:.0f}h ago)"
        except (KeyError, ValueError):
            pass
        print(f"  {a['action_id']}{age_str}")
        print(f"  Card: {a.get('card_id')}")
        print(f"  Action: {a.get('action', '')[:100]}")
        print(f"  Record: python3 action_outcome_log.py --outcome {a['action_id']} --result good|neutral|bad --evidence \"...\"")
        print()


# ── Review mode ───────────────────────────────────────────────────────────────

def cmd_review(card_id: str) -> None:
    actions = load_all_actions()
    card_actions = [a for a in actions if a.get("card_id") == card_id]

    if not card_actions:
        print(f"No action history for {card_id}")
        return

    total = len(card_actions)
    with_outcomes = [a for a in card_actions if not a.get("outcome_pending")]
    pending_count = total - len(with_outcomes)

    results = {"good": 0, "neutral": 0, "bad": 0}
    for a in with_outcomes:
        r = a.get("result", "")
        if r in results:
            results[r] += 1

    print(f"Action-outcome history: {card_id}")
    print(f"Total decisions driven by this card: {total}")
    print(f"With outcomes: {len(with_outcomes)} | Pending: {pending_count}")
    if with_outcomes:
        accuracy = results["good"] / len(with_outcomes) if with_outcomes else 0
        print(f"Good: {results['good']} | Neutral: {results['neutral']} | Bad: {results['bad']}")
        print(f"Effective accuracy: {accuracy:.0%}")
    print()

    for a in sorted(card_actions, key=lambda x: x.get("date", ""), reverse=True):
        status = "⏳ pending" if a.get("outcome_pending") else {
            "good": "✅", "neutral": "➡️", "bad": "❌"
        }.get(a.get("result", ""), "?")
        print(f"  {a['action_id']} | {a.get('date', '?')} | {status}")
        print(f"  Action: {a.get('action', '')[:120]}")
        if not a.get("outcome_pending") and a.get("outcome_evidence"):
            print(f"  Outcome: {a.get('outcome_evidence', '')[:120]}")
        print()


# ── Impact mode ───────────────────────────────────────────────────────────────

def cmd_impact(cards_root: Path) -> None:
    actions = load_all_actions()
    with_outcomes = [a for a in actions if not a.get("outcome_pending") and a.get("result")]

    if not with_outcomes:
        print("No resolved action-outcomes yet. Log decisions and record outcomes to populate this.")
        return

    print(f"Belief-in-Practice Impact Report — {date.today().isoformat()}")
    print(f"Total resolved action-outcomes: {len(with_outcomes)}")
    print()

    # Per-card breakdown
    by_card: dict[str, dict] = {}
    for a in with_outcomes:
        cid = a.get("card_id", "unknown")
        if cid not in by_card:
            by_card[cid] = {"good": 0, "neutral": 0, "bad": 0, "title": a.get("card_title", "")}
        r = a.get("result", "")
        if r in by_card[cid]:
            by_card[cid][r] += 1

    print("By card:")
    for cid, counts in sorted(by_card.items(), key=lambda x: -(x[1]["good"])):
        total_c = counts["good"] + counts["neutral"] + counts["bad"]
        acc = counts["good"] / total_c if total_c > 0 else 0
        bar = "█" * counts["good"] + "▒" * counts["neutral"] + "░" * counts["bad"]
        title = counts["title"][:50] or cid
        print(f"  {acc:.0%} [{bar}] {cid}: {title}")
        print(f"       good={counts['good']} neutral={counts['neutral']} bad={counts['bad']}")
    print()

    # Domain breakdown
    by_domain: dict[str, dict] = {}
    for a in with_outcomes:
        domain = a.get("card_domain", "unknown") or "unknown"
        if domain not in by_domain:
            by_domain[domain] = {"good": 0, "neutral": 0, "bad": 0}
        r = a.get("result", "")
        if r in by_domain[domain]:
            by_domain[domain][r] += 1

    if len(by_domain) > 1:
        print("By domain:")
        for domain, counts in sorted(by_domain.items()):
            total_d = counts["good"] + counts["neutral"] + counts["bad"]
            acc = counts["good"] / total_d if total_d > 0 else 0
            print(f"  {domain:<25} {acc:.0%} accuracy ({total_d} decisions)")
        print()

    # Overall
    total_all = len(with_outcomes)
    good_all = sum(1 for a in with_outcomes if a.get("result") == "good")
    bad_all = sum(1 for a in with_outcomes if a.get("result") == "bad")
    print(f"Overall: {good_all}/{total_all} good outcomes ({good_all/total_all:.0%} accuracy)")
    if bad_all > 0:
        bad_cards = set(a["card_id"] for a in with_outcomes if a.get("result") == "bad")
        print(f"Cards with bad outcomes ({len(bad_cards)}): {', '.join(bad_cards)}")
        print("→ Consider re-running adversarial-review.py --prep on these cards")


# ── Today mode ────────────────────────────────────────────────────────────────

def cmd_today() -> None:
    actions = load_all_actions()
    today = date.today().isoformat()
    today_actions = [a for a in actions if a.get("date") == today]

    if not today_actions:
        print(f"No actions logged today ({today}).")
        return

    print(f"Actions logged today ({today}): {len(today_actions)}")
    for a in today_actions:
        status = "⏳" if a.get("outcome_pending") else {"good": "✅", "neutral": "➡️", "bad": "❌"}.get(a.get("result", ""), "?")
        print(f"  {status} {a['action_id']} — {a.get('card_id')}")
        print(f"     {a.get('action', '')[:100]}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards-root", type=Path, default=CARDS_ROOT)
    parser.add_argument("--log", metavar="CARD-ID", help="Log a decision driven by this card")
    parser.add_argument("--action", default="", help="What decision/action was taken")
    parser.add_argument("--context", default="", help="Why/when the decision was made")
    parser.add_argument("--outcome", metavar="ACTION-ID", help="Record outcome for an action")
    parser.add_argument("--result", choices=VALID_RESULTS, help="good | neutral | bad")
    parser.add_argument("--evidence", default="", help="What was observed")
    parser.add_argument("--pending", action="store_true", help="Show actions awaiting outcomes")
    parser.add_argument("--review", metavar="CARD-ID", help="Show full history for a card")
    parser.add_argument("--impact", action="store_true", help="Impact summary across all cards")
    parser.add_argument("--today", action="store_true", help="Show today's logged actions")
    args = parser.parse_args()

    if args.log:
        if not args.action:
            print("ERROR: --action is required with --log")
            sys.exit(1)
        cmd_log(args.cards_root, args.log, args.action, args.context)
    elif args.outcome:
        if not args.result:
            print("ERROR: --result is required with --outcome")
            sys.exit(1)
        if not args.evidence:
            print("ERROR: --evidence is required with --outcome")
            sys.exit(1)
        cmd_outcome(args.outcome, args.result, args.evidence)
    elif args.pending:
        cmd_pending()
    elif args.review:
        cmd_review(args.review)
    elif args.impact:
        cmd_impact(args.cards_root)
    elif args.today:
        cmd_today()
    else:
        parser.print_help()
        sys.exit(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
