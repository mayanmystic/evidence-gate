#!/usr/bin/env python3
"""
encounter-detector.py — Daily encounter detection for evidence-gate cards.

Two modes:
  --show      Dump all active cards (candidate + tested_once) in compact form
              + recent memory/session content. The calling agent reads this
              output and reasons about which cards had encounters.

  --record    Write an encounter back to a card file.
              Args: --record CARD-ID --strength weak|medium|strong
                    --evidence "quoted snippet" [--date YYYY-MM-DD]

  --summary   Print encounter_count + days_since_last_encounter for all cards.
              Useful for triage.

No external dependencies. Reads ~/.brayden/cards/ by default.

Usage:
    python3 encounter-detector.py --show [--memory-dir PATH] [--cards-root PATH]
    python3 encounter-detector.py --record CARD-20260101-001-slug --strength medium --evidence "..."
    python3 encounter-detector.py --summary
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

CARDS_ROOT = Path.home() / ".evidence-gate" / "cards"
MEMORY_DIR = Path.home() / ".evidence-gate" / "memory"
ENCOUNTERS_LOG = CARDS_ROOT.parent / "encounters.jsonl"

ACTIVE_STAGES = ("candidate", "tested_once")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


# ── Parsing ──────────────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    fm: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm, text[match.end():]


def read_card(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fm, body = parse_frontmatter(text)
    if not fm:
        return None
    return {"path": path, "fm": fm, "body": body, "raw": text}


def load_active_cards(cards_root: Path) -> list[dict]:
    cards = []
    for stage in ACTIVE_STAGES:
        stage_dir = cards_root / stage
        if not stage_dir.exists():
            continue
        for path in sorted(stage_dir.glob("*.md")):
            card = read_card(path)
            if card:
                cards.append(card)
    return cards


# ── Memory loading ────────────────────────────────────────────────────────────

def load_recent_memory(memory_dir: Path, days: int = 2) -> str:
    today = date.today()
    chunks = []
    for offset in range(days):
        from datetime import timedelta
        d = today - timedelta(days=offset)
        path = memory_dir / f"{d.isoformat()}.md"
        if path.exists():
            content = path.read_text(encoding="utf-8")
            chunks.append(f"=== {d.isoformat()} ===\n{content[:6000]}")
    return "\n\n".join(chunks) if chunks else "(no recent memory files found)"


# ── Show mode ─────────────────────────────────────────────────────────────────

def cmd_show(cards_root: Path, memory_dir: Path) -> None:
    cards = load_active_cards(cards_root)
    memory = load_recent_memory(memory_dir)

    print("=" * 60)
    print("ENCOUNTER DETECTOR — Active Cards")
    print(f"Date: {date.today().isoformat()}")
    print(f"Active cards: {len(cards)}")
    print("=" * 60)
    print()

    for card in cards:
        fm = card["fm"]
        card_id = fm.get("id", "?")
        title = fm.get("title", "?")
        status = fm.get("status", "?")
        encounter_count = fm.get("encounter_count", "0")
        retest_threshold = fm.get("retest_after_n_encounters", "3")
        last_encounter = fm.get("last_encounter_date", "never")
        created = fm.get("created", "?")

        # Extract key sections from body for compact view
        body = card["body"]
        claim_match = re.search(r"# Claim\n(.*?)(?=\n#|\Z)", body, re.DOTALL)
        scope_match = re.search(r"# Scope\n(.*?)(?=\n#|\Z)", body, re.DOTALL)
        proxy_match = re.search(r"# Proxy Encounters\n(.*?)(?=\n#|\Z)", body, re.DOTALL)

        claim_text = claim_match.group(1).strip()[:400] if claim_match else "(no claim section)"
        scope_text = scope_match.group(1).strip()[:300] if scope_match else "(no scope section)"
        proxy_text = proxy_match.group(1).strip()[:300] if proxy_match else "(no proxy encounters defined)"

        print(f"CARD: {card_id}")
        print(f"  Title: {title}")
        print(f"  Status: {status} | Encounters: {encounter_count}/{retest_threshold} | Last: {last_encounter} | Created: {created}")
        print(f"  Claim: {claim_text[:200]}")
        print(f"  Scope: {scope_text[:150]}")
        print(f"  Proxy: {proxy_text[:150]}")
        print()

    print("=" * 60)
    print("RECENT SESSION CONTENT (last 2 days)")
    print("=" * 60)
    print(memory[:8000])
    print()
    print("=" * 60)
    print("INSTRUCTIONS FOR CALLING AGENT")
    print("=" * 60)
    print("""
For each card listed above:
1. Read the claim, scope, and proxy encounter definitions carefully.
2. Search the recent session content for situations that match.
3. A match = a real situation that would count as evidence for or against the claim.
   - Do NOT count theoretical discussions about the card itself.
   - Do NOT count situations where the card's topic came up but no outcome was observable.
   - DO count: observed behavior, user actions, decisions made, outcomes seen.
4. For each match found, call:
   python3 /home/openclaw/.openclaw/workspace/scripts/encounter-detector.py \\
     --record CARD-ID \\
     --strength weak|medium|strong \\
     --evidence "brief quoted evidence snippet (1-2 sentences)"

5. Use these strength definitions:
   - weak: topic arose but no clear confirming/denying signal
   - medium: observable situation that partially confirms or denies the claim
   - strong: clear, unambiguous evidence that confirms or denies the claim

6. If NO cards had encounters today, output: "NO_ENCOUNTERS_TODAY"
7. After all records are written, run:
   python3 validate.py
8. Then run:
   python3 /home/openclaw/.openclaw/workspace/scripts/encounter-detector.py --summary
   
   Report any cards that have hit their retest threshold (encounter_count >= retest_after_n_encounters).
   These should be flagged to Brayden for promotion, falsification, or scope update.
""")


# ── Record mode ───────────────────────────────────────────────────────────────

def cmd_record(
    cards_root: Path,
    card_id: str,
    strength: str,
    evidence: str,
    encounter_date: str,
) -> None:
    # Find the card file
    card_path: Path | None = None
    for stage in ACTIVE_STAGES:
        for candidate in (cards_root / stage).glob("*.md"):
            text = candidate.read_text(encoding="utf-8")
            fm, _ = parse_frontmatter(text)
            if fm.get("id") == card_id:
                card_path = candidate
                break
        if card_path:
            break

    if not card_path:
        print(f"ERROR: Card {card_id!r} not found in active stages ({', '.join(ACTIVE_STAGES)})")
        sys.exit(1)

    text = card_path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)

    # Increment encounter_count
    old_count = int(fm.get("encounter_count", "0") or "0")
    new_count = old_count + 1
    fm["encounter_count"] = str(new_count)
    fm["last_encounter_date"] = encounter_date

    # Rebuild frontmatter
    fm_lines = []
    seen_keys = set()
    # Preserve original key order, update changed keys
    match = FRONTMATTER_RE.match(text)
    if match:
        for line in match.group(1).splitlines():
            if ":" in line:
                k = line.split(":")[0].strip()
                if k in fm:
                    fm_lines.append(f"{k}: {fm[k]}")
                    seen_keys.add(k)
                else:
                    fm_lines.append(line)
            else:
                fm_lines.append(line)
    # Add any new keys not in original
    for k, v in fm.items():
        if k not in seen_keys:
            fm_lines.append(f"{k}: {v}")

    new_fm = "---\n" + "\n".join(fm_lines) + "\n---\n"

    # Append encounter to Encounters section or create it
    encounter_entry = (
        f"\n**Encounter {new_count}** — {encounter_date} | strength: {strength}\n"
        f"> {evidence}\n"
    )

    if "# Encounters" in body:
        body = body + encounter_entry
    else:
        body = body + f"\n# Encounters\n{encounter_entry}"

    card_path.write_text(new_fm + body, encoding="utf-8")

    # Append to audit log
    log_entry = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "card_id": card_id,
        "encounter_num": new_count,
        "date": encounter_date,
        "strength": strength,
        "evidence": evidence,
        "card_path": str(card_path),
    }
    with open(ENCOUNTERS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")

    threshold = int(fm.get("retest_after_n_encounters", "3") or "3")
    threshold_hit = new_count >= threshold

    print(f"RECORDED: {card_id} encounter #{new_count} (strength: {strength})")
    if threshold_hit:
        print(f"THRESHOLD_HIT: {card_id} has reached {new_count}/{threshold} encounters — flag for review")


# ── Summary mode ──────────────────────────────────────────────────────────────

def cmd_summary(cards_root: Path) -> None:
    cards = load_active_cards(cards_root)
    today = date.today()

    print(f"Encounter summary — {today.isoformat()}")
    print(f"Active cards: {len(cards)}")
    print()

    threshold_cards = []
    stale_cards = []

    for card in cards:
        fm = card["fm"]
        card_id = fm.get("id", "?")
        title = fm.get("title", "?")[:60]
        count = int(fm.get("encounter_count", "0") or "0")
        threshold = int(fm.get("retest_after_n_encounters", "3") or "3")
        last_enc = fm.get("last_encounter_date", "")
        created = fm.get("created", "")

        days_stale = None
        ref_date = last_enc or created
        if ref_date:
            try:
                d = datetime.strptime(ref_date, "%Y-%m-%d").date()
                days_stale = (today - d).days
            except ValueError:
                pass

        status_line = f"  {card_id}: {count}/{threshold} encounters | last: {last_enc or 'never'}"
        if days_stale and days_stale > 21:
            status_line += f" | STALE ({days_stale}d)"
            stale_cards.append((card_id, title, days_stale))
        print(status_line)

        if count >= threshold:
            threshold_cards.append((card_id, title, count, threshold))

    print()
    if threshold_cards:
        print(f"THRESHOLD CARDS ({len(threshold_cards)}) — flag for Brayden review:")
        for card_id, title, count, threshold in threshold_cards:
            print(f"  🔔 {card_id} [{count}/{threshold}]: {title}")
    else:
        print("No cards at threshold.")

    if stale_cards:
        print()
        print(f"STALE CARDS ({len(stale_cards)}) — no encounter in 21+ days:")
        for card_id, title, days in stale_cards:
            print(f"  ⚠  {card_id} ({days}d): {title}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards-root", type=Path, default=CARDS_ROOT)
    parser.add_argument("--memory-dir", type=Path, default=MEMORY_DIR)

    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("--show", help="Show active cards + recent memory for agent reasoning")
    sub.add_parser("--summary", help="Print encounter counts and threshold status")

    # Workaround: allow positional --show/--summary style
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--record", metavar="CARD-ID")
    parser.add_argument("--strength", choices=["weak", "medium", "strong"], default="medium")
    parser.add_argument("--evidence", default="")
    parser.add_argument("--date", dest="encounter_date", default=date.today().isoformat())

    args = parser.parse_args()

    if args.show:
        cmd_show(args.cards_root, args.memory_dir)
    elif args.summary:
        cmd_summary(args.cards_root)
    elif args.record:
        if not args.evidence:
            print("ERROR: --evidence is required with --record")
            sys.exit(1)
        cmd_record(
            args.cards_root,
            args.record,
            args.strength,
            args.evidence,
            args.encounter_date,
        )
    else:
        parser.print_help()
        sys.exit(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
