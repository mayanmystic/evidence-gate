---
id: CARD-YYYYMMDD-NNN-short-slug
title: One-line claim summary
status: candidate
created: YYYY-MM-DD
source: session-or-event-that-generated-this
domain: product  # or: engineering, infra, process, etc.
retest_after_n_encounters: 3
encounter_count: 0
scope_conditions: 
behavioral_impact_last_seen: 
---

# Claim

State the belief precisely. A good claim is:
- Specific enough to be falsifiable
- Scoped (not universal)
- Predictive (implies something about what you'll observe)

Bad: "Users prefer simplicity."
Good: "Users who complete onboarding without any tooltips have higher day-7 retention than those who receive the guided tour."

# Why we believe it

What led to this belief? Include:
- Initial observations or data points
- Analogical reasoning (if any)
- Counter-evidence you're already aware of

# Scope

**Applies to:** (what situations, users, or contexts does this belief cover?)

**Does NOT apply to:** (explicit exclusions — what would look similar but doesn't fit?)

**Explicit falsification condition:**
If [observable event] happens, this belief should be demoted or retired.

# Proxy Encounters

Define what counts as evidence for this card:

**Weak encounter:** [describe a situation that provides marginal evidence]
**Medium encounter:** [describe a situation that provides moderate evidence]
**Strong encounter:** [describe a situation that would substantially confirm or deny this]

Increment `encounter_count` when you observe a medium or strong encounter.
