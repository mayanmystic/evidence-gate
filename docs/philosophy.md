# Philosophy

## The Problem

AI agents make confident claims. The problem isn't the confidence — it's the lack of metadata around it. When an agent says "users prefer X over Y," you don't know:

- Was this tested, or inferred?
- Under what conditions does it hold?
- What would falsify it?
- Has the agent ever checked if it's still true?

Without answers to these questions, an agent's beliefs accumulate without accountability. Old beliefs persist past their expiry. Inferences get treated as validated facts. The agent doesn't know what it doesn't know.

Evidence Gate is a structural answer to this problem.

---

## The Core Idea

Every belief an agent maintains should be tracked as a card that moves through an evidence lifecycle:

**Candidate** → you've noticed a pattern and want to track it, but you haven't tested it yet.

**Tested once** → you made a prediction, ran a test, and observed an outcome. The belief has some evidence, but not enough to rely on.

**Validated** → multiple confirming encounters, explicit confidence update, no outstanding counter-evidence.

**Falsified** → the prediction failed. Kept as a record of what didn't hold.

**Retired** → the belief was valid but no longer applies. Scope changed, context shifted.

The key constraint: **you can't skip stages.** A belief can't become validated without going through tested_once. And a card can't enter tested_once without a prediction made *before* the test.

---

## The Falsification Rule

Every candidate card must include an explicit falsification condition. This is the single most important constraint in the system.

A falsification condition is: *If [observable event] happens, this belief should be demoted.*

Without a falsification condition, a belief is not falsifiable — and an unfalsifiable belief is not a belief. It's an assumption baked into the system with no mechanism for correction.

The falsification condition is checked at card creation. Cards without one are rejected by the validator.

---

## What This Isn't

**Not a memory system.** Memory is about retrieval. Evidence Gate is about epistemology — tracking the quality and confidence of what you believe, not just what you've stored.

**Not a note-taking system.** Notes are unbounded. Cards have strict lifecycle requirements. The friction is intentional: if a belief isn't worth tracking formally, it shouldn't be treated as a validated fact.

**Not a replacement for judgment.** The system enforces structure. It doesn't replace the human or agent judgment required to evaluate evidence, write falsification conditions, or decide when a belief has been validated.

---

## Design Choices

**Files over databases.** Cards are Markdown files with YAML frontmatter. They're readable, diffable, searchable, and don't require infrastructure. An agent can write them. A human can read them. Git handles versioning.

**Explicit over implicit.** Every required field is explicitly validated. The schema doesn't allow ambiguity. If a field is missing or malformed, the validator fails loudly.

**Cumulative sections.** A tested_once card must have everything a candidate has, plus a prediction and outcome. A validated card must have everything a tested_once has, plus a confidence update. This makes lifecycle progression legible.

**Falsification first.** The falsification condition is required before any other evidence is gathered. This forces the question "what would have to happen for this to be wrong?" before you start looking for confirming evidence.

---

## Integration Patterns

### Minimal (human-in-the-loop)
An agent writes candidate cards when it infers patterns. Humans review, add falsification conditions, and move cards through stages when evidence accumulates. `validate.py` runs as a CI check to enforce schema compliance.

### Agent-assisted
An agent writes and validates cards. A weekly review surfaces stale candidates (no encounters in 30+ days) and tested cards approaching their retest threshold. The agent proposes promotions; humans confirm.

### Semi-automated
An encounter detector runs over session history or structured logs, identifies situations matching candidate card claims, and auto-increments encounter_count. Cards meeting the `retest_after_n_encounters` threshold are automatically staged for human review.

### The Perfect Loop (not yet built)
- Machine-readable falsification predicates (not just prose)
- Automated encounter detection against structured event logs
- System-level calibration tracking (prediction confidence vs. observed accuracy)
- Auto-staging when evidence thresholds are met
- Adversarial pre-promotion pass (a second agent challenges the evidence before validated)
- Action-outcome feedback (beliefs that drive decisions get outcome logged back to the card)

See the [`ROADMAP`](../ROADMAP.md) for where this is headed.

---

## The Cost of Getting This Wrong

An AI agent that doesn't track belief quality will:
- Cite inferences as facts
- Carry stale beliefs long past their expiry
- Never notice when predictions fail
- Build new beliefs on top of unvalidated foundations
- Become less reliable as it gains more "memory"

The evidence gate is the correction mechanism. It won't make an agent's beliefs correct. It will make an agent's beliefs *accountable*.
