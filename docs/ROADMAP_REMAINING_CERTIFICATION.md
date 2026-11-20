# Roadmap follow-up: worker recovery

Wave 26 worker recovery improvement: processing jobs with missing/invalid or expired claim timestamps (10-minute lease) are recovered. Attempts at or above the worker limit are terminally failed; otherwise jobs are requeued with bounded backoff. This mitigates stranded jobs after worker crashes.

## Remaining certification blockers
- Idempotency keys/provider reconciliation (duplicate risk after provider accepted request but response lost).
- Instagram media processing polling, URL validation and media upload flow.
- YouTube publishing adapter and account integration.
- Billing provider checkout/webhooks and atomic entitlements.
- Web/mobile user flows, push/email providers.
- CI full test suite, static analysis and integration tests.
- Rate limiting, secrets rotation, security audit, load testing, backups/restore drills and deployment validation.
