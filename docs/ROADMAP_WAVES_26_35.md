# Remaining roadmap Waves 26–35

- 26 Publishing worker: opt-in polling process; Meta FB text/link and IG photo/Reels dispatch; capped exponential retries. Still missing idempotency/fencing, media upload/processing polling, YouTube adapter.
- 27 Billing: existing plan/usage APIs; payment checkout/webhooks and transactional entitlements remain incomplete.
- 28 Admin: allow-listed operational API, no admin UI.
- 29 Web: API contracts ready for integration; frontend not fully wired.
- 30 Mobile: shared API only; mobile UI integration not complete.
- 31 Notifications: existing inbox; push/email provider not configured.
- 32 Analytics/observability: request ID + structured latency logs; no external telemetry.
- 33 CI: existing pipeline; this PR adds worker policy smoke test.
- 34 Security: admin allow-list and opt-in worker; rate limits, token refresh, SSRF/media checks, secrets rotation still required.
- 35 Production/DR: operator checklist; restore drills, load tests, TLS, provider review and live account publishing certification remain gates.

Run from apps/api: `python -m app.worker`. Enable only after staging verification: `PUBLISHING_WORKER_ENABLED=true`. Set `ADMIN_EMAILS` to exact comma-separated allow-listed addresses.
