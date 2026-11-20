# Production integrations and account isolation

## YouTube / Instagram / Facebook

Creator Intelligence Studio must use per-user OAuth connections. Never import or reuse personal tokens from Remotion, AnyDownloader, or other repos. The connection record is workspace-scoped; tokens are encrypted at rest, access is granted only after the user's OAuth consent, and revocation/reconnect must be supported. Redirect URIs must be exact-match registered per environment (local, staging, production).

## Google login

Backend endpoints:
- `GET /v1/auth/google/start`
- `GET /v1/auth/google/callback`
- `POST /v1/auth/google/ticket?ticket=...`

Google callback uses one-time Redis state, exchanges the code, validates ID-token audience/issuer/email verification, creates or reuses an account, and issues a short-lived one-time ticket to avoid access tokens in URL query parameters. The web callback must redeem the ticket and store the access token according to the app's session policy. Configure `GOOGLE_OAUTH_REDIRECT_URI` exactly in Google Cloud Console. Do not enable in production until CI and security review pass.

## Dodo Payments

Billing must be server-side. Live mode is opt-in through environment configuration. Do not trust client-provided plan names or payment status. Webhook events must be signature-verified, replay/idempotency protected, and processed transactionally before entitlements change. Checkout URLs must be created server-side and validated. A real live merchant credential, product IDs, webhook secret, and endpoint registration are required by an account owner before launch.

## Readiness endpoint

`GET /v1/integrations/readiness` reports only whether required configuration values are present. It does not test provider connectivity, validate redirect registrations, or guarantee production readiness. It never returns secrets.

## Launch checklist

- Set HTTPS, secure cookies, production JWT secret, database/Redis and CORS origins.
- Register exact OAuth redirect URIs in each provider console.
- Set provider credentials in deployment secret storage (not Git).
- Run test-mode payment/webhook integration tests and OAuth tests.
- Verify YouTube channel selection and token revocation/reconnect.
- Review authorization and workspace isolation.
- Keep payment/live publishing disabled until all tests, adult account-owner review, and deployment approvals are complete.
