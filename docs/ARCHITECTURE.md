# Architecture baseline

## Principles
- Modular monolith first; extract services only when operational evidence warrants it.
- API-first, versioned contracts and explicit validation.
- PostgreSQL is the source of truth; Redis is disposable cache/queue infrastructure.
- Provider credentials and tokens must never be stored in plaintext.
- All tenant-owned data must be scoped by workspace and authorization checks.
- External API calls require timeouts, bounded retries, backoff, rate-limit handling, and observability.
- AI output is treated as untrusted data and validated before persistence or action.

## Current scaffold
- Next.js web app
- FastAPI API with health endpoints
- PostgreSQL and Redis via Docker Compose
- CI baseline

This scaffold is not production-certified. Readiness checks, migrations, authentication, secrets management, test coverage, monitoring, backup/restore and deployment hardening are subsequent implementation requirements.
