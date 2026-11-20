# Remaining Roadmap Consolidation — Completion Gates

This document tracks the outstanding production-readiness work. It is a **completion plan**, not a claim that every item is implemented.

## Wave 27 — Provider reconciliation and duplicate prevention
- [ ] DB-enforced unique idempotency key per workspace/queue item
- [ ] Atomic enqueue under concurrent requests
- [ ] Reconcile ambiguous provider outcomes before retrying
- [ ] Persist provider IDs and attempt history

## Wave 28 — Media safety and hosting
- [ ] Host media in application-controlled storage with signed URLs
- [ ] Validate media URL scheme, port, DNS resolution and resolved IPs
- [ ] Prevent DNS rebinding and redirect-based SSRF
- [ ] Revalidate every redirect and container poll URL
- [ ] Provider integration tests using mocked HTTP

## Wave 29 — YouTube publishing certification
- [ ] Worker tests for disabled flag, approval gate, channel resolution, token refresh, file-root restriction, metadata and result persistence
- [ ] DB lock around token refresh to avoid concurrent refresh races
- [ ] Reconcile ambiguous upload sessions and duplicate videos
- [ ] Validate OAuth scopes and revoked-token reconnect path
- [ ] Integration tests without live publishing

## Wave 30 — Billing and entitlements
- [ ] Plan catalog, checkout and provider integration
- [ ] Signature-verified webhook handling and replay protection
- [ ] Subscription lifecycle state machine
- [ ] Atomic usage ledger and entitlement checks
- [ ] Billing test-mode end-to-end tests

## Wave 31 — Web/mobile workflow certification
- [ ] Queue create/edit/schedule/cancel/retry flows
- [ ] API error, loading, empty and offline states
- [ ] Accessibility and keyboard coverage
- [ ] Responsive and mobile parity
- [ ] E2E tests for creator workflows

## Wave 32 — Notifications
- [ ] Email/push providers and verified sender configuration
- [ ] Delivery queue, retry/backoff, dead-letter handling
- [ ] Preferences, unsubscribe and consent
- [ ] Delivery status and tests

## Wave 33 — Security hardening
- [ ] Rate limiting and abuse controls
- [ ] Credential rotation and revocation
- [ ] Security headers and CORS review
- [ ] Threat model and dependency audit
- [ ] SSRF, authz, tenancy and secret-leak regression tests

## Wave 34 — Reliability and observability
- [ ] Metrics, structured logs and traces
- [ ] Correlation IDs through worker/API/provider requests
- [ ] Alerting for stuck queues, provider errors and token expiry
- [ ] Load/soak tests and recovery drills

## Wave 35 — Production certification
- [ ] Backup and restore drill
- [ ] Deployment smoke tests and rollback validation
- [ ] Production readiness review and runbooks
- [ ] Release approval checklist

## Publishing safety defaults
- YouTube publishing worker remains disabled unless explicitly enabled.
- Queue items must carry explicit approval.
- Default YouTube privacy remains private.
- Do not enable provider publishing during CI or certification tests.
