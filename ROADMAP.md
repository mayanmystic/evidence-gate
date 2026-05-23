# Roadmap

The current version of Evidence Gate is intentionally minimal: a schema, a validator, and a lifecycle doctrine. No infrastructure required. No dependencies.

The gap between "minimal" and "ideal" is worth naming clearly.

---

## What Would Make This Perfect

### 1. Machine-readable falsification predicates

Today, falsification conditions are prose. An agent can read them, but can't automatically check them against structured event logs or metrics.

The ideal version adds a structured `falsify_predicate` field alongside the prose condition:

```yaml
falsify_predicate:
  signal: session_outcome
  value: no_pain_expressed
  threshold: 3
  window_days: 60
```

An encounter detector could then evaluate this automatically against structured logs — no human required to notice when a falsification condition has been met.

---

### 2. Automated encounter detection

Today, `encounter_count` is manually incremented. The system relies on a human or agent noticing "this situation matches that card" — which is exactly the kind of thing that gets forgotten.

The ideal version runs an encounter detector as a background job: embed card claims, run over session transcripts or event logs weekly, auto-match situations to cards, and increment encounter_count with a timestamp and evidence snippet.

---

### 3. System-level calibration tracking

Today, confidence is tracked per card (before/after). There's no aggregate view: "How well-calibrated is this agent's belief system overall?"

The ideal version tracks every prediction with a timestamp and confidence score. When outcomes are observed, calibration is updated. A weekly calibration report answers: "In the last 90 days, predictions made at 0.7+ confidence were correct X% of the time."

Consistent over-confidence or under-confidence is a system-level signal that should affect how much weight to put on new beliefs.

---

### 4. Adversarial pre-promotion pass

Today, a card moves from tested_once to validated when its author (or the reviewing agent) decides the evidence is sufficient. There's no adversarial check.

The ideal version adds a pre-promotion gate: before a card becomes validated, a second agent (or a higher-capability model) is given the card and asked: "What's the strongest counter-evidence? What would have to be true for this to be wrong? Are the confirming encounters actually representative, or are they drawn from a narrow context?"

If the adversarial pass finds a material objection, it blocks promotion and appends a `# Challenges` section to the card.

---

### 5. Action-outcome feedback loop

Today, beliefs don't connect to decisions, and decisions don't connect to outcomes. The evidence gate tracks what you believe, but not whether acting on that belief produced better results.

The ideal version closes this loop: when an agent takes an action based on a validated card, it logs the action and the observed outcome back to the card. This creates a feedback signal from decisions to belief confidence — the full scientific loop.

---

### 6. Auto-staging for clear cases

Today, every card promotion requires a human to move the file. The triage system surfaces stale cards, but a human has to actually do the work.

The ideal version auto-stages cards when their evidence thresholds are clearly met — moving them to a `staged_for_promotion/` directory and sending a summary for human confirmation. The human approves or denies; the agent executes. This keeps humans in the loop for the judgment call while removing the operational friction.

---

## What Won't Be Added

- **Database backend.** Files stay files. The simplicity is a feature.
- **AI-generated cards.** The schema can be written by an agent, but the falsification condition and scope require judgment. Don't automate those away.
- **Confidence scores for everything.** Calibration tracking is for predictions, not for every belief. Some things don't have a falsifiable prediction — that's fine.
- **Public card repositories.** Evidence Gate is a private epistemology layer. Sharing card contents is the user's choice, not the system's default.

---

## Contributing

PRs welcome. Focus areas: the encounter detection pattern, structured falsification predicates, and calibration tracking. See the philosophy doc before proposing structural changes to the lifecycle.
