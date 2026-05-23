#!/usr/bin/env python3
"""
adversarial-review.py — Pre-promotion adversarial pass for evidence-gate cards.

Before a tested_once card gets promoted to validated, a skeptical reviewer
challenges it: strongest counter-evidence, scope over-claims, selection bias,
conditions where it breaks down.

MODES:
  --prep CARD-ID      Format the card + encounters for agent review. Output
                      is the full challenge prompt for an LLM agent to reason
                      against. The calling agent then records the result.

  --record CARD-ID    Write the review result back to the card.
    --status clean|challenged
    --challenges "..."   (required if --status challenged)
    --reviewer "name"    (optional, defaults to "adversarial-agent")

  --pending           List tested_once cards that are threshold-ready but
                      have not yet had an adversarial review.

Usage:
    # Step 1: prep context for review agent
    python3 adversarial-review.py --prep CARD-20260101-001-slug

    # Step 2: agent reads output, reasons, then records result
    python3 adversarial-review.py --record CARD-20260101-001-slug \\
      --status clean \\
      --reviewer "primary-agent"

    # Or if challenges found:
    python3 adversarial-review.py --record CARD-20260101-001-slug \\
      --status challenged \\
      --challenges "The confirming encounters all come from the same context (Brayden's own workflow). No external validation. The claim may not generalize beyond this single-user scenario." \\
      --reviewer "primary-agent"

    # List cards needing review
    python3 adversarial-review.py --pending
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

CARDS_ROOT = Path.home() / ".evidence-gate" / "cards"
ENCOUNTERS_LOG = CARDS_ROOT.parent / "encounters.jsonl"
ADVERSARIAL_LOG = CARDS_ROOT.parent / "adversarial-reviews.jsonl"

ACTIVE_STAGES = ("candidate", "tested_once")
ALL_STAGES = ("candidate", "tested_once", "validated", "falsified", "retired")
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


def find_card(cards_root: Path, card_id: str) -> tuple[Path, dict, str] | None:
    for stage in ALL_STAGES:
        stage_dir = cards_root / stage
        if not stage_dir.exists():
            continue
        for path in stage_dir.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(text)
            if fm.get("id") == card_id:
                return path, fm, body
    return None


def load_encounters(card_id: str) -> list[dict]:
    if not ENCOUNTERS_LOG.exists():
        return []
    encounters = []
    with open(ENCOUNTERS_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    e = json.loads(line)
                    if e.get("card_id") == card_id:
                        encounters.append(e)
                except ValueError:
                    pass
    return encounters


# ── Prep mode ─────────────────────────────────────────────────────────────────

CHALLENGE_PROMPT = """
You are a rigorous, skeptical peer reviewer. Your job is to challenge this belief
BEFORE it gets promoted to "validated." You are NOT trying to be contrarian for its
own sake — you are trying to find real weaknesses that would embarrass the system
if the belief turned out to be wrong after promotion.

For the card below, systematically work through these questions:

1. SCOPE OVER-CLAIM: Is the claim stated more broadly than the evidence supports?
   Does it generalize beyond what was actually observed?

2. SELECTION BIAS: Are the confirming encounters drawn from a narrow or unrepresentative
   sample? Same context, same person, same time period, same mood?

3. COUNTER-EVIDENCE: What's the strongest argument against this belief?
   What would a smart, well-informed opponent say?

4. CONFOUNDING: Could another factor explain the same observations?
   Is the claim actually measuring what it claims to measure?

5. EDGE CASES: Under what conditions would this belief break down?
   Name at least two specific edge cases.

6. FALSIFICATION QUALITY: Is the falsification condition tight enough to actually
   catch a wrong belief? Or is it written to be hard to trigger?

7. PROMOTION VERDICT:
   - CLEAN: The challenges are minor or already addressed. Promote.
   - CHALLENGED: Material weaknesses found. Do not promote until addressed.
     State exactly what needs to change before promotion.

Be specific. Vague challenges are useless. Either name a real problem or say it's clean.

---
CARD TO REVIEW:
{card_content}

---
ENCOUNTER HISTORY ({n_encounters} encounters):
{encounter_summary}

---
ADVERSARIAL REVIEW (your output):
"""


def cmd_prep(cards_root: Path, card_id: str) -> None:
    result = find_card(cards_root, card_id)
    if not result:
        print(f"ERROR: Card {card_id!r} not found")
        sys.exit(1)

    path, fm, body = result
    encounters = load_encounters(card_id)

    # Format encounter summary
    if encounters:
        enc_lines = []
        for e in encounters[-10:]:  # last 10 encounters
            falsifying = " [FALSIFYING]" if e.get("falsifying") else ""
            enc_lines.append(
                f"  #{e.get('encounter_num', '?')} | {e.get('date', '?')} | "
                f"strength: {e.get('strength', '?')}{falsifying}\n"
                f"  > {e.get('evidence', '')}"
            )
        encounter_summary = "\n\n".join(enc_lines)
    else:
        encounter_summary = "(no encounters logged yet)"

    # Full card content for review
    card_content = path.read_text(encoding="utf-8")

    print(CHALLENGE_PROMPT.format(
        card_content=card_content,
        n_encounters=len(encounters),
        encounter_summary=encounter_summary,
    ))

    print("\n" + "=" * 60)
    print("INSTRUCTIONS FOR CALLING AGENT:")
    print("=" * 60)
    print(f"""
After completing your adversarial review above, record the result:

If CLEAN:
  python3 adversarial_review.py \\
    --record {card_id} \\
    --status clean \\
    --reviewer "primary-agent"

If CHALLENGED:
  python3 adversarial_review.py \\
    --record {card_id} \\
    --status challenged \\
    --challenges "YOUR SPECIFIC CHALLENGES HERE" \\
    --reviewer "primary-agent"

After recording, the card will be updated with the adversarial_status field.
A CLEAN review allows promotion. A CHALLENGED review blocks promotion until
the challenges are addressed and a second review passes.
""")


# ── Record mode ───────────────────────────────────────────────────────────────

def cmd_record(
    cards_root: Path,
    card_id: str,
    status: str,
    challenges: str,
    reviewer: str,
) -> None:
    result = find_card(cards_root, card_id)
    if not result:
        print(f"ERROR: Card {card_id!r} not found")
        sys.exit(1)

    path, fm, body = result
    review_date = date.today().isoformat()

    # Update frontmatter
    new_fields = {
        "adversarial_status": status,
        "adversarial_review_date": review_date,
        "adversarial_reviewer": reviewer,
    }

    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        print(f"ERROR: Could not parse frontmatter in {path}")
        sys.exit(1)

    fm_lines = match.group(1).splitlines()
    seen_keys = set()
    updated_lines = []
    for line in fm_lines:
        if ":" in line:
            k = line.split(":")[0].strip()
            if k in new_fields:
                updated_lines.append(f"{k}: {new_fields[k]}")
                seen_keys.add(k)
            else:
                updated_lines.append(line)
        else:
            updated_lines.append(line)

    # Add any new keys not present
    for k, v in new_fields.items():
        if k not in seen_keys:
            updated_lines.append(f"{k}: {v}")

    new_fm = "---\n" + "\n".join(updated_lines) + "\n---\n"
    body_text = text[match.end():]

    # Append challenges section to body if challenged
    if status == "challenged" and challenges:
        if "# Adversarial Review" in body_text:
            # Replace existing
            body_text = re.sub(
                r"# Adversarial Review\n.*?(?=\n#|\Z)", 
                f"# Adversarial Review\n**Date:** {review_date} | **Reviewer:** {reviewer} | **Verdict:** CHALLENGED\n\n{challenges}\n",
                body_text,
                flags=re.DOTALL,
            )
        else:
            body_text += (
                f"\n# Adversarial Review\n"
                f"**Date:** {review_date} | **Reviewer:** {reviewer} | **Verdict:** CHALLENGED\n\n"
                f"{challenges}\n"
            )
    elif status == "clean":
        if "# Adversarial Review" not in body_text:
            body_text += (
                f"\n# Adversarial Review\n"
                f"**Date:** {review_date} | **Reviewer:** {reviewer} | **Verdict:** CLEAN\n\n"
                f"No material weaknesses found. Promotion approved.\n"
            )

    path.write_text(new_fm + body_text, encoding="utf-8")

    # Append to adversarial log
    log_entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "card_id": card_id,
        "status": status,
        "reviewer": reviewer,
        "review_date": review_date,
        "challenges": challenges if challenges else None,
    }
    with open(ADVERSARIAL_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")

    if status == "challenged":
        print(f"CHALLENGED: {card_id} — promotion blocked")
        print(f"  Challenges recorded. Address them, then run a second adversarial review.")
    else:
        print(f"CLEAN: {card_id} — adversarial review passed, promotion approved")

    print(f"  Review logged to {ADVERSARIAL_LOG.name}")


# ── Pending mode ──────────────────────────────────────────────────────────────

def cmd_pending(cards_root: Path) -> None:
    """List tested_once cards at threshold that need adversarial review."""
    stage_dir = cards_root / "tested_once"
    if not stage_dir.exists():
        print("No tested_once directory found.")
        return

    pending = []
    reviewed_clean = []
    reviewed_challenged = []

    for path in sorted(stage_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm, _ = parse_frontmatter(text)
        card_id = fm.get("id", path.stem)
        count = int(fm.get("encounter_count", "0") or "0")
        threshold = int(fm.get("retest_after_n_encounters", "3") or "3")
        adv_status = fm.get("adversarial_status", "")
        adv_date = fm.get("adversarial_review_date", "")
        title = fm.get("title", "")[:60]

        threshold_ready = count >= threshold

        if adv_status == "clean":
            reviewed_clean.append((card_id, title, count, threshold, adv_date))
        elif adv_status == "challenged":
            reviewed_challenged.append((card_id, title, count, threshold, adv_date))
        elif threshold_ready:
            pending.append((card_id, title, count, threshold))

    print(f"Adversarial review status — {date.today().isoformat()}")
    print()

    if pending:
        print(f"NEEDS REVIEW ({len(pending)}) — threshold met, no adversarial pass yet:")
        for card_id, title, count, threshold in pending:
            print(f"  🔍 {card_id} [{count}/{threshold}]: {title}")
            print(f"     Run: python3 adversarial-review.py --prep {card_id}")
        print()

    if reviewed_challenged:
        print(f"BLOCKED ({len(reviewed_challenged)}) — challenges unresolved, cannot promote:")
        for card_id, title, count, threshold, adv_date in reviewed_challenged:
            print(f"  🚫 {card_id} (reviewed {adv_date}): {title}")
        print()

    if reviewed_clean:
        print(f"READY TO PROMOTE ({len(reviewed_clean)}) — adversarial review passed:")
        for card_id, title, count, threshold, adv_date in reviewed_clean:
            print(f"  ✅ {card_id} (reviewed {adv_date}): {title}")
        print()

    if not pending and not reviewed_challenged and not reviewed_clean:
        print("No tested_once cards at threshold. Nothing needs adversarial review.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards-root", type=Path, default=CARDS_ROOT)
    parser.add_argument("--prep", metavar="CARD-ID")
    parser.add_argument("--record", metavar="CARD-ID")
    parser.add_argument("--status", choices=["clean", "challenged"])
    parser.add_argument("--challenges", default="")
    parser.add_argument("--reviewer", default="primary-agent")
    parser.add_argument("--pending", action="store_true")
    args = parser.parse_args()

    if args.prep:
        cmd_prep(args.cards_root, args.prep)
    elif args.record:
        if not args.status:
            print("ERROR: --status (clean|challenged) is required with --record")
            sys.exit(1)
        if args.status == "challenged" and not args.challenges:
            print("ERROR: --challenges is required when --status is challenged")
            sys.exit(1)
        cmd_record(args.cards_root, args.record, args.status, args.challenges, args.reviewer)
    elif args.pending:
        cmd_pending(args.cards_root)
    else:
        parser.print_help()
        sys.exit(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
