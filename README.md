# evidence-gate

**An evidence-gated belief system for AI agents.**

Most AI agent "memory" is a retrieval problem: store things, find them later. Evidence Gate is an epistemology problem: *when should an agent actually trust what it thinks it knows?*

Evidence Gate is a lightweight framework — a file structure, a card schema, a validation script, and a lifecycle doctrine — for maintaining falsifiable, evidence-tracked beliefs inside an AI agent system. Cards can't be promoted without meeting explicit evidentiary gates. Claims get retired when they stop earning encounters. Nothing is "known" until it's been tested.

---

## Why This Exists

AI agents are confident. Too confident. They surface beliefs from training or memory without distinguishing between:

- "I've seen this pattern confirmed three times"
- "This seems plausible based on analogical reasoning"
- "I inferred this once from a single data point"

Evidence Gate forces agents to make this distinction explicit. Every belief lives in a lifecycle stage. Every stage requires specific evidence. You can't skip stages. And every belief has an explicit falsification condition — without that, the loop never closes.

---

## The Card Lifecycle

```
candidate → tested_once → validated
               ↓               ↓
           falsified        retired
               ↓
           observations (weak signals, sub-card)
```

**candidate** — A belief worth tracking. Requires: claim, reasoning, scope, and *an explicit falsification condition*. No falsification condition = rejected.

**tested_once** — The belief has been tested against a real prediction. Requires: prediction made before the test, test design, and observed outcome.

**validated** — Multiple confirming encounters, confidence updated, no outstanding counter-evidence. Requires all of the above + confidence_before/after.

**falsified** — The prediction failed. The card is retained as a record of what didn't hold.

**retired** — The belief was valid but no longer applies. Scope shifted, context changed, superseded by a stronger card.

**observations/** — Sub-card signals that don't yet rise to a full claim. Park weak signals here before deciding whether to formalize.

---

## Quickstart

```bash
# Clone the repo
git clone https://github.com/YOUR_ORG/evidence-gate.git
cd evidence-gate

# Create your cards directory
mkdir -p ~/.evidence-gate/cards/{candidate,tested_once,validated,falsified,retired,observations}

# Copy a template and fill it in
cp templates/candidate.md ~/.evidence-gate/cards/candidate/CARD-20260101-001-my-first-claim.md
# Edit the card...

# Validate your cards
python3 validate.py --cards-root ~/.evidence-gate/cards

# Or use the default path
python3 validate.py
```

---

## Card Naming

```
CARD-YYYYMMDD-NNN-short-slug.md
```

Namespace prefix is optional but recommended for multi-domain systems:
- `CARD-` — general agent behavior / product beliefs
- Extend with your own prefixes for domain separation (e.g., `PRODUCT-`, `ENG-`)

---

## Required Fields (YAML Frontmatter)

| Field | Required | Notes |
|---|---|---|
| `id` | ✅ | Must match filename |
| `title` | ✅ | One-line claim summary |
| `status` | ✅ | Must match directory |
| `created` | ✅ | ISO date |
| `source` | recommended | Session, document, or event that generated this |
| `domain` | recommended | Scoping tag |
| `retest_after_n_encounters` | recommended | Default 3 |
| `encounter_count` | recommended | Increment when you encounter the situation |
| `confidence_before` | for tested_once+ | Float 0–1 |
| `confidence_after` | for validated | Float 0–1 |
| `expiry_or_retest_date` | recommended | ISO date — when to force a re-evaluation |
| `scope_conditions` | recommended | When does this belief apply? |
| `behavioral_impact_last_seen` | for validated | When did this belief last change a decision? |

---

## Required Body Sections by Status

**candidate:** `# Claim`, `# Why we believe it`, `# Scope`

**tested_once:** above + `# Prediction`, `# Test`, `# Outcome`

**validated:** above + `# Confidence update`

**falsified:** same as tested_once (outcome section explains the falsification)

**retired:** `# Claim`, `# Why we believe it`, `# Scope` (+ optional `# Retirement reason`)

---

## Validation

```bash
python3 validate.py                          # default: ~/.evidence-gate/cards
python3 validate.py --cards-root ./my-cards  # custom path
python3 validate.py --json                   # machine-readable output
```

Exits `0` if all cards pass, `1` on any error.

---

## The Falsification Rule

**Every candidate card must include an explicit falsification condition.** This is non-negotiable. A belief without a falsification condition is not a belief — it's an unfalsifiable assumption.

A good falsification condition is:
- **Specific** — not "if it doesn't work out"
- **Predictive** — describes a future observable event
- **Falsifying** — if this happens, the belief should be demoted or retired

Bad: *"If users don't like it, the belief is wrong."*

Good: *"Three consecutive decision-points where following this belief produced worse outcomes than the alternative would falsify this claim."*

---

## Integration Patterns

### Manual (human-in-the-loop)
Run `validate.py` after each card update. Use the triage cron pattern to surface stale cards. Move cards manually when thresholds are met.

### Agent-assisted
Have your AI agent write candidate cards when it infers a pattern. Agent runs `validate.py` to confirm schema compliance. Cards still require human review before promotion.

### Semi-automated
Add an encounter detection pass: agent reviews session history weekly, identifies situations matching candidate card claims, auto-increments `encounter_count`. Surfaces cards meeting threshold for human promotion decision.

---

## Philosophy

See [`docs/philosophy.md`](docs/philosophy.md) for the full design rationale.

---

## License

MIT. Use freely.
