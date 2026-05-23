# Card Lifecycle

## Overview

```
                      ┌─────────────┐
                      │  candidate  │ ← Initial logging
                      └──────┬──────┘
                             │ (add prediction + run test)
                      ┌──────▼──────┐
                      │ tested_once │
                      └──────┬──────┘
                    ┌─────────────────┐
          (confirmed)                (denied)
          ┌─────────┴──┐          ┌──┴────────┐
          │  validated │          │ falsified │
          └─────┬──────┘          └───────────┘
                │ (scope shift / superseded)
          ┌─────▼──────┐
          │   retired  │
          └────────────┘

observations/ ← weak signals, sub-card tier
```

---

## Stage Requirements

### candidate
A pattern worth tracking. Not yet tested.

**Required frontmatter:**
- `id`, `title`, `status: candidate`, `created`

**Required sections:**
- `# Claim` — the belief, stated precisely
- `# Why we believe it` — reasoning and initial evidence
- `# Scope` — what this applies to, and what it explicitly doesn't

**Strongly recommended (flagged by validator if missing):**
- An explicit falsification condition (in `# Scope`, `# Proxy Encounters`, or a dedicated section)

**Common mistake:** Writing a claim without specifying its scope conditions. "Users prefer X" is not a card. "Users in onboarding prefer X when they have less than 3 sessions completed" is.

---

### tested_once
The belief has been tested against a real prediction. Evidence exists, but one test is not sufficient for validation.

**Additional required sections:**
- `# Prediction` — what you expected to happen, stated *before* the test
- `# Test` — what you did to test it, and what the conditions were
- `# Outcome` — what actually happened

**Critical constraint:** The prediction must have been written *before* the test was run. Post-hoc predictions don't count. The validator can't enforce this mechanically, but it's the most important rule in the system.

**Required frontmatter additions:**
- `confidence_before` — your confidence in the claim before the test (float 0–1)

---

### validated
Multiple confirming encounters, explicit confidence update, no outstanding counter-evidence.

**Additional required section:**
- `# Confidence update` — why your confidence changed, what the confirming encounters were, and what would still falsify this

**Required frontmatter additions:**
- `confidence_after` — your confidence after validation (float 0–1)
- `behavioral_impact_last_seen` — when this belief last changed a decision (ISO date)

**What "validated" means:** Not "definitely true forever." It means "tested and confirmed under the stated scope conditions, with an explicit account of what would change this assessment."

**Common mistake:** Treating validated as permanent. Validated cards should have an `expiry_or_retest_date`. If the world has changed, the belief needs re-evaluation.

---

### falsified
The prediction failed. The belief didn't hold under the test conditions.

**Required:** Same as tested_once. The `# Outcome` section explains the failure.

Falsified cards are retained — they're a record of what you tested and what didn't hold. They're also useful for spotting patterns: if three cards in the same domain get falsified with similar failure modes, that's a signal about the domain, not just the individual claims.

---

### retired
The belief was valid but no longer applies. Scope shifted, context changed, superseded by a stronger card.

**Required:** `# Claim`, `# Why we believe it`, `# Scope`

**Recommended:** A `# Retirement reason` section, and a `superseded_by` frontmatter field if another card replaces it.

---

### observations/
A sub-card tier for weak signals that don't yet rise to a full candidate. Park signals here when you've noticed something interesting but don't have enough to write a proper claim.

Observations have no required sections and no promotion gate. They're informal. The only discipline: if an observation is still sitting there after 60 days with no follow-up, it should either become a candidate or be deleted. Observations are not a graveyard.

---

## Promotion Rules

| From | To | Gate |
|---|---|---|
| candidate | tested_once | Prediction written, test run, outcome observed |
| tested_once | validated | Multiple confirming encounters + confidence_after set |
| any | falsified | Prediction failed |
| validated | retired | Scope no longer applies, or superseded |

**Who moves cards:** The agent or human reviewing the evidence. The validator enforces schema but doesn't move files — that's a judgment call.

---

## Encounter Tracking

`encounter_count` is incremented each time you observe a situation that would count as evidence for or against the card's claim. Combine with `retest_after_n_encounters` (default: 3) to surface cards that have accumulated enough evidence for re-evaluation.

Use `# Proxy Encounters` in your cards to define what counts as a weak, medium, and strong encounter. This prevents encounter inflation (counting marginal evidence as a full encounter).

---

## Anti-Patterns

**The Archive Anti-Pattern:** Treating the card system as a one-way archive where beliefs go in but never come out. Cards should be retired, falsified, and updated, not just accumulated.

**The Inference-as-Fact Anti-Pattern:** Writing a candidate card and immediately treating it as validated because you believe it. The promotion gate exists specifically to prevent this.

**The Unfalsifiable Card:** A card without a falsification condition can never be promoted correctly, because you haven't defined what "wrong" looks like. The validator warns on these.

**The Stale Validated Card:** A validated card that was true in 2024 but never got an `expiry_or_retest_date`. The validator flags validated cards past expiry.

**The Predictions-After-The-Fact Anti-Pattern:** Writing the prediction section after you already know the outcome. The system can't detect this, but it defeats the entire point of tested_once.
