# Wave 20 — Production Certification Gate

This checklist defines release evidence. The project is **not certified** until every required gate has evidence and an accountable reviewer has approved the release.

## 1. CI and build
- [ ] API unit and integration tests pass
- [ ] Web lint, typecheck and production build pass
- [ ] Mobile typecheck and Expo prebuild/native build pass for Android
- [ ] iOS build passes on macOS CI
- [ ] Migration upgrade and rollback rehearsal pass
- [ ] Coverage thresholds configured and met

## 2. Identity and tenancy
- [ ] Registration/login/refresh/logout tests
- [ ] Refresh token rotation and reuse detection
- [ ] OAuth state and PKCE verification
- [ ] Workspace isolation tests across all routers
- [ ] Role/permission enforcement for every write endpoint
- [ ] Account recovery and email verification implemented and verified
- [ ] Session revocation and account disable behavior verified

## 3. Provider integrations
- [ ] YouTube OAuth consent and disconnect/reconnect lifecycle
- [ ] YouTube Analytics scope and reports validated with real test channel
- [ ] Quota reservation, retries and backoff verified
- [ ] Social provider OAuth token encryption, refresh, revocation and publish APIs
- [ ] Webhook signatures, replay defense and idempotency
- [ ] Provider errors and rate limits handled

## 4. Publishing and background jobs
- [ ] Queue duplicate protection at database level
- [ ] Worker leases recover after crash
- [ ] Retry policy bounded and dead-letter handling defined
- [ ] Scheduling timezone and daylight-saving behavior tested
- [ ] Approval gating enforced before publish
- [ ] Provider-side idempotency / duplicate upload prevention
- [ ] Audit trail for publish attempts and outcomes

## 5. Billing and entitlements
- [ ] Payment provider test/live mode separated
- [ ] Webhook signature verification and replay handling
- [ ] Subscription lifecycle and cancellation tested
- [ ] Credits and entitlements enforced server-side
- [ ] Usage idempotency backed by unique constraint
- [ ] Refund, dispute, failed-payment and grace-period behavior defined
- [ ] Billing secrets never logged

## 6. Security
- [ ] Secrets rotated and environment templates contain no secrets
- [ ] Production JWT, encryption and cookie settings reviewed
- [ ] HTTPS and secure headers enabled
- [ ] CORS origins restricted
- [ ] Rate limits on auth, AI and provider endpoints
- [ ] Input validation and output redaction reviewed
- [ ] Dependency and container scans clean
- [ ] Threat model and penetration test findings triaged

## 7. Observability and operations
- [ ] Structured logs with request IDs; no secrets or token payloads
- [ ] Metrics for latency, error rate, queue depth and provider quota
- [ ] Alerts for API health, DB/Redis, workers and provider failures
- [ ] Readiness probes validated during dependency outage
- [ ] Dashboards and incident runbooks published
- [ ] Backup schedule and restore drill completed
- [ ] Disaster recovery targets (RPO/RTO) documented and tested

## 8. Product and UX
- [ ] Responsive web layouts validated on common viewport sizes
- [ ] Mobile accessibility, navigation and error states reviewed
- [ ] Empty/loading/error states across key screens
- [ ] User-facing permission explanations and consent flows
- [ ] Privacy policy, terms and data-retention policy reviewed
- [ ] Account deletion and export workflow validated

## 9. Release
- [ ] Staging deployment smoke tests passed
- [ ] Release owner and rollback plan assigned
- [ ] Database migration backup confirmed
- [ ] Feature flags and kill switches documented
- [ ] Production smoke tests passed
- [ ] Release notes and support path published

## Certification record
- Release/version:
- Commit:
- Environment:
- Evidence links:
- Reviewer:
- Approval date:

A checkbox alone is not evidence. Attach CI links, logs, test reports, screenshots or provider test results for every gate.