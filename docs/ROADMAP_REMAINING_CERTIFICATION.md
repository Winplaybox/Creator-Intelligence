# Remaining roadmap: implementation and certification

## Implemented foundations in this PR
- Publishing queue accepts an optional idempotency key and returns the existing queue item for repeat submissions within the workspace.
- Instagram Reels publishing waits for media-container processing to finish before requesting publication, with bounded polling (90 seconds) and terminal provider error handling.
- Unit coverage for Instagram container status classification.

## Wave 27 — publishing safety (partial)
- Queue-level duplicate submission lookup is implemented when clients provide an idempotency key.
- **Certification blocker:** this is a lookup-before-insert, not a database-enforced unique constraint; concurrent requests can race. Provider-level reconciliation/idempotency is still needed to prevent duplicate posts after ambiguous provider responses.

## Wave 28 — Instagram reliability (partial)
- Reels container processing is polled before media publish.
- Implemented in follow-up: public HTTPS URL checks reject credentials, non-443 ports, localhost/local hosts, and private/reserved IP literals. Photo and Reel containers both wait for `FINISHED` before publish.
- Remaining: application-controlled media hosting/allowlist and DNS-rebinding defenses, provider reconciliation, real-account integration tests.

## Wave 29 — YouTube publishing (partial)
- OAuth now requests the `youtube.upload` scope in addition to read/analytics scopes (users must reconnect to grant it).
- Added a worker-side resumable upload primitive with streamed file chunks and metadata/privacy validation.
- Still required: token refresh/permission gating in upload worker, queue integration, scheduling/retries, integration tests, and provider reconciliation.

## Wave 30 — billing (not implemented)
- Plan catalog and usage ledger are foundations only. Payment checkout, signature-verified webhooks, subscription lifecycle and atomic entitlement enforcement remain required.

## Wave 31 — web/mobile workflows (not certified)
- API and web studio exist. Full end-to-end queue workflows, UX coverage, mobile parity and cross-platform acceptance tests remain required.

## Wave 32 — notifications (partial)
- Workspace inbox API exists. External email/push delivery, delivery retries and provider integrations remain required.

## Wave 33 — security hardening (not certified)
- Rate limits, token rotation, SSRF-safe media validation, security audit and threat model remain required.

## Wave 34 — reliability & observability (partial)
- Request correlation and basic health endpoints exist. Full metrics, traces, alerting, load tests and provider integration suites remain required.

## Wave 35 — production certification (not certified)
- Backups and restore drills, deployment validation, production smoke tests, operational runbooks and release approval remain required.

No live publishing, billing, or external delivery is enabled by this PR. CI results must be reviewed before merge.
