# Creator Intelligence on the Hostinger VPS

Runs next to OVD on the same VPS. OVD's Caddy terminates TLS for every app; this stack only joins the
`winplaybox_edge` Docker network (created by the OVD stack) and publishes no ports.

| Host | Service |
|---|---|
| `creator.winplaybox.in` | `ci-web` (Next.js) |
| `creator-api.winplaybox.in` | `ci-api` (FastAPI) |

## Deploy

```sh
# DNS (hPanel): A records `creator` and `creator-api` -> VPS IP
git clone https://github.com/Winplaybox/creator-intelligence /opt/creator && cd /opt/creator
cp .env.production.example .env.production && chmod 600 .env.production && nano .env.production
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.production ps     # ci-api healthy

# enable the sites in OVD's Caddy
cd /opt/ovd && cp deploy/sites/creator.caddy.example deploy/sites/creator.caddy && docker compose restart caddy
curl -fsS https://creator-api.winplaybox.in/ready
```

Migrations run automatically (`alembic upgrade head`) every time the API container starts.
The API refuses to start in production if `JWT_SECRET`, `COOKIE_SECURE`, https-only `CORS_ORIGINS`,
`WEB_BASE_URL`, `ADMIN_EMAILS`, encryption keys or the Dodo webhook secret are missing.

## Google

One OAuth "Web" client: *Authorized JavaScript origins* `https://creator.winplaybox.in`, *redirect URI*
`https://creator-api.winplaybox.in/v1/youtube/callback`. The same client id is the Sign-In audience.

## Dodo Payments (Live)

Products: Creator monthly/yearly, Pro monthly/yearly → `DODO_PRODUCT_*`. Webhook endpoint
`https://creator-api.winplaybox.in/v1/billing/dodo/webhook` (payment.*, refund.*, dispute.*, subscription.*).
OVD and Studio use the same Dodo account; each app ignores the other apps' events via `metadata.app`.

Plans grant credits only on verified `payment.succeeded` (monthly = plan credits, yearly = 12×), exactly once
per payment; refunds/disputes reverse once; cancellation returns the workspace to Free and keeps its credits.
Customers can no longer set their own plan (`PUT /v1/billing/workspace-plan` is platform-admin only).

## Backup

```sh
# 27 3 * * *  cd /opt/creator && docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U creator creator_intelligence | gzip > /opt/creator-backups/ci-$(date +\%F).sql.gz
```
