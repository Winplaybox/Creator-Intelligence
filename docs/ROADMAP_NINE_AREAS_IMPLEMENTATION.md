# Nine-area roadmap foundation

This PR introduces reusable, testable primitives that can be adopted by the remaining roadmap areas. It is a foundation PR, not a production-completion claim.

## Areas covered

1. **Provider reconciliation / duplicate prevention** — stable workspace-scoped operation fingerprints. Database unique constraints, transactional enqueue and provider reconciliation still need to be wired to queue persistence.
2. **Media safety / hosting** — HTTP(S) URL shape validation rejects credentials, localhost, nonstandard ports and private IP literals. DNS validation is optional/advisory; production fetchers must re-check every redirect and enforce DNS/IP at connection time to prevent rebinding.
3. **YouTube publishing certification** — bounded retry delay primitive and existing worker tests; provider ambiguity reconciliation and refresh-token concurrency lock remain integration work.
4. **Billing / entitlements** — subscription lifecycle transition validator. Checkout, signed webhooks, replay protection and atomic entitlement ledger are not implemented by this helper.
5. **Web/mobile workflows** — this PR defines deterministic retry semantics; complete creator workflow UI/E2E remains open.
6. **Notifications** — explicit channel/category preference gate and unsubscribe gate. Provider delivery queue, consent persistence, and bounce handling remain open.
7. **Security** — URL safety primitive and request-ID normalization; authz/tenancy audit, distributed rate limiting, CORS review and dependency audit remain open.
8. **Reliability / observability** — bounded backoff primitive and safe request-ID helper. Metrics, traces, alerts and soak testing remain open.
9. **Production certification** — these helpers are covered by unit tests; deployment, restore, rollback and release drills remain open.

## Production integration constraints

- Idempotency fingerprints are not substitutes for a DB unique index or transaction.
- URL validation must run before any outbound request; redirect targets must be revalidated. Resolve DNS at connection time and reject any non-public address to mitigate SSRF/rebinding.
- Do not use in-memory rate limits in multi-worker production.
- Notification opt-outs must be persisted and enforced for every delivery path.
- Provider publishing remains feature-flagged and must be tested with mocked provider responses.
- Billing state must only be updated after verified, replay-protected webhook events.
- Do not mark any roadmap wave production-ready until its acceptance tests and operational drills are completed.
