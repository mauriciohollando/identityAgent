# Transaction log model (ground truth for reputation)

This document defines what the **transaction log service** records and how those records become `success_rate` and `sample_size` for the Trust Auditor.

## Outcomes

| Outcome | Meaning | Used in success_rate denominator |
|---------|---------|----------------------------------|
| `success` | Work met the agreed acceptance criteria. | Yes (numerator if counted as success). |
| `failure` | Work did not complete successfully (error, timeout, rejection). | Yes (counts against success). |
| `refunded` | Payer was made whole after a completed or charged interaction. | Yes (counts like failure for the rate). |
| `disputed` | Outcome is under dispute; not treated as settled success/failure. | **No** — excluded until you add a resolution flow. |
| `cancelled` | Legitimately withdrawn before meaningful work (e.g. user cancelled pre-start). | **No** — excluded so the rate reflects attempted work. |

**Success rate (v1):**

`success_rate = successes / (successes + failures + refunds)`

where `refunds` is the count of `refunded` events. If the denominator is zero, the API returns `success_size: 0` and omits or zero-fills `success_rate` (auditor client treats missing as default).

## Context

Optional string (e.g. `payments`, `support`) stored on each event. The auditor passes `context` as a query parameter; the log service filters aggregates to events whose `context` matches when provided.

## Time window

Only events with `created_at` within the last **N** days are included. Default **N** = `LOG_AGGREGATION_WINDOW_DAYS` (default 90).

## Fairness notes

- Define **acceptance criteria** in your product docs so `success` vs `failure` is not arbitrary.
- **Disputes** should eventually resolve to `success`, `failure`, or `refunded`; until then they are excluded from the headline rate to avoid double-counting uncertainty.
- For high-value use cases, prefer **raw event export** plus server-side aggregation you control, rather than only pre-aggregated numbers from partners.
