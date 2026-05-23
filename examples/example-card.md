---
id: CARD-20260101-001-async-updates-reduce-interruption
title: Async delivery reduces interruption without reducing information transfer
status: tested_once
created: 2026-01-01
tested_date: 2026-01-15
source: user-feedback-session-jan-2026
domain: product
retest_after_n_encounters: 3
encounter_count: 2
confidence_before: 0.65
scope_conditions: applies to status updates for background tasks lasting > 30 minutes
behavioral_impact_last_seen: 2026-01-20
---

# Claim

For background tasks that run longer than 30 minutes, delivering results
asynchronously (to a secondary channel) is preferred over interrupting
the user mid-session — and produces equivalent or better information
transfer as measured by user ability to recall key outcomes.

# Why we believe it

- Users explicitly asked for fewer interruptions during active work sessions
- Async delivery allows users to review on their own schedule
- Secondary channels (e.g., messaging) already have user attention at natural breakpoints

Counter-evidence to track: some users may miss async updates if they don't
check the secondary channel. Check for this pattern.

# Scope

**Applies to:** background tasks > 30 minutes where the result is not time-critical.

**Does NOT apply to:** tasks requiring immediate user action, error conditions, or tasks
the user explicitly asked to be notified about immediately.

**Explicit falsification condition:**
If users consistently miss async updates and express that they wanted to be
notified earlier, this belief should be demoted. Specifically: if 3+ users
in the same month report missing an important async update they wish had
been delivered immediately, this card should move to falsified.

# Prediction

**Written 2026-01-05, before the A/B test.**

Users in the async group will rate information completeness equally to or higher
than the synchronous group, and will report fewer interruptions as a negative.
Confidence before: 0.65.

# Test

- A/B tested two delivery modes for a background processing task: immediate
  inline notification vs. async delivery to a secondary channel
- 40 users, 20 per group, over 2 weeks
- Measured: self-reported interruption impact (1–5), ability to recall 3 key
  outcomes from the last background task result

# Outcome

- Async group: avg interruption impact 1.8/5 (less negative), recall score 74%
- Sync group: avg interruption impact 3.1/5 (more negative), recall score 71%
- Outcome partially matches prediction: recall is roughly equivalent, interruption
  impact is significantly lower in the async group
- No users in the async group reported missing a time-critical update (test period)

# Proxy Encounters

**Weak encounter:** A user mentions preferring async updates in a feedback session.
**Medium encounter:** Observed pattern where users review async updates within 30 minutes of delivery.
**Strong encounter:** A user explicitly attributes a good outcome to receiving an async update vs. being interrupted mid-task.

Increment encounter_count on medium or strong encounters.
