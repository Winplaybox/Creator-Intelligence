#!/usr/bin/env bash
# Brings Creator Intelligence up on the shared VPS (behind the host nginx). Idempotent; never touches OVD.
set -euo pipefail
D=/opt/creator-intelligence; ENVF=$D/.env.production
if ! command -v docker >/dev/null; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io docker-compose-v2 >/dev/null
  systemctl enable --now docker >/dev/null
fi
docker network inspect winplaybox_edge >/dev/null 2>&1 || docker network create winplaybox_edge >/dev/null
[ -d "$D/.git" ] || git clone -q https://github.com/Winplaybox/Creator-Intelligence.git "$D"
cd "$D" && git pull -q origin main
if [ ! -f "$ENVF" ]; then
  umask 077
  PID=$(systemctl show -p MainPID --value ovd-backend)
  DODO_KEY=$(tr '\0' '\n' < /proc/$PID/environ | sed -n 's/^DODO_PAYMENTS_API_KEY=//p' | head -1)
  [ -n "$DODO_KEY" ] || { echo "no Dodo key found"; exit 1; }
  FERNET() { python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"; }
  cat > "$ENVF" <<ENV
WEB_BASE_URL=https://creator.winplaybox.in
NEXT_PUBLIC_API_URL=https://creator-api.winplaybox.in
CORS_ORIGINS=https://creator.winplaybox.in
POSTGRES_PASSWORD=$(openssl rand -hex 24)
REDIS_PASSWORD=$(openssl rand -hex 24)
JWT_SECRET=$(openssl rand -hex 32)
ADMIN_EMAILS=sagarsuthar530@gmail.com
YOUTUBE_TOKEN_ENCRYPTION_KEY=$(FERNET)
SOCIAL_TOKEN_ENCRYPTION_KEY=$(FERNET)
DODO_ENV=live
DODO_API_KEY=$DODO_KEY
DODO_WEBHOOK_SECRET=
DODO_PRODUCT_CREATOR_MONTHLY=pdt_0Ns7d1IFevE0leBItgnap
DODO_PRODUCT_CREATOR_YEARLY=pdt_0Ns7d1P9FBO608ZTD2QQH
DODO_PRODUCT_PRO_MONTHLY=pdt_0Ns7d1UBHJRfagEguIy1f
DODO_PRODUCT_PRO_YEARLY=pdt_0Ns7d1bbLTadqFqh779K5
ENV
  echo "created $ENVF"
fi
grep -q '^DODO_WEBHOOK_SECRET=whsec_' "$ENVF" || { echo "DODO_WEBHOOK_SECRET not set yet"; exit 1; }
cat > docker-compose.vps.yml <<'YML'
services:
  ci-api:
    ports: ["127.0.0.1:8100:8000"]
  ci-web:
    ports: ["127.0.0.1:3100:3000"]
YML
docker compose -f docker-compose.prod.yml -f docker-compose.vps.yml --env-file "$ENVF" up -d --build
for i in $(seq 1 40); do
  sleep 3
  if curl -sf -m 5 http://127.0.0.1:8100/health >/dev/null; then echo "API HEALTHY after $((i*3))s"; break; fi
  [ "$i" = 40 ] && { echo "API NOT HEALTHY"; docker compose -f docker-compose.prod.yml -f docker-compose.vps.yml logs --tail 30 ci-api; exit 1; }
done
curl -s -m 8 -o /dev/null -w "web: %{http_code}\n" http://127.0.0.1:3100/login
docker compose -f docker-compose.prod.yml -f docker-compose.vps.yml ps --format '{{.Service}} {{.Status}}'
